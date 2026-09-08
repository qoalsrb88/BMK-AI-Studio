"""Named, cooperatively cancelled jobs with shared progress reporting."""
from PySide6.QtCore import QThread,Signal,QTimer,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTreeWidget,QTreeWidgetItem,QPushButton,QLabel,QHeaderView

class ManagedJob(QThread):
    result=Signal(object);failed=Signal(str);progress=Signal(object)
    def __init__(self,title,fn,parent=None):
        super().__init__(parent);self.title=title;self.fn=fn;self.detail='대기';self.cancel_allowed=True;self.outcome='진행 중'
        self.progress.connect(self.set_progress)
    def set_progress(self,value):
        done,total,label=value;self.detail=f'{done} / {total} · {label}'
    def run(self):
        try:
            value=self.fn(self);self.outcome='취소됨' if self.isInterruptionRequested() else '완료';self.result.emit(value)
        except Exception as exc:self.outcome='취소됨' if self.isInterruptionRequested() else '실패';self.failed.emit(str(exc))

class JobCenter(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.setWindowTitle('작업 목록 / 안전하게 취소');self.resize(700,430)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('취소는 현재 파일·추론 배치 처리를 마친 뒤 적용됩니다. 저장·내보내기는 완료를 기다립니다.'))
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['작업','상태']);layout.addWidget(self.tree)
        self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents);self.tree.header().setStretchLastSection(True)
        cancel=QPushButton('선택 작업 취소');cancel.clicked.connect(self.cancel);layout.addWidget(cancel)
        self.timer=QTimer(self);self.timer.setInterval(300);self.timer.timeout.connect(self.refresh);self.timer.start();self.refresh()
    def done(self,result):self.timer.stop();super().done(result)
    def jobs(self):return list(dict.fromkeys(self.studio.jobs+self.studio.findChildren(QThread)))
    def refresh(self):
        selected=self.tree.currentItem();selected_id=selected.data(0,Qt.ItemDataRole.UserRole) if selected else None;self.tree.clear()
        names={'IndexJob':'이미지 색인','SearchJob':'이미지 검색','BatchTagJob':'일괄 태깅','FolderWatch':'폴더 감시','ModelJob':'모델 다운로드','ThumbnailJob':'큰 썸네일','Job':'이미지 처리 / 저장'}
        for job in self.jobs():
            if not job.isRunning():continue
            item=QTreeWidgetItem([getattr(job,'title',names.get(type(job).__name__,'백그라운드 작업')),getattr(job,'detail','처리 중')]);item.setData(0,Qt.ItemDataRole.UserRole,id(job));self.tree.addTopLevelItem(item)
            if selected_id==id(job):self.tree.setCurrentItem(item)
        for title,outcome in getattr(self.studio,'completed_jobs',[])[-15:]:self.tree.addTopLevelItem(QTreeWidgetItem([title,outcome]))
    def cancel(self):
        item=self.tree.currentItem()
        if not item:return
        for job in self.jobs():
            if id(job)!=item.data(0,Qt.ItemDataRole.UserRole):continue
            if getattr(job,'cancel_allowed',False) or type(job).__name__ in ('IndexJob','SearchJob','BatchTagJob','FolderWatch','ModelJob','ThumbnailJob'):
                if job is self.studio.watch_job:self.studio.watch_toggle.setChecked(False)
                elif job is self.studio.batch_job:self.studio.cancel_tags()
                elif job is self.studio.index_job:
                    self.studio.index_cancelled=True;self.studio.pending_index.clear();job.requestInterruption()
                elif type(job).__name__=='ThumbnailJob':self.studio.library.large.pause()
                else:job.requestInterruption()
                item.setText(1,'취소 요청됨')
            else:item.setText(1,'안전한 완료를 기다리는 작업입니다')
