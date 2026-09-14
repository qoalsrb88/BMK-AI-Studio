"""Focused editors, independent of the main application window."""
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt,QThread,Signal,QRectF
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSlider,
    QGraphicsView,QGraphicsScene,QSpinBox,QComboBox,QDialogButtonBox,QPlainTextEdit,
    QListWidget,QListWidgetItem,QSplitter,QWidget)
from .core import resize_image,tone_delta,apply_tone_delta
from .appearance import CANVAS

def line(*widgets):
    widget=QWidget();layout=QHBoxLayout(widget);layout.setContentsMargins(0,0,0,0)
    for w in widgets:layout.addWidget(w)
    return widget

class ImageCanvas(QGraphicsView):
    def __init__(self):
        super().__init__();self.setScene(QGraphicsScene(self));self.setBackgroundBrush(QColor(CANVAS))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
    def display(self,image,fit=False):
        self.scene().clear();self.scene().addPixmap(QPixmap.fromImage(ImageQt(image.convert('RGBA'))))
        self.scene().setSceneRect(QRectF(0,0,*image.size))
        if fit:self.fitInView(self.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def wheelEvent(self,event):self.scale(*([1.2 if event.angleDelta().y()>0 else 1/1.2]*2))

class CompareDialog(QDialog):
    def __init__(self,before,after,parent=None):
        super().__init__(parent);self.setWindowTitle('전후 비교 · 왼쪽 원본 / 오른쪽 작업본');self.resize(1100,850)
        self.before=before.copy();self.before.thumbnail((1200,900))
        self.after=resize_image(after,*self.before.size,'contain',background='#17212b')
        layout=QVBoxLayout(self)
        text='같은 위치를 슬라이더로 비교합니다. 휠 확대 / 드래그 이동.'
        if before.size!=after.size:text+=' 크기가 다른 작업본은 비율을 유지해 화면에 맞춥니다.'
        layout.addWidget(QLabel(text));self.canvas=ImageCanvas();layout.addWidget(self.canvas,1)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,100);self.slider.setValue(50);self.slider.valueChanged.connect(self.render)
        layout.addWidget(line(QLabel('원본'),self.slider,QLabel('작업본')))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        self.render();self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def render(self,*args):
        output=self.before.copy().convert('RGBA');x=round(output.width*self.slider.value()/100)
        output.paste(self.after.crop((x,0,output.width,output.height)),(x,0))
        self.canvas.display(output)
    def showEvent(self,event):
        super().showEvent(event);self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

class ResizeDialog(QDialog):
    def __init__(self,image,parent=None):
        super().__init__(parent);self.setWindowTitle('출력 규격 · 비율과 크기');self.resize(820,780);self.image=image
        layout=QVBoxLayout(self);self.presets=QComboBox();self.presets.addItems(['직접 입력','1024 × 1024','832 × 1216','1216 × 832','1920 × 1080','1080 × 1920'])
        self.width=QSpinBox();self.height=QSpinBox()
        for w,value in ((self.width,image.width),(self.height,image.height)):w.setRange(1,32768);w.setValue(value)
        self.mode=QComboBox();self.mode.addItem('전체 유지 + 여백','contain');self.mode.addItem('가운데 크롭으로 채우기','cover');self.mode.addItem('지정 크기로 늘리기','stretch')
        self.background=QComboBox();self.background.addItems(['white','black','transparent'])
        layout.addWidget(self.presets);layout.addWidget(line(QLabel('너비'),self.width,QLabel('높이'),self.height));layout.addWidget(line(self.mode,self.background))
        self.canvas=ImageCanvas();layout.addWidget(self.canvas,1);self.message=QLabel('');layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('적용');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.presets.currentIndexChanged.connect(self.preset)
        self.width.valueChanged.connect(self.preview);self.height.valueChanged.connect(self.preview);self.mode.currentIndexChanged.connect(self.preview);self.background.currentIndexChanged.connect(self.preview)
        self.preview()
    def preset(self,index):
        if index:
            w,h=map(int,self.presets.currentText().split(' × '));self.width.setValue(w);self.height.setValue(h)
    def settings(self):return self.width.value(),self.height.value(),self.mode.currentData(),self.background.currentText()
    def preview(self,*args):
        w,h,mode,bg=self.settings();valid=w*h<=64_000_000;self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
        self.message.setText(f'{self.image.width} × {self.image.height} → {w} × {h} · {w*h/1e6:.2f} MP'+(' · 64 MP 제한 초과' if not valid else ''))
        scale=min(1,720/max(w,h));preview=resize_image(self.image,max(1,round(w*scale)),max(1,round(h*scale)),mode,bg)
        self.canvas.display(preview,True)
    def showEvent(self,event):super().showEvent(event);self.preview()

class MaskCanvas(ImageCanvas):
    def __init__(self,image,mask=None):
        super().__init__();self.original_size=image.size;self.image=image.copy();self.image.thumbnail((1024,1024))
        self.mask=mask.convert('L').resize(self.image.size) if mask else Image.new('L',self.image.size,255)
        self.brush=40;self.erase=False;self.last=None;self.undo_stack=[];self.render(True)
    def render(self,fit=False):
        overlay=Image.new('RGBA',self.image.size,'#4ae6c4');overlay.putalpha(self.mask.point(lambda x:round(x*.3)))
        self.display(Image.alpha_composite(self.image.convert('RGBA'),overlay),fit)
    def paint(self,point):
        p=(point.x(),point.y());radius=max(1,self.brush*self.image.width/self.original_size[0]/2)
        draw=ImageDraw.Draw(self.mask);value=0 if self.erase else 255
        if self.last is not None:draw.line([self.last,p],fill=value,width=max(1,round(radius*2)))
        draw.ellipse((p[0]-radius,p[1]-radius,p[0]+radius,p[1]+radius),fill=value);self.last=p;self.render()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.undo_stack.append(self.mask.copy());self.undo_stack=self.undo_stack[-10:];self.paint(self.mapToScene(event.position().toPoint()));return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.last is not None:self.paint(self.mapToScene(event.position().toPoint()));return
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.last=None;return
        super().mouseReleaseEvent(event)
    def fill(self,value):
        self.undo_stack.append(self.mask.copy());self.undo_stack=self.undo_stack[-10:];self.mask=Image.new('L',self.image.size,value);self.render()
    def undo(self):
        if self.undo_stack:self.mask=self.undo_stack.pop();self.render()
    def result(self):return self.mask.resize(self.original_size,Image.Resampling.BILINEAR)

class MaskDialog(QDialog):
    def __init__(self,image,mask=None,parent=None):
        super().__init__(parent);self.setWindowTitle('스티치 마스크 · 초록색 영역에 수정본 적용');self.resize(1000,850)
        layout=QVBoxLayout(self);layout.addWidget(QLabel('선택 영역만 합성합니다. 마스크가 전부 검정이면 원본을 유지합니다.'))
        self.canvas=MaskCanvas(image,mask);layout.addWidget(self.canvas,1)
        mode=QComboBox();mode.addItems(['선택 추가','선택 지우기']);mode.currentIndexChanged.connect(lambda i:setattr(self.canvas,'erase',bool(i)))
        brush=QSpinBox();brush.setRange(1,1000);brush.setValue(40);brush.valueChanged.connect(lambda v:setattr(self.canvas,'brush',v))
        full=QPushButton('전체 선택');full.clicked.connect(lambda:self.canvas.fill(255));clear=QPushButton('전체 지우기');clear.clicked.connect(lambda:self.canvas.fill(0));undo=QPushButton('획 취소');undo.clicked.connect(self.canvas.undo)
        layout.addWidget(line(mode,QLabel('브러시 px'),brush,full,clear,undo))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('마스크 적용');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
    def showEvent(self,event):super().showEvent(event);self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

class PreviewJob(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,image,reference,levels,luminance):
        super().__init__();self.image=image;self.reference=reference;self.levels=levels;self.luminance=luminance
    def run(self):
        try:
            before=self.image.copy();before.thumbnail((1024,1024))
            scale=self.image.width/before.width
            levels=max(1,self.levels-round(math.log2(scale)))
            delta=tone_delta(before,self.reference,levels,self.luminance)
            self.result.emit((before,delta))
        except Exception as exc:self.failed.emit(str(exc))

class ToneDialog(QDialog):
    def __init__(self,image,reference,strength,levels,luminance,parent=None):
        super().__init__(parent);self.setWindowTitle('톤 복원 미리보기');self.resize(1100,850);self.before=None;self.delta=None;self.closing=False
        layout=QVBoxLayout(self);self.status=QLabel('축소 미리보기 계산 중… 적용 시 원본 해상도로 다시 계산합니다.');layout.addWidget(self.status)
        self.canvas=ImageCanvas();layout.addWidget(self.canvas,1)
        self.strength=QSlider(Qt.Orientation.Horizontal);self.strength.setRange(0,200);self.strength.setValue(round(strength*100));self.value=QLabel(f'{strength:.2f}')
        self.split=QSlider(Qt.Orientation.Horizontal);self.split.setRange(0,100);self.split.setValue(50)
        layout.addWidget(line(QLabel('복원 강도'),self.strength,self.value));layout.addWidget(line(QLabel('원본'),self.split,QLabel('보정본')))
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False);self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setText('원본 해상도로 적용');self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.strength.valueChanged.connect(self.render);self.split.valueChanged.connect(self.render)
        self.job=PreviewJob(image,reference,levels,luminance);self.job.result.connect(self.ready);self.job.failed.connect(self.failed);self.job.start()
    def ready(self,result):
        if self.closing:return
        self.before,self.delta=result;self.render();self.canvas.fitInView(self.canvas.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
        self.status.setText('축소 미리보기 · 왼쪽 원본 / 오른쪽 보정본 · 적용 시 원본 해상도로 계산')
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True)
    def failed(self,message):self.status.setText('미리보기 실패: '+message)
    def render(self,*args):
        self.value.setText(f'{self.strength.value()/100:.2f}')
        if self.before is None:return
        corrected=apply_tone_delta(self.before,self.delta,self.strength.value()/100)
        x=round(self.before.width*self.split.value()/100);output=self.before.convert('RGBA').copy();output.paste(corrected.crop((x,0,corrected.width,corrected.height)),(x,0));self.canvas.display(output)
    def done(self,result):
        # Worker owns only a <=1024px preview calculation; retain dialog until it finishes.
        if self.job.isRunning():
            if self.closing:return
            self.closing=True;self.buttons.setEnabled(False)
            self.status.setText('미리보기 계산을 마무리한 뒤 닫습니다.')
            self.job.finished.connect(lambda:super(ToneDialog,self).done(result));return
        super().done(result)

class RevisionDialog(QDialog):
    def __init__(self,revisions,parent=None):
        super().__init__(parent);self.setWindowTitle('노트 버전 이력 · 복원 시 새 버전으로 기록');self.resize(1000,720);self.revision_id=None
        layout=QVBoxLayout(self);split=QSplitter();layout.addWidget(split,1)
        self.list=QListWidget();self.preview=QPlainTextEdit();self.preview.setReadOnly(True);split.addWidget(self.list);split.addWidget(self.preview);split.setSizes([300,700])
        for rev in revisions:
            item=QListWidgetItem(f'#{rev[0]} · {rev[1]}\n{rev[3]}');item.setData(Qt.ItemDataRole.UserRole,rev);self.list.addItem(item)
        self.list.currentItemChanged.connect(self.select)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.RestoreDefaults|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText('선택 버전 복원');buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        if self.list.count():self.list.setCurrentRow(0)
    def select(self,item,*args):
        if item:
            rev=item.data(Qt.ItemDataRole.UserRole);self.revision_id=rev[0];self.preview.setPlainText(rev[2])
