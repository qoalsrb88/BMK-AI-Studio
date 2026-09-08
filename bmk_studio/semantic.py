"""Local multilingual text embeddings. No image/prompt upload or remote code."""
import json,hashlib,re,sqlite3
from pathlib import Path
from contextlib import closing
import numpy as np
from .model_download import download_file,verify_file,DownloadCancelled
from .organize import field

REPO='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
FILES={'onnx/model_quint8_avx2.onnx','tokenizer.json','tokenizer_config.json','config.json'}

def manifest():
    from huggingface_hub import HfApi
    info=HfApi(token=False).model_info(REPO,files_metadata=True,timeout=20)
    if not re.fullmatch('[0-9a-f]{40}',info.sha or ''):raise ValueError('모델 리비전 확인 실패')
    files=[]
    for entry in info.siblings:
        if entry.rfilename not in FILES|{'README.md','LICENSE','LICENSE.txt'}:continue
        if not entry.size or entry.size>600*1024**2:raise ValueError('모델 크기 확인 실패')
        files.append({'name':entry.rfilename,'size':entry.size,'algorithm':'sha256' if entry.lfs else 'git-sha1','digest':entry.lfs.sha256 if entry.lfs else entry.blob_id,'url':f'https://huggingface.co/{REPO}/resolve/{info.sha}/{entry.rfilename}?download=true'})
    if not FILES.issubset({item['name'] for item in files}):raise ValueError('필수 파일 누락')
    return {'repo':REPO,'revision':info.sha,'files':files}

def install(folder,cancelled=lambda:False,progress=lambda value:None):
    from PySide6.QtCore import QLockFile
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);lock=QLockFile(str(folder/'semantic-download.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(0):raise ValueError('의미 검색 모델 다운로드가 이미 진행 중입니다.')
    try:
        info=manifest();target=folder/('multilingual-minilm-'+info['revision'][:12]);staging=folder/'.downloads'/target.name
        if target.exists():
            if all(verify_file(target/item['name'],item) for item in info['files']):return str(target)
            raise ValueError('기존 모델이 검증되지 않습니다. 기존 폴더를 덮어쓰지 않습니다.')
        staging.mkdir(parents=True,exist_ok=True);total=sum(item['size'] for item in info['files']);done=0
        for item in info['files']:
            path=staging/item['name'];path.parent.mkdir(parents=True,exist_ok=True);base=done
            download_file(item,path,cancelled,lambda count:progress((base+count,total,'모델 다운로드')));done+=item['size']
        if cancelled():raise DownloadCancelled('다운로드 취소 · 다음 실행에서 이어받습니다.')
        (staging/'install_manifest.json').write_text(json.dumps(info,indent=2),encoding='utf-8');staging.rename(target);return str(target)
    finally:lock.unlock()

class Encoder:
    def __init__(self,folder):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        folder=Path(folder);info=json.loads((folder/'install_manifest.json').read_text(encoding='utf-8'))
        if info.get('repo')!=REPO or not re.fullmatch('[0-9a-f]{40}',info.get('revision','')):raise ValueError('지원 모델 설치 정보를 확인하세요.')
        self.key=info['revision']+':quint8-mean128-v1'
        required={entry['name']:entry for entry in info['files'] if entry['name'] in FILES}
        if set(required)!=FILES or not all(verify_file(folder/name,entry) for name,entry in required.items()):raise ValueError('의미 검색 모델 해시 검증 실패')
        self.tokenizer=Tokenizer.from_file(str(folder/'tokenizer.json'));self.tokenizer.enable_truncation(max_length=128);self.tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(folder/'onnx/model_quint8_avx2.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    def encode(self,texts):
        tokens=self.tokenizer.encode_batch(texts);values={'input_ids':np.asarray([t.ids for t in tokens],dtype=np.int64),'attention_mask':np.asarray([t.attention_mask for t in tokens],dtype=np.int64),'token_type_ids':np.asarray([t.type_ids for t in tokens],dtype=np.int64)}
        embeddings=self.session.run(None,{item.name:values[item.name] for item in self.session.get_inputs()})[0]
        mask=values['attention_mask'][...,None].astype(np.float32);vectors=(embeddings*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
        return (vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-9)).astype(np.float32)

def search(database,paths,query,folder,source='positive',limit=100,cancelled=lambda:False,progress=lambda value:None,encoder_factory=Encoder):
    if source not in ('positive','work','tags'):raise ValueError('검색할 텍스트 출처를 선택하세요.')
    encoder=encoder_factory(folder);query_vector=encoder.encode([query])[0];results=[];skipped=0;batch=[]
    with closing(sqlite3.connect(database)) as db:
        def consume():
            nonlocal batch
            if not batch:return
            vectors=encoder.encode([item[2] for item in batch])
            with db:
                for (path,signature,text),vector in zip(batch,vectors):
                    if cancelled():break
                    db.execute('INSERT OR REPLACE INTO semantic_vectors VALUES(?,?,?,?,?)',(path,source,signature,encoder.key,vector.tobytes()))
                    results.append((float(vector@query_vector),path))
            batch=[]
        for n,path in enumerate(paths):
            if cancelled():break
            row=db.execute('SELECT i.searchable,a.draft,t.text FROM image_index i LEFT JOIN assets a ON a.path=i.path LEFT JOIN tag_search t ON t.path=i.path AND t.stamp=i.stamp WHERE i.path=?',(path,)).fetchone()
            if not row:skipped+=1;continue
            text=field(row[0],'positive') if source=='positive' else (row[1] if source=='work' else row[2]);text=(text or '').strip()
            if not text:skipped+=1;continue
            signature=hashlib.sha256(text.encode()).hexdigest();cached=db.execute('SELECT vector FROM semantic_vectors WHERE path=? AND source=? AND signature=? AND model=?',(path,source,signature,encoder.key)).fetchone()
            if cached:
                vector=np.frombuffer(cached[0],dtype=np.float32)
                if vector.shape==query_vector.shape and np.isfinite(vector).all():results.append((float(vector@query_vector),path))
                else:batch.append((path,signature,text))
            else:batch.append((path,signature,text))
            if len(batch)>=8:consume()
            progress((n+1,len(paths),'텍스트 의미 색인 / 검색'))
        if not cancelled():consume()
    return {'matches':sorted(results,reverse=True)[:limit],'skipped':skipped,'cancelled':cancelled(),'source':source}
