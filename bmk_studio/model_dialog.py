from pathlib import Path
from PySide6.QtCore import QThread,Signal,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QPushButton,QProgressBar
from .model_download import MODELS,official_manifest,install_model,DownloadCancelled

class ModelJob(QThread):
    result=Signal(object);failed=Signal(str);progress=Signal(object)
    def __init__(self,repo,folder,manifest=None,parent=None):
        super().__init__(parent);self.repo=repo;self.folder=folder;self.manifest=manifest
    def run(self):
        try:
            result=official_manifest(self.repo) if self.manifest is None else install_model(self.folder,self.manifest,self.isInterruptionRequested,self.progress.emit)
            if self.isInterruptionRequested() and self.manifest is None:raise DownloadCancelled('모델 정보 조회를 취소했습니다.')
            self.result.emit(result)
        except Exception as exc:self.failed.emit(str(exc))

class ModelDownloadDialog(QDialog):
    def __init__(self,folder,parent=None):
        super().__init__(parent);self.folder=Path(folder);self.manifest=None;self.job=None;self.installed=None
        self.setWindowTitle('WD v3 모델 다운로드');self.resize(640,320);layout=QVBoxLayout(self)
        self.choice=QComboBox()
        for label,repo in MODELS.items():self.choice.addItem(label,repo)
        layout.addWidget(self.choice);self.choice.currentIndexChanged.connect(self.reset_manifest)
        layout.addWidget(QLabel('공식 Hugging Face 저장소에서 익명으로 내려받습니다. 모델 카드에서 이용 조건을 확인하세요.'))
        self.status=QLabel('정보 확인으로 다운로드 크기와 리비전을 먼저 확인하세요.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,1000);layout.addWidget(self.progress)
        row=QHBoxLayout();self.info=QPushButton('정보 확인');self.download=QPushButton('다운로드 / 이어받기');self.download.setEnabled(False)
        self.cancel=QPushButton('취소');self.cancel.setEnabled(False);row.addWidget(self.info);row.addWidget(self.download);row.addWidget(self.cancel);layout.addLayout(row)
        self.info.clicked.connect(lambda:self.start(False));self.download.clicked.connect(lambda:self.start(True));self.cancel.clicked.connect(self.cancel_job)
        card=QPushButton('공식 모델 카드 / 이용 조건');card.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://huggingface.co/'+self.choice.currentData())));layout.addWidget(card)
        self.use=QPushButton('설치한 모델 사용');self.use.setEnabled(False);self.use.clicked.connect(self.accept);layout.addWidget(self.use)
        layout.addWidget(QLabel('설치 위치: '+str(self.folder)))
    def reset_manifest(self,*args):self.manifest=None;self.installed=None;self.download.setEnabled(False);self.use.setEnabled(False)
    def start(self,download):
        if self.job:return
        self.info.setEnabled(False);self.download.setEnabled(False);self.choice.setEnabled(False);self.cancel.setEnabled(True);self.use.setEnabled(False);self.progress.setRange(0,0)
        self.status.setText('검증된 파일을 확인하고 있습니다…' if download else '공식 모델 정보를 확인하고 있습니다…')
        job=ModelJob(self.choice.currentData(),self.folder,self.manifest if download else None,self);self.job=job
        owner=self.parent()
        if hasattr(owner,'jobs'):owner.jobs.append(job)
        job.progress.connect(self.show_progress);job.failed.connect(self.status.setText)
        def result(value):
            if isinstance(value,dict):
                self.manifest=value;size=sum(file['size'] for file in value['files'])/1024**3
                self.status.setText(f'{size:.2f} GB · 리비전 {value["revision"][:12]} · 기존 모델 폴더는 유지합니다.')
            else:self.installed=value;self.status.setText('설치 및 무결성 검증 완료: '+value)
        def finish():
            if hasattr(owner,'jobs'):owner.jobs.remove(job)
            self.job=None;self.info.setEnabled(True);self.choice.setEnabled(True);self.download.setEnabled(self.manifest is not None);self.cancel.setEnabled(False);self.use.setEnabled(self.installed is not None)
            self.progress.setRange(0,1000)
            if self.installed:self.progress.setValue(1000)
        job.result.connect(result);job.finished.connect(finish);job.start()
    def show_progress(self,payload):
        self.progress.setRange(0,1000);self.progress.setValue(int(payload['done']/max(1,payload['total'])*1000))
        self.status.setText(f'{payload["file"]} · {payload["done"]/1024**2:.1f} / {payload["total"]/1024**2:.1f} MB')
    def cancel_job(self):
        if self.job:self.job.requestInterruption();self.status.setText('취소 요청 · 진행 중인 네트워크 읽기가 끝나면 정지합니다.');self.cancel.setEnabled(False)
    def reject(self):
        if self.job:self.cancel_job();return
        super().reject()
    def closeEvent(self,event):
        if self.job:self.cancel_job();event.ignore()
        else:super().closeEvent(event)
