"""Real mouse crop UX, reverse numeric sync, overlay, undo, original preservation."""
import os,sys,tempfile,time
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-crop-'));source=root/'image.png'
pixels=np.zeros((400,512,3),dtype=np.uint8);pixels[:]=(210,180,140);pixels[150:250,200:300]=(120,200,240)
Image.fromarray(pixels).save(source);before=fingerprint(source)
w=Studio(root/'data');w.show();w.add_paths([source]);w.tabs.setCurrentIndex(3)
end=time.monotonic()+20
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
v=w.viewer;w.crop_toggle.setChecked(True);app.processEvents();v.actual_size();app.processEvents()
# Entering work mode schedules fit; exact pixel assertions require 100% after that fit.
def pos(x,y):return v.mapFromScene(QPointF(x,y))
def drag(a,b,modifier=Qt.KeyboardModifier.NoModifier,live=None):
    QTest.mousePress(v.viewport(),Qt.MouseButton.LeftButton,modifier,pos(*a));QTest.mouseMove(v.viewport(),pos(*b));app.processEvents()
    if live:live()
    QTest.mouseRelease(v.viewport(),Qt.MouseButton.LeftButton,modifier,pos(*b));app.processEvents()
drag((64,64),(320,288),live=lambda:(_ for _ in ()).throw(AssertionError('Not live')) if w.box!=(64,64,256,224) else None)
assert w.box==(64,64,256,224)==v.crop_rect
drag((200,180),(216,196));assert w.box==(80,80,256,224)
for name,target,expected in [('nw',(64,48),(64,48,272,256)),('ne',(352,48),(80,48,272,256)),('sw',(64,320),(64,80,272,240)),('se',(352,320),(80,80,272,240))]:
    w.set_box((80,80,256,224));start=v.crop_points()[name];drag(start,target);assert w.box==expected,(name,w.box)
w.set_box((80,80,256,224));QTest.mousePress(v.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,pos(180,180));QTest.mouseMove(v.viewport(),pos(210,210));QTest.keyClick(v,Qt.Key.Key_Escape);QTest.mouseRelease(v.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,pos(210,210));assert w.box==(80,80,256,224)
w.crop_snap.setCurrentIndex(w.crop_snap.findData(16));drag((180,180),(200,190));assert w.box==(96,96,256,224)
w.coords[0].setValue(121);assert w.box[0]==128 and v.crop_rect==w.box
w.ratio.setCurrentText('4:3');drag(v.crop_points()['se'],(510,390));assert abs(w.box[2]-w.box[3]*4/3)<=1
assert w.box[0]+w.box[2]<=512 and w.box[1]+w.box[3]<=400
w.ratio.setCurrentText('자유');w.set_box((64,64,256,224))
QTest.keyClick(v,Qt.Key.Key_Right);assert w.box[0]==80
# Dim only outside the crop; frame does not tint its interior.
app.processEvents();on=v.viewport().grab().toImage();outside=pos(30,30);inside=pos(150,130)
w.crop_toggle.setChecked(False);app.processEvents();off=v.viewport().grab().toImage()
assert on.pixelColor(outside).red()<off.pixelColor(outside).red()*.6
assert on.pixelColor(inside)==off.pixelColor(inside)
w.crop_toggle.setChecked(True);v.scale(2,2);v.centerOn(QPointF(200,180));app.processEvents()
corner=v.crop_points()['nw'];p=pos(*corner);assert v.crop_hit(p+QPoint(7,0))=='nw';assert v.crop_hit(p+QPoint(-15,-15))!='nw'
# Panning must leave image-coordinate crop unchanged.
box=w.box;start=QPoint(180,180);QTest.mousePress(v.viewport(),Qt.MouseButton.MiddleButton,Qt.KeyboardModifier.NoModifier,start);QTest.mouseMove(v.viewport(),start+QPoint(20,20));QTest.mouseRelease(v.viewport(),Qt.MouseButton.MiddleButton,Qt.KeyboardModifier.NoModifier,start+QPoint(20,20));assert w.box==box
v.fit();w.set_box((64,64,256,224));app.processEvents()
out=Path(sys.argv[1]) if len(sys.argv)>1 else root/'preview.png';w.grab().save(str(out))
w.apply_crop();np.testing.assert_array_equal(np.asarray(w.current)[:,:,:3],pixels[64:288,64:320])
assert w.box==(0,0,256,224)
w.crop_toggle.setChecked(True);assert v.crop_rect is None
w.crop_toggle.setChecked(False);w.undo();np.testing.assert_array_equal(np.asarray(w.current)[:,:,:3],pixels)
assert fingerprint(source)==before
w.confirm_image_change=lambda:True;w.close();app.processEvents();w=Studio(root/'data');assert w.viewer.crop_snap==16;w.close();app.processEvents()
print('PASS: live draw/move/four-corner resize, opposite anchors, numeric sync, ratio/snap, Esc/arrows, zoom hit size, pan, dim, exact crop/undo/source hash and snap restart;',out)
