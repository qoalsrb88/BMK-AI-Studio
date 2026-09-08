"""Background indexing and stable-file discovery. Source files are read-only."""
from pathlib import Path
import io
import time
from PySide6.QtCore import QThread, Signal
from PIL import Image, ImageOps
from .core import EXTENSIONS, Store, inspect_image, json_text, file_stamp, load_image
from .color import high_precision

def folder_snapshot(folder):
    result={}
    for path in Path(folder).iterdir():
        if path.suffix.lower() not in EXTENSIONS or not path.is_file():continue
        try:result[str(path.resolve())]=file_stamp(path)
        except OSError:continue
    return result

class StableFiles:
    """Only announce a changed file after its size/mtime stayed stable."""
    def __init__(self, baseline=None, settle_seconds=2.0):
        self.accepted=dict(baseline or {})
        self.pending={}
        self.settle_seconds=settle_seconds
    def update(self, snapshot, now):
        ready=[]
        self.accepted={p:s for p,s in self.accepted.items() if p in snapshot}
        self.pending={p:v for p,v in self.pending.items() if p in snapshot}
        for path,stamp in snapshot.items():
            if self.accepted.get(path)==stamp:
                self.pending.pop(path,None);continue
            old=self.pending.get(path)
            if old is None or old[0]!=stamp:self.pending[path]=(stamp,now)
            elif now-old[1]>=self.settle_seconds:
                ready.append(path);self.accepted[path]=stamp;self.pending.pop(path,None)
        return ready

class IndexJob(QThread):
    indexed=Signal(object)
    failed_item=Signal(str,str)
    def __init__(self, paths, root):
        super().__init__();self.paths=list(paths);self.root=root
    def run(self):
        store=Store(self.root)
        try:
            for source in self.paths:
                if self.isInterruptionRequested():break
                path=Path(source).resolve()
                try:
                    stamp=file_stamp(path)
                    record=inspect_image(path)
                    if high_precision(path):thumb=load_image(path)
                    else:
                        with Image.open(path) as im:
                            im.draft('RGB',(128,128));thumb=ImageOps.exif_transpose(im).convert('RGBA')
                    thumb.thumbnail((160,160));buf=io.BytesIO();thumb.save(buf,format='PNG')
                    if stamp!=file_stamp(path):raise ValueError('읽는 중 파일이 변경되었습니다.')
                    searchable=(path.name+'\n'+json_text(record)).casefold()
                    blob=buf.getvalue()
                    store.index_image(path,stamp,searchable,blob)
                    self.indexed.emit((str(path),stamp,searchable,blob))
                except Exception as exc:self.failed_item.emit(str(path),str(exc))
        finally:store.db.close()

class FolderWatch(QThread):
    discovered=Signal(object)
    failed=Signal(str)
    def __init__(self,folder,interval=1.0,settle_seconds=2.0):
        super().__init__();self.folder=folder;self.interval=interval;self.settle_seconds=settle_seconds
    def run(self):
        try:
            # Include files arriving just before startup; existing rows deduplicate in the UI.
            stable=StableFiles(settle_seconds=self.settle_seconds)
            while not self.isInterruptionRequested():
                ready=stable.update(folder_snapshot(self.folder),time.monotonic())
                if ready:self.discovered.emit(ready)
                slices=max(1,int(self.interval/.1))
                for _ in range(slices):
                    if self.isInterruptionRequested():return
                    self.msleep(100)
        except Exception as exc:self.failed.emit(str(exc))
