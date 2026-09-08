import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtCore import QTimer
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint
from bmk_studio.color import srgb_profile

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-color-'));path=root/'rgba.png'
Image.new('RGBA',(30,20),(20,70,140,120)).save(path,icc_profile=srgb_profile());before=fingerprint(path)
w=Studio(root/'data');w.load(path);w.rotate();errors=[];w.error=errors.append
def apply():app.activeModalWidget().findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
QTimer.singleShot(0,apply);w.normalize_color()
end=time.monotonic()+20
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
assert not w.jobs and not errors and w.current.size==(30,20)
assert w.current.getpixel((0,0))==(20,70,140,120) and w.current.info['icc_profile']
assert w.operations[-1]['color_normalization']['output']=='sRGB' and fingerprint(path)==before
w.undo();assert w.current.size==(20,30)
w.confirm_image_change=lambda:True;w.close();app.processEvents()
print('PASS: real normalization dialog/background apply restores full source geometry, preserves alpha/source hash, attaches sRGB profile; undo restores preceding edit')
