"""Cancellable batches. SQLite connections and hashing live on the worker thread."""
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from .core import Store, fingerprint, file_stamp
from .tagger import inference_signature

class BatchTagJob(QThread):
    item_ready=Signal(object)
    item_failed=Signal(str,str)
    progress=Signal(int,int)
    summary=Signal(object)

    def __init__(self,paths,model_dir,tagger,root,batch_size=4):
        super().__init__()
        self.paths=list(dict.fromkeys(str(Path(p).resolve()) for p in paths))
        self.model_dir=model_dir;self.tagger=tagger;self.root=root
        self.precision=getattr(tagger,'precision','fp32')
        self.batch_size=max(1,min(16,int(batch_size)))
        self.stats={'completed':0,'cached':0,'failed':0,'cancelled':False,'total':len(self.paths)}

    def cancel(self):self.requestInterruption()

    def run(self):
        store=Store(self.root)
        try:
            signature=inference_signature(self.model_dir,self.precision)
            pending=[]
            for path in self.paths:
                if self.isInterruptionRequested():break
                try:
                    stamp=file_stamp(path)
                    digest=fingerprint(path)
                    if stamp!=file_stamp(path):raise ValueError('파일을 읽는 중 내용이 변경되었습니다.')
                    key=digest+'|wd-v3-'+self.precision+'-1|'+signature
                    cached=store.cache(key)
                    if cached:self._accept(store,path,stamp,key,cached,signature,True)
                    else:pending.append((path,stamp,key))
                except Exception as exc:self._error(path,exc)
                if len(pending)>=self.batch_size:
                    self._infer(store,pending,signature);pending=[]
            if pending and not self.isInterruptionRequested():self._infer(store,pending,signature)
        except Exception as exc:
            self.item_failed.emit('모델 / 작업',str(exc))
            self.stats['fatal']=str(exc)
        finally:
            self.stats['cancelled']=self.isInterruptionRequested()
            store.db.close();self.summary.emit(dict(self.stats))

    def _error(self,path,exc):
        self.stats['failed']+=1;self.item_failed.emit(path,str(exc));self._progress()

    def _progress(self):self.progress.emit(self.stats['completed']+self.stats['failed'],len(self.paths))

    def _accept(self,store,path,stamp,key,result,signature,cached=False):
        if file_stamp(path)!=stamp:raise ValueError('추론 중 이미지가 변경되어 결과를 저장하지 않았습니다.')
        store.record_tag_run(path,signature,stamp,key,result)
        self.stats['completed']+=1
        if cached:self.stats['cached']+=1
        self.item_ready.emit({'path':path,'stamp':stamp,'model_signature':signature,'result':result,'cached':cached})
        self._progress()

    def _infer(self,store,pending,signature):
        if self.isInterruptionRequested():return
        try:
            if inference_signature(self.model_dir,self.precision)!=signature:raise ValueError('작업 중 모델 파일이 변경되었습니다.')
            outputs=self.tagger.run_many([p[0] for p in pending],self.model_dir)
            if len(outputs)!=len(pending):raise ValueError('모델 출력 이미지 수가 일치하지 않습니다.')
            if inference_signature(self.model_dir,self.precision)!=signature:raise ValueError('추론 중 모델 파일이 변경되었습니다.')
        except Exception as exc:
            # A bad file or oversized GPU batch must not discard healthy neighbours.
            if len(pending)>1:
                for item in pending:
                    if self.isInterruptionRequested():break
                    self._infer(store,[item],signature)
            else:self._error(pending[0][0],exc)
            return
        for (path,stamp,key),result in zip(pending,outputs):
            try:self._accept(store,path,stamp,key,result,signature)
            except Exception as exc:self._error(path,exc)
