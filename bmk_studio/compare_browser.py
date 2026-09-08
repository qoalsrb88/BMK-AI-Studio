"""Read-only A/B originals with normalized, synchronized pan and zoom."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QCheckBox,QSplitter,QPlainTextEdit,QDialogButtonBox
from .dialogs import ImageCanvas

class CompareCanvas(ImageCanvas):
    changed=Signal()
    def wheelEvent(self,event):
        scale=self.transform().m11()
        if (event.angleDelta().y()>0 and scale<32) or (event.angleDelta().y()<0 and scale>.02):super().wheelEvent(event)
        self.changed.emit()

class BrowserCompareDialog(QDialog):
    def __init__(self,a,b,parent=None):
        super().__init__(parent);self.setWindowTitle('A/B 원본 비교 · 생성 정보 차이');self.resize(1200,850);self.syncing=False
        layout=QVBoxLayout(self);self.sync=QCheckBox('확대·이동 동기화 · 이미지 너비와 중심의 상대 위치 기준');self.sync.setChecked(True);layout.addWidget(self.sync)
        label=QLabel(f'A: {Path(a[0]).name}    /    B: {Path(b[0]).name}\n원본 읽기 전용 · 비교 미리보기 최대 2048px · 비율이 다른 이미지는 상대 위치를 맞춥니다.');label.setWordWrap(True);layout.addWidget(label)
        split=QSplitter();layout.addWidget(split,3);self.canvases=[]
        for path,info,image in (a,b):
            canvas=CompareCanvas();canvas.display(image);split.addWidget(canvas);self.canvases.append(canvas)
            canvas.changed.connect(lambda c=canvas:self.synchronize(c))
            for bar in (canvas.horizontalScrollBar(),canvas.verticalScrollBar()):bar.valueChanged.connect(lambda value,c=canvas:self.synchronize(c))
        text=QPlainTextEdit();text.setReadOnly(True);text.setMaximumHeight(240);layout.addWidget(text,1)
        left,right=a[1],b[1];differences=[]
        for name in ('positive','negative','source','size','settings','branches'):
            av,bv=left.get(name),right.get(name)
            if av!=bv:
                render=lambda value:json.dumps(value,ensure_ascii=False,indent=2) if value else '정보 없음'
                differences.append(f'[{name}]\nA: {render(av)}\nB: {render(bv)}')
        text.setPlainText('\n\n'.join(differences) or '비교한 생성 정보가 같습니다. 정보가 없는 경우에도 동일하게 표시됩니다.')
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def showEvent(self,event):
        super().showEvent(event);self.syncing=True
        for canvas in self.canvases:canvas.fitInView(canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
        self.syncing=False
    def synchronize(self,source):
        if self.syncing or not self.sync.isChecked() or len(self.canvases)<2:return
        self.syncing=True
        try:
            target=next(c for c in self.canvases if c is not source);a=source.sceneRect();b=target.sceneRect()
            if a.isEmpty() or b.isEmpty():return
            center=source.mapToScene(source.viewport().rect().center());transform=source.transform()
            factor=a.width()/b.width();transform.scale(factor,factor);target.setTransform(transform)
            target.centerOn(center.x()/a.width()*b.width(),center.y()/a.height()*b.height())
        finally:self.syncing=False
