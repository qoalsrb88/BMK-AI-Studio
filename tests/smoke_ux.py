"""Exercise UI actions against private data and synthetic pixels."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton,QComboBox,QSpinBox,QDialogButtonBox
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint

app=QApplication([]);configure_app(app)
root=Path(tempfile.mkdtemp(prefix='bmk-ux-'));source=root/'synthetic.png'
image=Image.new('RGB',(320,240),'#6489b0');image.save(source);before=fingerprint(source)
w=Studio(root/'data');w.show();w.add_paths([source])
deadline=time.monotonic()+15
while w.jobs and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
assert not w.jobs
assert app.palette().color(QPalette.ColorRole.Window).lightness()>200
w.thumbnail_slider.setValue(112);app.processEvents()
assert w.library.iconSize().width()==112 and w.library.visualRect(w.library.proxy.index(0,0)).height()>=112
for label,editor in [('프롬프트',w.positive),('네거티브',w.negative),('작업 프롬프트',w.draft),('작업 네거티브',w.draft_negative)]:
    editor.setPlainText(label+'\n전체 텍스트')
    copy=next(b for b in w.findChildren(QPushButton) if b.accessibleName()==label+' 전체 복사')
    copy.click();assert app.clipboard().text()==editor.toPlainText()
w.viewer.actual_size();w.viewer.scale(4,4);w.viewer.update_scroll_margin()
rect=w.viewer.image_rect;margin=w.viewer.sceneRect()
assert 0<rect.left()-margin.left()<=rect.width()/2
assert w.viewer.horizontalScrollBar().maximum()>0
bar=w.viewer.horizontalScrollBar();bar.setValue(bar.minimum())
assert w.viewer.mapToScene(QPoint(0,0)).x()<0
menu=w.viewer.interpolation_menu();menu.actions()[0].trigger();assert w.viewer.interpolation=='nearest'
assert w.viewer.pixmap_item.transformationMode()==Qt.TransformationMode.FastTransformation
menu.deleteLater()
w.appearance.update(theme='dark',overscroll=40);w.apply_appearance();w.store.state('appearance',w.appearance)
assert app.palette().color(QPalette.ColorRole.Window).lightness()<80
w.tabs.setCurrentIndex(0);app.processEvents();w.grab().save(str(root/'dark.png'))
w.appearance['theme']='light';w.apply_appearance();w.store.state('appearance',w.appearance)
app.processEvents();w.grab().save(str(root/'light.png'))
def save_settings():
    dialog=app.activeModalWidget()
    dialog.findChildren(QComboBox)[0].setCurrentIndex(1)
    dialog.findChild(QSpinBox).setValue(35)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
QTimer.singleShot(0,save_settings);w.settings_button.click()
assert w.viewer.overscroll==35 and w.appearance['theme']=='dark'
current=w.path
index=w.library.proxy.index(0,0);point=w.library.visualRect(index).center()
QTest.mouseMove(w.library.viewport(),point);app.processEvents()
assert w.library.remove_button.isVisible()
QTest.mouseClick(w.library.remove_button,Qt.MouseButton.LeftButton);app.processEvents()
assert w.library.count()==0 and w.path==current and fingerprint(source)==before
w.search.setText('no matching image');w.restore_removed_button.click();app.processEvents()
assert w.library.count()==1 and w.library.proxy.rowCount()==0 and w.path==current
w.search.clear();w.remove_library_paths([source]);assert w.library.count()==0
w.close();app.processEvents()
w=Studio(root/'data');assert w.viewer.interpolation=='nearest' and w.viewer.overscroll==35 and w.appearance['theme']=='dark'
assert w.thumbnail_slider.value()==112 and w.library.iconSize().width()==112
assert w.library.count()==0 and fingerprint(source)==before
w.close();app.processEvents()
print('PASS: four copy actions, hover removal/source preservation, bounded pan, interpolation action, theme and preferences restart; captures:',root)
