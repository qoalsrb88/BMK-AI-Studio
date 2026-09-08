"""Copy a verified source's local associations to a new path; retain old records."""
import json,sqlite3,uuid,shutil
from pathlib import Path
from contextlib import closing
from .core import Store,fingerprint,file_stamp,json_text
from .sessions import Sessions

def relink_source(root,old,new):
    old=str(Path(old).resolve());new=str(Path(new).resolve())
    if old==new:raise ValueError('다른 원본 경로를 선택하세요.')
    candidate=Path(new)
    if not candidate.is_file():raise ValueError('선택한 원본 파일이 없습니다.')
    stamp=file_stamp(candidate);digest=fingerprint(candidate)
    stores=[Sessions(root),Sessions(Path(root)/'recovery')]
    created=[];committed=False
    try:
        with closing(sqlite3.connect(Path(root)/'library.sqlite3')) as db:
            for name,repo in zip(('manual','recovery'),stores):db.execute(f'ATTACH DATABASE ? AS {name}',(str(repo.db_path),))
            db.execute('BEGIN IMMEDIATE')
            expected=set()
            identity=db.execute('SELECT hash FROM source_identity WHERE path=?',(old,)).fetchone()
            if identity:expected.add(identity[0])
            records=[]
            for name,repo in zip(('manual','recovery'),stores):
                row=db.execute(f'SELECT state,snapshot,hash,updated FROM {name}.checkpoints WHERE source=?',(old,)).fetchone()
                if row:expected.add(json.loads(row[0])['source_hash']);records.append((name,repo,row))
                if db.execute(f'SELECT 1 FROM {name}.checkpoints WHERE source=?',(new,)).fetchone():raise ValueError('새 경로에 이미 보관 작업이 있습니다. 덮어쓰지 않습니다.')
            if not expected and Path(old).is_file():expected.add(fingerprint(old))
            if not expected:raise ValueError('이 원본의 저장된 해시가 없어 동일한 파일인지 확인할 수 없습니다. 기존 원본 또는 보관 기록이 필요합니다.')
            if expected!={digest}:raise ValueError('원본 SHA256이 다릅니다. 같은 이름이나 비슷한 이미지로 재연결할 수 없습니다.')
            for table in ('assets','image_index','tag_runs','tag_search','source_identity'):
                if db.execute(f'SELECT 1 FROM {table} WHERE path=?',(new,)).fetchone():raise ValueError('새 경로에 기존 작업 데이터가 있습니다. 덮어쓰지 않습니다.')
            for name,repo,row in records:
                state=json.loads(row[0]);state['source']=new;repo.validate(state)
                snapshot=(repo.folder/row[1]).resolve();snapshot.relative_to(repo.folder)
                if fingerprint(snapshot)!=row[2]:raise ValueError('보관 이미지가 손상되어 재연결을 중단했습니다.')
                target=repo.folder/(uuid.uuid4().hex+'.png')
                with snapshot.open('rb') as source,target.open('xb') as output:
                    created.append(target);shutil.copyfileobj(source,output)
                if fingerprint(target)!=row[2]:raise ValueError('보관 이미지 복사 검증에 실패했습니다.')
                db.execute(f'INSERT INTO {name}.checkpoints VALUES(?,?,?,?,?)',(new,json_text(state),target.name,row[2],row[3]))
            db.execute('INSERT INTO assets SELECT ?,metadata,draft,negative,memo FROM assets WHERE path=?',(new,old))
            db.execute('INSERT INTO image_index SELECT ?,?,searchable,thumbnail FROM image_index WHERE path=?',(new,stamp,old))
            db.execute('INSERT INTO tag_runs SELECT ?,model_signature,?,cache_key FROM tag_runs WHERE path=?',(new,stamp,old))
            db.execute('INSERT INTO tag_search SELECT ?,?,text FROM tag_search WHERE path=?',(new,stamp,old))
            db.execute('INSERT INTO source_identity VALUES(?,?)',(new,digest))
            for table in ('favorites','collection_items'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                    if table=='favorites':db.execute('INSERT OR IGNORE INTO favorites SELECT ?,rating FROM favorites WHERE path=?',(new,old))
                    else:db.execute('INSERT OR IGNORE INTO collection_items SELECT name,? FROM collection_items WHERE path=?',(new,old))
            db.execute('INSERT OR IGNORE INTO library_hidden VALUES(?)',(old,))
            db.execute('DELETE FROM library_hidden WHERE path=?',(new,))
            saved=db.execute("SELECT value FROM app_state WHERE key='window'").fetchone()
            if saved:
                window=json.loads(saved[0])
                if window.get('path')==old:window['path']=new;db.execute("UPDATE app_state SET value=? WHERE key='window'",(json_text(window),))
            if file_stamp(new)!=stamp or fingerprint(new)!=digest:raise ValueError('재연결 중 원본이 변경되었습니다.')
            db.commit();committed=True
        return new
    finally:
        if not committed:
            for target in created:target.unlink(missing_ok=True)
