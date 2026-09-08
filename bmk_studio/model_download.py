"""Anonymous official WD downloads pinned to a revision and verified before install."""
import csv,hashlib,json,os,re
from pathlib import Path
from urllib.request import Request,urlopen
from PySide6.QtCore import QLockFile

MODELS={
    'WD EVA02 Large v3':'SmilingWolf/wd-eva02-large-tagger-v3',
    'WD ViT v3':'SmilingWolf/wd-vit-tagger-v3',
    'WD SwinV2 v3':'SmilingWolf/wd-swinv2-tagger-v3',
}
REQUIRED={'config.json','model.safetensors','selected_tags.csv'}

class DownloadCancelled(Exception):pass

def official_manifest(repo):
    if repo not in MODELS.values():raise ValueError('목록의 공식 WD v3 모델만 다운로드할 수 있습니다.')
    from huggingface_hub import HfApi
    info=HfApi(token=False).model_info(repo,files_metadata=True,timeout=15)
    if not re.fullmatch('[0-9a-f]{40}',info.sha or ''):raise ValueError('모델 리비전을 확인할 수 없습니다.')
    files=[]
    for file in info.siblings:
        if file.rfilename not in REQUIRED|{'README.md','LICENSE','LICENSE.txt'}:continue
        if file.size is None or not 0<file.size<=8*1024**3:raise ValueError('모델 파일 크기를 확인할 수 없습니다.')
        lfs=file.lfs
        files.append({'name':file.rfilename,'size':file.size,'algorithm':'sha256' if lfs else 'git-sha1','digest':lfs.sha256 if lfs else file.blob_id,
            'url':f'https://huggingface.co/{repo}/resolve/{info.sha}/{file.rfilename}?download=true'})
    if not REQUIRED.issubset({file['name'] for file in files}):raise ValueError('독립 태거에 필요한 파일이 없는 저장소입니다.')
    return {'repo':repo,'revision':info.sha,'files':files}

def verify_file(path,entry):
    if not path.is_file() or path.stat().st_size!=entry['size']:return False
    digest=hashlib.sha256() if entry['algorithm']=='sha256' else hashlib.sha1(b'blob '+str(entry['size']).encode()+b'\0')
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()==entry['digest']

def download_file(entry,path,cancelled=lambda:False,progress=lambda done:None,opener=urlopen):
    if verify_file(path,entry):progress(entry['size']);return
    partial=path.with_name(path.name+'.part')
    if partial.exists() and partial.stat().st_size>=entry['size']:
        if verify_file(partial,entry):os.replace(partial,path);progress(entry['size']);return
        partial.unlink()
    offset=partial.stat().st_size if partial.exists() else 0
    if cancelled():raise DownloadCancelled('다운로드를 취소했습니다. 다시 시작하면 이어받습니다.')
    request=Request(entry['url'],headers={'User-Agent':'BMK-AI-Studio','Accept-Encoding':'identity',**({'Range':f'bytes={offset}-'} if offset else {})})
    with opener(request,timeout=15) as response:
        status=getattr(response,'status',200)
        if status==206:
            value=response.headers.get('Content-Range','')
            if not value.startswith(f'bytes {offset}-') or not value.endswith('/'+str(entry['size'])):raise ValueError('이어받기 응답 범위가 일치하지 않습니다.')
        elif status==200:offset=0
        else:raise ValueError(f'다운로드 응답 오류: {status}')
        with partial.open('ab' if offset else 'wb') as output:
            progress(offset)
            while True:
                if cancelled():raise DownloadCancelled('다운로드를 취소했습니다. 다시 시작하면 이어받습니다.')
                chunk=response.read(1024*1024)
                if not chunk:break
                if offset+len(chunk)>entry['size']:raise ValueError('다운로드 크기가 선언된 파일 크기를 넘었습니다.')
                output.write(chunk);offset+=len(chunk);progress(offset)
    if not verify_file(partial,entry):
        if partial.stat().st_size==entry['size']:partial.unlink()
        raise ValueError('다운로드가 불완전하거나 해시가 다릅니다. 다시 시작해 재시도하세요.')
    os.replace(partial,path)

def install_model(folder,manifest,cancelled=lambda:False,progress=lambda payload:None):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    repo=manifest['repo'];revision=manifest['revision']
    if repo not in MODELS.values() or not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('지원하지 않는 모델 매니페스트입니다.')
    names={entry['name'] for entry in manifest['files']}
    if not REQUIRED.issubset(names) or not names.issubset(REQUIRED|{'README.md','LICENSE','LICENSE.txt'}):raise ValueError('모델 파일 목록이 유효하지 않습니다.')
    name=repo.split('/')[1]+'-'+revision[:12];target=folder/name
    lock=QLockFile(str(folder/(name+'.lock')));lock.setStaleLockTime(0)
    if not lock.tryLock(0):raise ValueError('같은 모델의 다운로드가 다른 실행에서 진행 중입니다.')
    try:
        if target.exists():
            if all(verify_file(target/file['name'],file) for file in manifest['files']):return str(target)
            raise ValueError('설치 경로에 검증되지 않는 파일이 있습니다. 기존 폴더는 덮어쓰지 않습니다.')
        staging=folder/'.downloads'/name;staging.mkdir(parents=True,exist_ok=True)
        total=sum(entry['size'] for entry in manifest['files']);completed=0
        for entry in manifest['files']:
            base=completed
            download_file(entry,staging/entry['name'],cancelled,lambda done:progress({'done':base+done,'total':total,'file':entry['name']}))
            completed+=entry['size']
        if cancelled():raise DownloadCancelled('다운로드를 취소했습니다. 검증된 파일은 재사용합니다.')
        config=json.loads((staging/'config.json').read_text(encoding='utf-8'))
        if not isinstance(config,dict) or not config.get('architecture'):raise ValueError('모델 설정 형식이 유효하지 않습니다.')
        with (staging/'selected_tags.csv').open(encoding='utf-8') as stream:
            reader=csv.DictReader(stream)
            if not {'name','category'}.issubset(reader.fieldnames or []):raise ValueError('태그 목록 형식이 유효하지 않습니다.')
        from safetensors import safe_open
        with safe_open(str(staging/'model.safetensors'),framework='numpy') as weights:
            if not list(weights.keys()):raise ValueError('모델 가중치가 비어 있습니다.')
        (staging/'install_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        staging.rename(target)
        return str(target)
    finally:lock.unlock()
