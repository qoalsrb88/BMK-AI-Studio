import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from bmk_studio.core import tone_restore,fingerprint
from bmk_studio.gpu_tone import tone_restore_cuda
from bmk_studio.app import Studio,configure_app

rng=np.random.default_rng(42);a=Image.fromarray(rng.integers(0,256,(67,83,4),dtype=np.uint8));b=Image.fromarray(rng.integers(0,256,(53,78,3),dtype=np.uint8))
for luminance in (False,True):
    for levels in (1,5,8):
        cpu=np.asarray(tone_restore(a,b,.8,levels,luminance)).astype(int);gpu=np.asarray(tone_restore_cuda(a,b,.8,levels,luminance)).astype(int)
        assert np.max(np.abs(cpu-gpu))<=1 and np.array_equal(gpu[:,:,3],np.asarray(a)[:,:,3])
app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-gpu-tone-'));path=root/'source.png';ref=root/'ref.png';a.save(path);b.save(ref);before=fingerprint(path)
w=Studio(root/'data');w.load(path);w.reference.setText(str(ref));w.tone_backend.setCurrentIndex(1);errors=[];w.error=errors.append
ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(1);w.restore_tone()
end=time.monotonic()+30
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
timer.stop();assert not w.jobs and not errors and ticks and w.operations[-1]['backend']=='cuda'
assert fingerprint(path)==before;w.confirm_image_change=lambda:True;w.close();app.processEvents()
print('PASS: CUDA vs CPU RGB/luminance, levels 1/5/8, <=1 LSB difference and exact alpha; Qt background apply, timer responsiveness, source hash')
