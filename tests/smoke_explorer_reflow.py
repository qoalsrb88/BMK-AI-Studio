"""Cold-thumbnail paint stability and Explorer input integration."""
import os,sys,time,tempfile,threading
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from bmk_studio.app import Studio,configure_app
from bmk_studio.disk_browser import thumbnail
from bmk_studio.core import Store
root=Path(tempfile.mkdtemp(prefix='bmk-reflow-')).resolve();folder=root/'images';folder.mkdir();(folder/'child').mkdir()
for n,size in enumerate([(420,100),(100,420),(240,240)]):Image.new('RGB',size,'#e63127').save(folder/f'file-{n}-long-name.png')
store=Store(root/'user');store.state('disk_browser',{'split':[850,430]});store.db.close()
app=QApplication([]);configure_app(app);w=Studio(root/'user');w.resize(1500,900);w.show();w.activateWindow();w.workspace_mode.setCurrentIndex(2);d=w.disk_browser;app.processEvents();assert all(n>0 for n in d.split.sizes()),'0.9.5 split migration hid a pane'

def wait(check):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
        if check():return
    raise AssertionError('timeout')
release=threading.Event()
def delayed(path,stamp,cache):
    assert release.wait(15),'thumbnail gate timeout'
    return thumbnail(path,stamp,cache)
try:
    with patch('bmk_studio.disk_browser.thumbnail',delayed):
        d.navigate(str(folder));wait(lambda:len(d.model.rows)==4 and d.thumb_job is not None)
        index=d.proxy.index(1,0);rect=d.view.visualRect(index);label=rect.adjusted(6,rect.height()-28,-6,-4)
        QTest.mouseMove(w,QPoint(5,5));app.processEvents();before=d.view.viewport().grab().toImage();before.copy(label).save(str(root/'label-before.png'))
        assert len({before.pixelColor(x,y).name() for x in range(label.left(),label.right()) for y in range(label.top(),label.bottom())})>3,'filename must already be painted without thumbnail'
        release.set();wait(lambda:all(str(p) in d.icons for p in folder.glob('*.png')) and not d.thumb_job)
        app.processEvents();after=d.view.viewport().grab().toImage();assert d.view.visualRect(index)==rect;assert before.copy(label)==after.copy(label),'filename moved after thumbnail arrived'
        area=rect.adjusted(12,6,-12,-34);assert any(after.pixelColor(x,y).red()>180 and after.pixelColor(x,y).green()<100 for x in range(area.left(),area.right(),4) for y in range(area.top(),area.bottom(),4)),'thumbnail was not painted until resize'
    # Real wheel event, without resize or extra click.
    value=d.size.value();pos=QPointF(60,60);event=QWheelEvent(pos,QPointF(d.view.viewport().mapToGlobal(QPoint(60,60))),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
    app.sendEvent(d.view.viewport(),event);assert d.size.value()==value+16
    d.view.setFocus();QTest.keyClick(d.view,Qt.Key.Key_L,Qt.KeyboardModifier.ControlModifier);assert d.address.hasFocus() and d.address.selectedText()==str(folder)
    QTest.keyClick(d.address,Qt.Key.Key_F,Qt.KeyboardModifier.ControlModifier);assert d.search.hasFocus()
    # Tree click uses the same navigation/history; Alt+Up returns to the parent.
    child=d.navigation.fs.index(str(folder/'child'));wait(lambda:child.isValid() and not d.navigation.tree.visualRect(child).isEmpty())
    d.navigation.tree.scrollTo(child);QTest.mouseClick(d.navigation.tree.viewport(),Qt.MouseButton.LeftButton,pos=d.navigation.tree.visualRect(child).center());wait(lambda:d.folder==str(folder/'child') and not d.scan_job)
    QTest.keyClick(d.navigation.tree,Qt.Key.Key_Up,Qt.KeyboardModifier.AltModifier);wait(lambda:d.folder==str(folder) and not d.scan_job)
    d.view.setFocus();QTest.keyClick(d.view,Qt.Key.Key_Left,Qt.KeyboardModifier.AltModifier);wait(lambda:d.folder==str(folder/'child') and not d.scan_job)
    QTest.keyClick(d.view,Qt.Key.Key_Right,Qt.KeyboardModifier.AltModifier);wait(lambda:d.folder==str(folder) and not d.scan_job)
    Image.new('RGB',(10,10),'green').save(folder/'fresh.png');QTest.keyClick(d.view,Qt.Key.Key_F5);wait(lambda:len(d.model.rows)==5 and not d.scan_job)
    assert w.library.count()==0 and w.path is None
    wait(lambda:not w.jobs);w.grab().save(str(root/'explorer-light.png'));w.resize(1120,760);w.appearance['theme']='dark';w.apply_appearance();app.processEvents();w.grab().save(str(root/'explorer-dark.png'))
finally:
    release.set();w.close();wait(lambda:not w.jobs);app.processEvents()
print('PASS: cold-cache filename/thumbnail paint before resize, stable geometry, Ctrl+wheel, address/search shortcuts, actual tree click, Alt history/up, F5, no registration. Captures:',root)
