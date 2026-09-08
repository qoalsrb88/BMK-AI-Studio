"""End-to-end Qt: real GPU batch, selection safety, watcher and library restart."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,tempfile,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from PIL.PngImagePlugin import PngInfo
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import file_stamp
from bmk_studio.tagger import model_signature

app=QApplication([]);configure_app(app)
root=Path(tempfile.mkdtemp(prefix='bmk-workflow-'))
def fixture(name,size,color,prompt):
    image=Image.new('RGB',size,color);draw=ImageDraw.Draw(image)
    draw.ellipse((size[0]//4,size[1]//5,3*size[0]//4,3*size[1]//5),fill='#eec88b')
    meta=PngInfo();meta.add_text('parameters',prompt+'\nNegative prompt: blur\nSteps: 24, Seed: 1')
    path=root/name;image.save(path,format='PNG',pnginfo=meta);return path
a=fixture('Moonlight.png',(720,960),'#234859','mountain landscape, moonlight')
b=fixture('Sunset.png',(960,640),'#654536','sunset, calm atmosphere')

def wait_until(predicate,seconds=40):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(.025)
    app.processEvents();assert predicate(),'Timed out'

w=Studio(root/'data');errors=[];w.error=errors.append;w.show()
w.add_paths([a,b]);w.model_path.setText(sys.argv[1])
wait_until(lambda:not w.jobs)
assert not w.library_items[str(a)].icon().isNull()
w.search.setText('moonlight');wait_until(lambda:not w.library.search_pending);assert not w.library_items[str(a)].isHidden();assert w.library_items[str(b)].isHidden()
w.search.clear()
for i in range(w.library.count()):w.library.item(i).setSelected(True)
w.batch_size.setValue(2);w.run_selected_tags()
w.load(b)  # Navigation while inference runs must never attach A's result to B.
wait_until(lambda:not w.jobs,90)
assert not errors,errors
assert w.last_batch_summary['completed']==2,w.last_batch_summary
expected=w.store.saved_tags(b,model_signature(sys.argv[1]),file_stamp(b))
assert w.scores==expected and expected
assert w.tag_progress.value()==2
w.run_selected_tags();wait_until(lambda:not w.jobs)
assert w.last_batch_summary['cached']==2
w.folder=str(root);w.watch_toggle.setChecked(True)
partial=fixture('Incoming.png.crdownload',(320,480),'#28333b','new reference')
time.sleep(.1);partial.rename(root/'Incoming.png')
wait_until(lambda:str(root/'Incoming.png') in w.library_items and str(root/'Incoming.png') in w.index_stamps,12)
assert w.path==b,'Watcher must not steal the active image'
assert w.library.count()==3
w.tabs.setCurrentIndex(2);app.processEvents()
if len(sys.argv)>2:w.grab().save(sys.argv[2])
w.close();wait_until(lambda:not w.jobs and not w.isVisible())
w2=Studio(root/'data');w2.model_path.setText(sys.argv[1]);w2.load(b)
assert w2.library.count()==3 and not w2.watch_toggle.isChecked()
assert w2.scores==expected
w2.close();wait_until(lambda:not w2.jobs)
print('PASS: two-image real GPU batch, cache reuse, navigation isolation, thumbnails, metadata search, stable download discovery, safe watcher shutdown, persistent library/tag reload')
