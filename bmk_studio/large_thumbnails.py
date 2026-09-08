"""Demand-generated 512px thumbnails; bounded memory and disk, original read-only."""
import sqlite3,io,time
from collections import OrderedDict
from contextlib import closing
from PySide6.QtCore import QObject,QThread,Signal,QTimer
from PIL import Image,ImageOps
from .core import file_stamp,load_image
from .color import high_precision

class ThumbnailJob(QThread):
    ready=Signal(str,object);failed=Signal(str)
    def __init__(self,database,paths,parent=None):super().__init__(parent);self.database=database;self.paths=paths
    def run(self):
        with closing(sqlite3.connect(self.database)) as db:
            for path in self.paths:
                if self.isInterruptionRequested():break
                try:
                    stamp=file_stamp(path);cached=db.execute('SELECT thumbnail FROM large_thumbnails WHERE path=? AND stamp=?',(path,stamp)).fetchone()
                    if cached:blob=cached[0]
                    else:
                        if high_precision(path):image=load_image(path)
                        else:
                            with Image.open(path) as source:
                                source.draft('RGB',(512,512));image=ImageOps.exif_transpose(source).convert('RGBA')
                        image.thumbnail((512,512),Image.Resampling.LANCZOS);stream=io.BytesIO();image.save(stream,format='PNG');blob=stream.getvalue()
                        if stamp!=file_stamp(path):continue
                        with db:db.execute('INSERT OR REPLACE INTO large_thumbnails VALUES(?,?,?,?)',(path,stamp,blob,time.time()))
                    with db:db.execute('UPDATE large_thumbnails SET used=? WHERE path=?',(time.time(),path))
                    if stamp==file_stamp(path):self.ready.emit(path,(stamp,blob))
                except Exception:self.failed.emit(path)
            # Only derived thumbnail rows are evicted; 256 MiB disk budget.
            total=db.execute('SELECT coalesce(sum(length(thumbnail)),0) FROM large_thumbnails').fetchone()[0]
            if total>256*1024**2:
                with db:
                    for path,size in db.execute('SELECT path,length(thumbnail) FROM large_thumbnails ORDER BY used').fetchall():
                        if total<=240*1024**2:break
                        db.execute('DELETE FROM large_thumbnails WHERE path=?',(path,));total-=size

class LargeThumbnails(QObject):
    def __init__(self,view):
        super().__init__(view);self.view=view;self.cache=OrderedDict();self.pending=OrderedDict();self.failed=set();self.job=None;self.paused=False
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.start)
    def get(self,path):
        if path in self.cache:self.cache.move_to_end(path);return self.cache[path]
        if self.paused or path in self.failed:return None
        if not self.job or path not in self.job.paths:self.pending[path]=None
        while len(self.pending)>256:self.pending.popitem(last=False)
        if not self.job:self.timer.start(20)
        return None
    def start(self):
        if self.paused or self.job or not self.pending:return
        paths=[self.pending.popitem(last=False)[0] for _ in range(min(8,len(self.pending)))]
        job=ThumbnailJob(self.view.database,paths,self);self.job=job
        if self.view.owner:self.view.owner.jobs.append(job)
        job.ready.connect(self.ready);job.failed.connect(self.failed.add)
        def finish():
            if self.view.owner:self.view.owner.jobs.remove(job)
            self.job=None;job.deleteLater()
            if not self.paused:self.timer.start(10)
        job.finished.connect(finish);job.start()
    def ready(self,path,payload):
        if self.paused:return
        stamp,blob=payload
        if self.view.owner and self.view.owner.index_stamps.get(path)!=stamp:return
        self.cache[path]=blob
        while len(self.cache)>64:self.cache.popitem(last=False)
        self.view.records.icons.pop(path,None)
        item=self.view.owner.library_items.get(path) if self.view.owner else next((i for i in self.view.records.rows if i.path==path),None)
        if item:
            index=self.view.records.index(item.position);self.view.records.dataChanged.emit(index,index)
    def invalidate(self,path):self.cache.pop(path,None);self.failed.discard(path)
    def pause(self):
        self.paused=True;self.timer.stop();self.pending.clear()
        if self.job:self.job.requestInterruption()
    def resume(self):self.paused=False;self.view.records.icons.clear();self.view.viewport().update()
