import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PIL import Image
from bmk_studio.app import Studio,configure_app

class SlowFake:
    loaded=None
    def run_many(self,paths,model):
        time.sleep(.3)
        return [{'device':'fake','model':'test','scores':[{'tag':'test','category':0,'score':.9}]} for p in paths]

app=QApplication([]);configure_app(app)
root=Path(tempfile.mkdtemp(prefix='bmk-cancel-')).resolve();model=root/'model';model.mkdir()
for name in ('config.json','model.safetensors','selected_tags.csv'):(model/name).write_text('fake')
paths=[]
for i in range(8):
    p=root/f'{i}.png';Image.new('RGB',(30+i,20+i),'blue').save(p);paths.append(p)
w=Studio(root/'data');w.show();w.add_paths(paths);w.model_path.setText(str(model));w.tagger=SlowFake();w.batch_size.setValue(2)
while w.jobs:app.processEvents();time.sleep(.01)
w.start_tags(paths);QTimer.singleShot(100,w.cancel_tags)
end=time.monotonic()+10
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
assert not w.jobs
assert w.last_batch_summary['cancelled'] and 0<w.last_batch_summary['completed']<8,w.last_batch_summary
saved=w.last_batch_summary['completed'];w.start_tags(paths)
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
assert w.last_batch_summary['completed']==8 and w.last_batch_summary['cached']==saved
w.close();app.processEvents()
print('PASS: responsive cancellation from GUI timer, partial results persisted, rerun skips completed images')
