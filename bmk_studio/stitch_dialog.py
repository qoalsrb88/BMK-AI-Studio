"""Bounded asynchronous preview; full-resolution rendering belongs to the caller."""
from PIL import Image
from PySide6.QtCore import QThread,Signal,QTimer,Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QSpinBox,QDoubleSpinBox,QDialogButtonBox,QSlider
from .dialogs import ImageCanvas,line
from .core import stitch_image

class StitchPreview(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,base,patch,mask,ctx,settings):
        super().__init__();self.base=base;self.patch=patch;self.mask=mask;self.ctx=ctx;self.settings=settings
    def run(self):
        try:
            ratio=min(1,900/max(self.base.size));base=self.base.copy();base.thumbnail((900,900))
            rotated=base.rotate(-self.ctx['rotation'],expand=True)
            x,y,w,h=self.ctx['box'];x=min(round(x*ratio),rotated.width-1);y=min(round(y*ratio),rotated.height-1)
            w=min(max(1,round(w*ratio)),rotated.width-x);h=min(max(1,round(h*ratio)),rotated.height-y)
            dx,dy,angle,scale,feather=self.settings
            output=stitch_image(base,self.patch,(x,y,w,h),self.ctx['rotation'],feather*ratio,self.mask,(dx*ratio,dy*ratio),angle,scale)
            self.result.emit((base,output))
        except Exception as exc:self.failed.emit(str(exc))

class StitchDialog(QDialog):
    def __init__(self,base,patch,mask,ctx,feather,parent=None):
        super().__init__(parent);self.setWindowTitle('스티치 위치·회전·크기 조정');self.resize(1050,850)
        self.base=base;self.patch=patch;self.mask=mask;self.ctx=ctx;self.job=None;self.closing=None;self.latest=None
        layout=QVBoxLayout(self);layout.addWidget(QLabel('크롭 중심 기준 · X/Y는 원본 픽셀 · 각도는 시계 방향 · 캔버스 밖은 잘립니다.'))
        self.dx=QSpinBox();self.dy=QSpinBox()
        for widget in (self.dx,self.dy):widget.setRange(-32768,32768)
        self.angle=QDoubleSpinBox();self.angle.setRange(-180,180);self.angle.setSingleStep(.1);self.angle.setSuffix('°')
        self.scale=QDoubleSpinBox();self.scale.setRange(.1,4);self.scale.setValue(1);self.scale.setSingleStep(.01)
        self.feather=QSpinBox();self.feather.setRange(0,512);self.feather.setValue(feather)
        layout.addWidget(line(QLabel('X'),self.dx,QLabel('Y'),self.dy,QLabel('각도'),self.angle,QLabel('배율'),self.scale,QLabel('페더'),self.feather))
        self.canvas=ImageCanvas();layout.addWidget(self.canvas,1)
        self.split=QSlider(Qt.Orientation.Horizontal);self.split.setRange(0,100);self.split.setValue(50)
        layout.addWidget(line(QLabel('원본'),self.split,QLabel('합성')));self.split.valueChanged.connect(self.render)
        self.message=QLabel('미리보기 계산 중…');layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('원본 해상도로 적용');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(120);self.timer.timeout.connect(self.refresh)
        for widget in (self.dx,self.dy,self.angle,self.scale,self.feather):widget.valueChanged.connect(self.changed)
        self.changed()
    def settings(self):return (self.dx.value(),self.dy.value(),self.angle.value(),self.scale.value(),self.feather.value())
    def changed(self,*args):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False);self.timer.start()
    def refresh(self):
        if self.job or self.closing is not None:return
        settings=self.settings();job=StitchPreview(self.base,self.patch,self.mask,self.ctx,settings);self.job=job
        def ready(result):
            if self.closing is None and settings==self.settings():
                self.latest=result;self.render();self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
                self.message.setText('축소 미리보기입니다. 적용 시 원본 해상도로 계산합니다.')
                self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        def failed(message):self.message.setText(message)
        def finished():
            self.job=None
            if self.closing is not None:super(StitchDialog,self).done(self.closing)
            elif settings!=self.settings():self.timer.start()
        job.result.connect(ready);job.failed.connect(failed);job.finished.connect(finished);job.start()
    def render(self,*args):
        if not self.latest:return
        before,after=self.latest;output=before.convert('RGBA');x=round(output.width*self.split.value()/100)
        output.paste(after.crop((x,0,after.width,after.height)),(x,0));self.canvas.display(output)
    def done(self,result):
        self.timer.stop()
        if self.job:
            self.closing=result;self.setEnabled(False);return
        super().done(result)
