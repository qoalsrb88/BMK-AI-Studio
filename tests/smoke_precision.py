import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app
from bmk_studio.tagger import inference_signature
from bmk_studio.core import file_stamp

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-precision-'));path=root/'image.png';Image.new('RGB',(128,128),'#9348a1').save(path)
w=Studio(root/'data');w.load(path);w.model_path.setText(sys.argv[1]);errors=[];w.error=errors.append
for mode in ('fp32','fp16','bf16'):
    w.precision.setCurrentIndex(w.precision.findData(mode));w.run_tags()
    end=time.monotonic()+120
    while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not w.jobs and not errors,errors
    assert w.scores and w.scores['precision']==mode and w.scores['device']=='cuda'
    assert len(w.scores['scores'])>10000
    saved=w.store.saved_tags(path,inference_signature(sys.argv[1],mode),file_stamp(path));assert saved['precision']==mode
    print('PASS:',mode,len(saved['scores']),'CUDA scores')
assert w.store.db.execute('SELECT COUNT(*) FROM tag_runs').fetchone()[0]==3
w.unload_tagger();w.close();app.processEvents()
