import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-queue-')).resolve();model=root/'model';model.mkdir()
for name in ('config.json','model.safetensors','selected_tags.csv'):(model/name).write_text('fixture')
paths=[]
for i in range(4):
    path=root/f'{i}.png';Image.new('RGB',(30+i,30),(i*50,0,0)).save(path);paths.append(str(path))
class Tagger:
    loaded=None;precision='fp32'
    def __init__(self):self.calls=[];self.started=threading.Event();self.release=threading.Event()
    def run_many(self,paths,model):
        self.calls.extend(paths);self.started.set();assert self.release.wait(10)
        return [{'model':'fixture','device':'cpu','scores':[{'tag':'test','category':0,'score':.9}]} for p in paths]
w=Studio(root/'data');w.model_path.setText(str(model));w.tagger=Tagger();w.batch_size.setValue(1)
w.tag_queue=paths[:3];w.open_queue();w.run_queue();assert w.tagger.started.wait(5)
# Reorder/remove waiting images while the first batch is executing.
w.queue_dialog.items.item(1).setSelected(True);w.queue_dialog.move(-1);assert w.tag_queue==[paths[2],paths[1]]
w.queue_dialog.remove();assert w.tag_queue==[paths[1]]
w.tag_queue.append(paths[3]);w.save_queue();w.pause_queue();w.tagger.release.set()
def wait(predicate):
    end=time.monotonic()+15
    while not predicate() and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert predicate()
wait(lambda:not w.tag_busy);assert w.tagger.calls==paths[:1] and w.tag_queue==[paths[1],paths[3]]
w.queue_dialog.close();w.close();app.processEvents()
w=Studio(root/'data');assert w.tag_queue==[paths[1],paths[3]] and not w.queue_running
w.tagger=Tagger();w.tagger.release.set();w.run_queue();wait(lambda:not w.queue_running and not w.tag_busy)
assert w.tagger.calls==[paths[1],paths[3]] and not w.tag_queue
w.close();app.processEvents()
print('PASS: edit/reorder/remove/add waiting items during real worker batch; pause completes active batch; restart retains pending; resume processes only remaining items')
