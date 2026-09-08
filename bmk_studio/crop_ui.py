"""Interactive crop overlay in image coordinates; never edits image pixels."""
import math
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPen,QPainterPath,QTransform

def snap_value(value,step):return int(math.floor(value/max(1,step)+.5)*max(1,step))

def bounded_box(box,size):
    x,y,w,h=map(lambda v:int(round(v)),box);iw,ih=map(int,size)
    w=max(1,min(iw,w));h=max(1,min(ih,h))
    return max(0,min(iw-w,x)),max(0,min(ih-h,y)),w,h

def anchored_box(anchor,point,size,ratio=0,step=1):
    iw,ih=size;ax,ay=anchor
    px=max(0,min(iw,snap_value(point[0],step)));py=max(0,min(ih,snap_value(point[1],step)))
    sx=-1 if px<ax else 1;sy=-1 if py<ay else 1
    available_w=iw-ax if sx>0 else ax;available_h=ih-ay if sy>0 else ay
    w=abs(px-ax);h=abs(py-ay)
    if ratio:
        w=max(w,h*ratio);h=w/ratio
        factor=min(1,available_w/max(w,1e-9),available_h/max(h,1e-9));w*=factor;h*=factor
    w=min(available_w,int(round(w)));h=min(available_h,int(round(h)))
    return int(ax if sx>0 else ax-w),int(ay if sy>0 else ay-h),int(w),int(h)

class CropInteraction:
    def init_crop(self):
        self.crop_rect=None;self.crop_drag=None;self.crop_snap=1;self.crop_space=False;self.crop_pan=None
        self.setMouseTracking(True)
    def set_crop_box(self,box):
        self.crop_rect=tuple(box) if box else None;self.viewport().update()
    def publish_crop(self,box):
        self.set_crop_box(box)
        if box and box[2]>=1 and box[3]>=1:self.cropChanged.emit(box)
    def crop_points(self):
        x,y,w,h=self.crop_rect
        return {'nw':(x,y),'ne':(x+w,y),'sw':(x,y+h),'se':(x+w,y+h)}
    def crop_hit(self,point):
        if not self.crop_rect:return None
        # Hit target remains 11 logical pixels regardless of image zoom/DPI.
        nearest=None;distance=12
        for name,xy in self.crop_points().items():
            mapped=self.mapFromScene(QPointF(*xy));d=math.hypot(mapped.x()-point.x(),mapped.y()-point.y())
            if d<distance:nearest=name;distance=d
        if nearest:return nearest
        if QRectF(*self.crop_rect).contains(self.mapToScene(point)):return 'move'
        return None
    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        if not self.crop_mode or not self.crop_rect or self.image_rect.isEmpty():return
        image=self.mapFromScene(self.image_rect).boundingRect().toRectF()
        crop=self.mapFromScene(QRectF(*self.crop_rect)).boundingRect().toRectF()
        painter.save();painter.setWorldTransform(QTransform())
        outside=QPainterPath();outside.setFillRule(Qt.FillRule.OddEvenFill);outside.addRect(image);outside.addRect(crop)
        painter.fillPath(outside,QColor(0,0,0,140))
        painter.setPen(QPen(QColor('#55b6ff'),1.5));painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRect(crop)
        painter.setPen(QPen(QColor(255,255,255,90),1))
        for i in (1,2):
            x=crop.x()+crop.width()*i/3;y=crop.y()+crop.height()*i/3
            painter.drawLine(QPointF(x,crop.top()),QPointF(x,crop.bottom()))
            painter.drawLine(QPointF(crop.left(),y),QPointF(crop.right(),y))
        painter.setPen(QPen(QColor('#15324a'),1));painter.setBrush(QColor('#70c3ff'))
        for xy in self.crop_points().values():
            point=self.mapFromScene(QPointF(*xy));painter.drawRect(QRectF(point.x()-4,point.y()-4,8,8))
        painter.restore()
    def mousePressEvent(self,event):
        if self.crop_mode and not self.image_rect.isEmpty():
            self.setFocus();position=event.position().toPoint()
            if event.button()==Qt.MouseButton.MiddleButton or (event.button()==Qt.MouseButton.LeftButton and self.crop_space):
                self.crop_pan=position;self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor);event.accept();return
            if event.button()==Qt.MouseButton.LeftButton:
                point=self.mapToScene(position);hit=None if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.crop_hit(position)
                if not hit and not self.image_rect.contains(point):event.accept();return
                before=self.crop_rect;step=1 if event.modifiers() & Qt.KeyboardModifier.AltModifier else self.crop_snap
                if hit=='move':
                    self.crop_drag={'mode':'move','offset':(point.x()-before[0],point.y()-before[1]),'before':before}
                else:
                    anchor=self.crop_points()[{'nw':'se','ne':'sw','sw':'ne','se':'nw'}[hit]] if hit else (max(0,min(int(self.image_rect.width()),snap_value(point.x(),step))),max(0,min(int(self.image_rect.height()),snap_value(point.y(),step))))
                    self.crop_drag={'mode':'resize' if hit else 'new','anchor':anchor,'before':before}
                self.viewport().setCursor(Qt.CursorShape.SizeAllCursor if hit=='move' else Qt.CursorShape.CrossCursor)
                event.accept();return
        super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        position=event.position().toPoint()
        if self.crop_pan is not None:
            delta=position-self.crop_pan;self.crop_pan=position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x());self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y());event.accept();return
        if self.crop_mode:
            if self.crop_drag:
                point=self.mapToScene(position);step=1 if event.modifiers() & Qt.KeyboardModifier.AltModifier else self.crop_snap
                size=(int(self.image_rect.width()),int(self.image_rect.height()));drag=self.crop_drag
                if drag['mode']=='move':
                    x=snap_value(point.x()-drag['offset'][0],step);y=snap_value(point.y()-drag['offset'][1],step)
                    box=bounded_box((x,y,*drag['before'][2:]),size)
                else:box=anchored_box(drag['anchor'],(point.x(),point.y()),size,self.ratio,step)
                if box[2]>=1 and box[3]>=1:self.publish_crop(box)
                event.accept();return
            hit=self.crop_hit(position)
            cursor=Qt.CursorShape.OpenHandCursor if self.crop_space else Qt.CursorShape.SizeAllCursor if hit=='move' else Qt.CursorShape.SizeFDiagCursor if hit in ('nw','se') else Qt.CursorShape.SizeBDiagCursor if hit else Qt.CursorShape.CrossCursor
            self.viewport().setCursor(cursor)
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.crop_pan is not None and event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.MiddleButton):
            self.crop_pan=None;self.viewport().setCursor(Qt.CursorShape.CrossCursor);event.accept();return
        if self.crop_drag and event.button()==Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event);self.crop_drag=None;event.accept();return
        super().mouseReleaseEvent(event)
    def keyPressEvent(self,event):
        if self.crop_mode:
            if event.key()==Qt.Key.Key_Space:self.crop_space=True;self.viewport().setCursor(Qt.CursorShape.OpenHandCursor);event.accept();return
            if event.key()==Qt.Key.Key_Escape and self.crop_drag:
                before=self.crop_drag['before'];self.crop_drag=None
                if before:self.publish_crop(before)
                else:
                    self.cropChanged.emit((0,0,int(self.image_rect.width()),int(self.image_rect.height())));self.set_crop_box(None)
                event.accept();return
            directions={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}
            if self.crop_rect and event.key() in directions:
                dx,dy=directions[event.key()];step=self.crop_snap*(10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)
                x,y,w,h=self.crop_rect;self.publish_crop(bounded_box((x+dx*step,y+dy*step,w,h),(self.image_rect.width(),self.image_rect.height())));event.accept();return
        super().keyPressEvent(event)
    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Space and not event.isAutoRepeat():self.crop_space=False;self.viewport().unsetCursor()
        super().keyReleaseEvent(event)
    def focusOutEvent(self,event):
        self.crop_space=False;self.crop_pan=None;self.crop_drag=None
        super().focusOutEvent(event)
