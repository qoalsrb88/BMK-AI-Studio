import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication,QDialogButtonBox
from PySide6.QtCore import QTimer
from bmk_studio.app import Studio,configure_app
from bmk_studio.stitch_dialog import StitchDialog
from bmk_studio.core import fingerprint,load_image,stitch_image

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-stitch-')).resolve()
source=root/'source.png';Image.new('RGB',(360,280),'#285050').save(source)
external=root/'external.png';Image.new('RGBA',(80,100),(200,60,30,200)).save(external)
w=Studio(root/'data');w.show();w.load(source);w.set_box((100,80,80,100));w.apply_crop();ctx=w.crop_context.copy();before=fingerprint(source)
class AutomatedDialog(StitchDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.dx.setValue(3);self.dy.setValue(-2);self.angle.setValue(7.5);self.scale.setValue(1.1);self.feather.setValue(4)
        self.poll=QTimer(self);self.poll.setInterval(20);self.poll.timeout.connect(self.check);self.poll.start()
    def check(self):
        if self.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled() and self.job is None:
            self.grab().save(str(root/'stitch-preview.png'));self.poll.stop();self.accept()
with patch('bmk_studio.app.StitchDialog',AutomatedDialog),patch('bmk_studio.app.QFileDialog.getOpenFileName',return_value=(str(external),'')):
    w.stitch()
deadline=time.monotonic()+15
while w.jobs and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
assert not w.jobs
expected=stitch_image(load_image(ctx['base']),load_image(external),ctx['box'],ctx['rotation'],4,None,(3,-2),7.5,1.1)
np.testing.assert_array_equal(np.asarray(w.current),np.asarray(expected));assert w.crop_context is None
assert w.operations[-1]['angle']==7.5 and fingerprint(source)==before
assert w.save_edit_session();w.close();app.processEvents()
w=Studio(root/'data');np.testing.assert_array_equal(np.asarray(w.current),np.asarray(expected));w.close();app.processEvents()
print('PASS: crop/external edit/dialog adjustment/background full resolution/stitch checkpoint/restart; source preserved; preview:',root/'stitch-preview.png')
