"""Build an exclusive ZIP and a SHA256 manifest from a clean, data-free bundle."""
import argparse,hashlib,json,re,zipfile
from pathlib import Path

REQUIRED=('BMK-AI-Studio.exe','build-info.json','LICENSE','README.txt','THIRD_PARTY_NOTICES.md','DEPENDENCY_SOURCES.md')

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def inspect_bundle(folder):
    folder=Path(folder).resolve()
    for name in REQUIRED:
        if not (folder/name).is_file():raise ValueError('Missing release file: '+name)
    if not (folder/'_internal').is_dir() or not (folder/'licenses').is_dir():raise ValueError('Missing runtime or licenses')
    info=json.loads((folder/'build-info.json').read_text(encoding='utf-8-sig'))
    if info.get('source_dirty') is not False or not re.fullmatch('[0-9a-f]{40}',info.get('source_commit','')):raise ValueError('Clean source provenance required')
    files=[]
    for path in sorted(folder.rglob('*')):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Links are not allowed')
        if not path.is_file():continue
        rel=path.relative_to(folder);name=path.name.lower()
        if rel.parts[0].lower() in {'data','user','models','notes','cache','imagesample'} or name in {'local-settings.json','data-location.json','.env'} or '.sqlite' in name or path.suffix.lower() in {'.db','.onnx','.safetensors','.pt','.pth','.ckpt','.lnk','.log'}:
            raise ValueError('Private data, weights or logs in release: '+str(rel))
        if 'virtualkeyboard' in name or name=='qpdf.dll':raise ValueError('Excluded Qt plugin in release: '+str(rel))
        files.append({'path':rel.as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)})
    return {'build':info,'files':files,'file_count':len(files),'total_bytes':sum(item['bytes'] for item in files)}

def package(folder,output):
    folder=Path(folder).resolve();output=Path(output).resolve();manifest=output.with_suffix('.manifest.json')
    if output.exists() or manifest.exists():raise FileExistsError('Existing release outputs are preserved')
    if output==folder or folder in output.parents:raise ValueError('Archive must be outside the bundle')
    report=inspect_bundle(folder);top=output.stem
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as archive:
        for item in report['files']:archive.write(folder/item['path'],top+'/'+item['path'])
    report.update(archive=output.name,archive_root=top,archive_bytes=output.stat().st_size,archive_sha256=digest(output))
    if output.stat().st_size>=2*1024**3:raise ValueError('Release asset exceeds 2 GiB; keep it local and choose another format')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP integrity check failed')
    with manifest.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps({key:report[key] for key in ('archive','archive_bytes','archive_sha256','file_count','total_bytes')},indent=2),flush=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('output');args=parser.parse_args();package(args.folder,args.output)
