import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,subprocess,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-sessions-'))
a=root/'a.png';b=root/'b.png';Image.new('RGB',(160,120),'red').save(a);Image.new('RGB',(120,160),'blue').save(b)
w=Studio(root/'data');w.show();w.load(a);w.set_box((10,20,60,70));w.apply_crop()
before=fingerprint(a);ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(1)
assert w.save_edit_session();assert not w.image_dirty();ctx=w.crop_context.copy()
w.load(b);w.rotate();assert w.save_edit_session();assert len(w.sessions.entries())==2
w.load(a);assert w.current.size==(60,70);assert w.crop_context==ctx
w.strength.setValue(1.3);w.feather.setValue(12);w.draft.setPlainText('recovered draft')
w.close();app.processEvents();timer.stop();assert ticks
code="""from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio
import sys
app=QApplication([]);w=Studio(sys.argv[1])
assert w.current.size==(60,70)
assert w.crop_context and w.draft.toPlainText()=='recovered draft'
assert w.strength.value()==1.3 and w.feather.value()==12
assert not w.image_dirty()
w.close()
"""
subprocess.run([sys.executable,'-c',code,str(root/'data')],check=True,cwd=Path(__file__).resolve().parents[1])
assert fingerprint(a)==before
Image.new('RGB',(160,120),'green').save(a)
w=Studio(root/'data');assert w.current.size==(160,120);assert not w.operations;assert '원본 이미지만' in w.source.text()
w.close();app.processEvents()
print('PASS: two independently saved image sessions, crop dependencies, timer-responsive checkpoint, fresh-process image/draft/settings recovery, changed-source fallback, unchanged original hash')
