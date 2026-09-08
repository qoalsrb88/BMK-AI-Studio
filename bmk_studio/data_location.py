"""User-selected data roots and verified, non-destructive copy migration."""
import json,os,shutil,sqlite3,uuid,hashlib
from pathlib import Path
from contextlib import closing
from PySide6.QtCore import QLockFile

INCOMPLETE='.bmk-transfer-incomplete'
LOCK='.bmk-studio.lock'
session_directory=None

def config_path():return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BMK-AI-Studio-config'/'data-location.json'
def default_directory():return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BMK-AI-Studio'
def resolve_directory(config=None):
    if session_directory:return Path(session_directory).expanduser().resolve()
    if os.environ.get('BMK_STUDIO_DATA','').strip():return Path(os.environ['BMK_STUDIO_DATA']).expanduser().resolve()
    config=Path(config) if config else config_path()
    if config.exists():
        value=json.loads(config.read_text(encoding='utf-8'))
        path=value.get('directory') if isinstance(value,dict) else None
        if not isinstance(path,str) or not Path(path).is_absolute():raise ValueError('사용자 데이터 경로 설정이 손상되었습니다: '+str(config))
        if not Path(path).is_dir():raise ValueError('지정한 사용자 데이터 폴더를 찾을 수 없습니다. 드라이브 연결을 확인하거나 --user-directory로 폴더를 지정하세요: '+path)
        return Path(path).resolve()
    return default_directory().resolve()

def check_directory(path):
    path=Path(path).resolve();path.mkdir(parents=True,exist_ok=True)
    if (path/INCOMPLETE).exists():raise ValueError('완료되지 않은 데이터 복사 폴더입니다. 기존 데이터 폴더를 계속 사용하세요: '+str(path))
    probe=path/('.bmk-write-test-'+uuid.uuid4().hex)
    try:
        with probe.open('xb') as stream:stream.write(b'BMK')
    finally:probe.unlink(missing_ok=True)
    return path

def lock_directory(path):
    lock=QLockFile(str(Path(path)/LOCK));lock.setStaleLockTime(0)
    if not lock.tryLock(0):raise ValueError('이 사용자 데이터 폴더를 사용하는 다른 BMK AI Studio를 종료하세요: '+str(path))
    return lock

def validate_existing(path):
    path=check_directory(path);content=[p for p in path.iterdir() if p.name!=LOCK]
    if content and not (path/'library.sqlite3').is_file():raise ValueError('빈 폴더 또는 library.sqlite3가 있는 BMK 사용자 데이터 폴더를 선택하세요.')
    for database in path.rglob('*.sqlite3'):
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('사용자 데이터베이스가 손상되었습니다.')
            if database==path/'library.sqlite3':
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'notes','assets'}.issubset(tables):raise ValueError('BMK 사용자 데이터베이스 형식이 아닙니다.')
    return path

def save_choice(path,config=None):
    config=Path(config) if config else config_path();config.parent.mkdir(parents=True,exist_ok=True)
    temporary=config.with_name(config.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump({'schema':1,'directory':str(Path(path).resolve())},stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,config)
    finally:temporary.unlink(missing_ok=True)

def path_mapper(source,target):
    def remap(value):
        if not isinstance(value,str) or not Path(value).is_absolute():return value
        try:return str(target/Path(value).relative_to(source))
        except ValueError:return value
    return remap

def rewrite_record(record,remap):
    """Only operational path fields; original metadata and note bodies stay verbatim."""
    if not isinstance(record,dict):return record
    for key in ('source','base','mask','stitch','tone'):
        if key in record:record[key]=remap(record[key])
    for key in ('crop_context','crop','context'):
        if isinstance(record.get(key),dict):rewrite_record(record[key],remap)
    if isinstance(record.get('operations'),list):
        for operation in record['operations']:rewrite_record(operation,remap)
    if isinstance(record.get('exported_state'),str) and record['exported_state']:
        state=json.loads(record['exported_state']);rewrite_record(state,remap);record['exported_state']=json.dumps(state,ensure_ascii=False,indent=2)
    return record

def rewrite_database(path,remap):
    with closing(sqlite3.connect(path)) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with db:
            for table in ('assets','image_index','tag_runs','tag_search','library_hidden','source_identity','favorites','collection_items','visual_signatures','semantic_vectors','large_thumbnails'):
                if table not in tables:continue
                for old, in db.execute(f'SELECT DISTINCT path FROM {table}').fetchall():
                    new=remap(old)
                    if new!=old:db.execute(f'UPDATE {table} SET path=? WHERE path=?',(new,old))
            if 'app_state' in tables:
                for key,value in db.execute('SELECT key,value FROM app_state').fetchall():
                    state=json.loads(value)
                    if key=='window' and isinstance(state,dict):
                        for field in ('path','reference','model'):
                            if field in state:state[field]=remap(state[field])
                    elif key=='tag_queue' and isinstance(state,dict):
                        for field in ('active','pending'):
                            if isinstance(state.get(field),list):state[field]=[remap(v) for v in state[field]]
                    elif key=='disk_browser' and isinstance(state,dict):
                        if 'folder' in state:state['folder']=remap(state['folder'])
                        if isinstance(state.get('favorites'),list):state['favorites']=[remap(v) for v in state['favorites']]
                    elif key=='semantic_settings' and isinstance(state,dict):
                        if 'model' in state:state['model']=remap(state['model'])
                    elif key=='last_deleted_collection' and isinstance(state,dict):
                        if isinstance(state.get('paths'),list):state['paths']=[remap(v) for v in state['paths']]
                    else:continue
                    db.execute('UPDATE app_state SET value=? WHERE key=?',(json.dumps(state,ensure_ascii=False),key))
            if 'checkpoints' in tables:
                for source,state in db.execute('SELECT source,state FROM checkpoints').fetchall():
                    state=rewrite_record(json.loads(state),remap)
                    db.execute('UPDATE checkpoints SET source=?,state=? WHERE source=?',(remap(source),json.dumps(state,ensure_ascii=False),source))
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('복사한 데이터베이스 검증에 실패했습니다.')

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def copy_data(source,target):
    """Caller must quiesce UI/jobs. Source is never deleted or rewritten."""
    source=Path(source).resolve();target=Path(target).resolve()
    if not source.is_dir():raise ValueError('현재 사용자 데이터 폴더가 없습니다.')
    if source==target or source in target.parents or target in source.parents:raise ValueError('현재 데이터 폴더와 같거나 서로 포함하는 폴더는 사용할 수 없습니다.')
    check_directory(target)
    if any(p.name!=LOCK for p in target.iterdir()):raise ValueError('현재 데이터를 복사하려면 비어 있는 폴더를 선택하세요. 기존 파일은 덮어쓰지 않습니다.')
    marker=target/INCOMPLETE;marker.write_text(str(source),encoding='utf-8')
    remap=path_mapper(source,target);count=0
    # A failed/crashed copy retains the marker. It cannot be opened as a valid library.
    for path in source.rglob('*'):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('데이터 폴더의 링크/정션은 복사하지 않습니다: '+str(path))
        relative=path.relative_to(source)
        if path.name==LOCK or path.name.endswith(('.sqlite3-wal','.sqlite3-shm','.sqlite3-journal')):continue
        dest=target/relative
        if path.is_dir():dest.mkdir(exist_ok=True);continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        if path.suffix=='.sqlite3':
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(dest)) as copied:
                original.backup(copied)
            rewrite_database(dest,remap)
        else:
            before=digest(path)
            with path.open('rb') as src,dest.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            shutil.copystat(path,dest)
            if digest(dest)!=before or digest(path)!=before:raise ValueError('복사 중 파일이 변경되었거나 복사 검증에 실패했습니다: '+str(path))
            if path.name.endswith('.bmk.json') and relative.parts[0]=='exports':
                record=json.loads(dest.read_text(encoding='utf-8'));rewrite_record(record,remap)
                dest.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        count+=1
    marker.unlink()
    return count

def activate_directory(source,target,copy_current,config=None):
    source=Path(source).resolve();target=Path(target).resolve()
    if source==target:raise ValueError('이미 사용 중인 사용자 데이터 폴더입니다.')
    if source in target.parents or target in source.parents:raise ValueError('서로 포함하지 않는 별도 데이터 폴더를 선택하세요.')
    check_directory(target);lock=lock_directory(target)
    try:
        if copy_current:count=copy_data(source,target)
        else:
            validate_existing(target)
            count=0
        save_choice(target,config)
        return {'directory':str(target),'copied':count}
    finally:lock.unlock()
