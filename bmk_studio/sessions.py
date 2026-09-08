"""Transactional, local image checkpoints. Never executes saved operations as code."""
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path
from .core import fingerprint,load_image,json_text

class Sessions:
    def __init__(self,root):
        self.root=Path(root).resolve();self.folder=self.root/'sessions';self.folder.mkdir(parents=True,exist_ok=True)
        self.db_path=self.root/'sessions.sqlite3'
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS checkpoints(source TEXT PRIMARY KEY, state TEXT NOT NULL, snapshot TEXT NOT NULL, hash TEXT NOT NULL, updated TEXT NOT NULL)');db.commit()
    def entries(self):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute('SELECT source,updated FROM checkpoints ORDER BY updated DESC').fetchall()
    def contains(self,path):
        with closing(sqlite3.connect(self.db_path)) as db:
            return db.execute('SELECT 1 FROM checkpoints WHERE source=?',(str(Path(path).resolve()),)).fetchone() is not None
    def remove(self,path):
        """Retire only our checkpoint reference and generated snapshot."""
        source=str(Path(path).resolve())
        with closing(sqlite3.connect(self.db_path)) as db:
            row=db.execute('SELECT snapshot FROM checkpoints WHERE source=?',(source,)).fetchone()
            with db:db.execute('DELETE FROM checkpoints WHERE source=?',(source,))
        if row:
            target=(self.folder/row[0]).resolve()
            try:
                target.relative_to(self.folder)
                if len(target.stem)==32 and target.suffix=='.png':target.unlink(missing_ok=True)
            except (ValueError,OSError):pass
    def validate(self,state):
        if not isinstance(state,dict) or state.get('schema')!=1:raise ValueError('지원하지 않는 작업 보관 형식입니다.')
        if not isinstance(state.get('operations'),list):raise ValueError('작업 기록이 손상되었습니다.')
        if state.get('rotation',0) not in (0,90,180,270):raise ValueError('작업 회전 정보가 손상되었습니다.')
        box=state.get('box')
        if box is not None and (not isinstance(box,(list,tuple)) or len(box)!=4 or any(not isinstance(v,int) or v<0 for v in box)):
            raise ValueError('작업 영역 정보가 손상되었습니다.')
        source=Path(state['source'])
        if not source.is_file():raise ValueError('작업의 원본 이미지가 없습니다: '+str(source))
        if fingerprint(source)!=state['source_hash']:raise ValueError('원본 이미지가 변경되어 자동 복원을 중단했습니다.')
        ctx=state.get('crop_context')
        if ctx is not None and not isinstance(ctx,dict):raise ValueError('크롭 작업 정보가 손상되었습니다.')
        if ctx:
            for key in ('base','mask'):
                if key not in ctx:continue
                path=Path(ctx[key])
                if not path.is_file() or fingerprint(path)!=ctx[key+'_hash']:
                    raise ValueError('크롭 작업의 '+key+' 파일이 없거나 변경되었습니다.')
        return state
    def save(self,image,state):
        self.validate(state)
        source=str(Path(state['source']).resolve());target=self.folder/(uuid.uuid4().hex+'.png')
        try:
            with target.open('xb') as stream:image.save(stream,format='PNG')
            digest=fingerprint(target);self.validate(state)
            with closing(sqlite3.connect(self.db_path)) as db:
                old=db.execute('SELECT snapshot FROM checkpoints WHERE source=?',(source,)).fetchone()
                with db:db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?,?,?)',(source,json_text(state),target.name,digest,datetime.now().isoformat()))
        except Exception:
            target.unlink(missing_ok=True);raise
        # Only retire this app's previous snapshot, after the replacement is committed.
        if old:
            previous=self.folder/old[0]
            try:
                previous.resolve().relative_to(self.folder.resolve())
                if previous!=target and len(previous.stem)==32 and previous.suffix=='.png':previous.unlink(missing_ok=True)
            except (ValueError,OSError):pass
        return str(target)
    def load(self,path):
        source=str(Path(path).resolve())
        with closing(sqlite3.connect(self.db_path)) as db:
            row=db.execute('SELECT state,snapshot,hash FROM checkpoints WHERE source=?',(source,)).fetchone()
        if row is None:return None
        state=self.validate(json.loads(row[0]))
        if str(Path(state['source']).resolve())!=source:raise ValueError('작업의 원본 경로가 일치하지 않습니다.')
        snapshot=(self.folder/row[1]).resolve()
        snapshot.relative_to(self.folder)
        if not snapshot.is_file() or fingerprint(snapshot)!=row[2]:raise ValueError('보관된 작업 이미지가 없거나 변경되었습니다.')
        return load_image(snapshot),state
