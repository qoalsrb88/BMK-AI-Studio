"""Crash recovery and stale background completion against private synthetic data."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,subprocess,time,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint

root=Path(tempfile.mkdtemp(prefix='bmk-recovery-'));source=root/'a.png';Image.new('RGB',(120,80),'red').save(source);digest=fingerprint(source)
code='''import os,sys,time
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio
app=QApplication([]);w=Studio(sys.argv[1]);w.load(sys.argv[2]);w.set_box((10,10,50,40));w.apply_crop()
w.new_note();w.note_title.setText('Crash note');w.draft.setPlainText('durable note');w.save_draft()
w.new_note();w.note_title.setText('Closed note');w.draft.setPlainText('still stored');w.save_draft();w.close_document(2);w.open_note_id(w.note_tabs.tabData(1)['id'])
w.auto_checkpoint()
end=time.monotonic()+15
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
assert not w.jobs and w.recovery.contains(w.path)
os._exit(0)
'''
subprocess.run([sys.executable,'-c',code,str(root/'data'),str(source)],check=True,cwd=Path(__file__).resolve().parents[1])
app=QApplication([]);configure_app(app);w=Studio(root/'data')
assert w.current.size==(50,40) and w.image_dirty()
assert w.note_tabs.count()==2 and w.note_title.text()=='Crash note' and w.draft.toPlainText()=='durable note'
assert len(w.store.notes())==2 and fingerprint(source)==digest
assert w.save_edit_session() and not w.recovery.contains(source)
w.rotate();saved_method=w.recovery.save;started=threading.Event();release=threading.Event()
def slow_save(image,state):
    started.set();assert release.wait(10);return saved_method(image,state)
w.recovery.save=slow_save;w.auto_checkpoint();assert started.wait(3)
w.discard_recovery(source);release.set()
def wait():
    end=time.monotonic()+15
    while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
    assert not w.jobs
wait();assert not w.recovery.contains(source)
w.recovery.save=saved_method;w.auto_checkpoint();wait()
saved,state=w.recovery.load(source);assert saved.size==w.current.size and state['operations']==w.operations
# Saving A while navigating to B must never attach A's edit state to B.
w.rotate();w.recovery.save=slow_save;started.clear();release.clear();w.auto_checkpoint();assert started.wait(3)
second=root/'second.png';Image.new('RGB',(25,35),'blue').save(second);w.confirm_image_change=lambda:True;w.load(second)
release.set();wait();assert w.path==second and w.current.size==(25,35) and not w.operations
assert w.recovery.contains(source) and not w.recovery.contains(second)
# A completed recovery does not make unexported edits look explicitly saved.
assert fingerprint(source)==digest
w.confirm_image_change=lambda:True;w.close();app.processEvents()
print('PASS: ungraceful exit restores crop and active note tabs; close-tab persistence; original hash; explicit save retires recovery; invalidated in-flight save cannot resurrect discarded recovery')
