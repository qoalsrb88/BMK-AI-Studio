import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,shutil,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QListWidget,QPushButton,QDialogButtonBox,QFileDialog
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-relink-ui-')).resolve();old=root/'old.png';new=root/'moved.png';Image.new('RGB',(50,40),'red').save(old)
w=Studio(root/'data');w.load(old);w.set_box((1,2,20,30));w.apply_crop();w.draft.setPlainText('relink draft');assert w.save_edit_session()
before=fingerprint(old);shutil.move(old,new);w.close();app.processEvents()
w=Studio(root/'data');errors=[];w.error=errors.append;original=QFileDialog.getOpenFileName
QFileDialog.getOpenFileName=lambda *args:(str(new),'Images')
def reconnect():
    dialog=app.activeModalWidget();items=dialog.findChild(QListWidget);items.setCurrentRow(0)
    next(button for button in dialog.findChildren(QPushButton) if button.text()=='선택 원본 재연결…').click()
    assert items.currentItem().data(Qt.ItemDataRole.UserRole)==str(new)
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open).click()
try:QTimer.singleShot(0,reconnect);w.open_edit_sessions()
finally:QFileDialog.getOpenFileName=original
assert not errors and w.path==new and w.current.size==(20,30) and w.draft.toPlainText()=='relink draft'
assert fingerprint(new)==before and w.sessions.contains(old)
w.close();end=time.monotonic()+15
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
assert not w.jobs
print('PASS: actual checkpoint dialog selects relocated source, verifies/copies associations, opens restored crop/draft; original hash and old records retained')
