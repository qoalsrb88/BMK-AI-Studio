import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF,Qt
from PySide6.QtTest import QTest
from bmk_studio.app import Studio,configure_app
from bmk_studio.dialogs import MaskDialog,ResizeDialog,ToneDialog,CompareDialog,RevisionDialog

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-editors-')).resolve()
before=Image.new('RGBA',(720,960),(35,80,120,255));reference=Image.new('RGBA',(720,960),(85,70,100,255))
source=root/'image.png';before.save(source)
w=Studio(root/'data');w.show();w.load(source)
nid=w.store.save_note('캐릭터 A',{'prompt':'first','loras':[{'name':'keep'}],'custom':{'keep':True}},category='인물/의상')
w.open_note_id(nid);w.draft.setPlainText('second');w.save_draft();first=w.store.revisions(nid)[-1][0]
w.restore_note_version(first);assert w.draft.toPlainText()=='first'
assert w.note_extra['custom']=={'keep':True};assert len(w.store.revisions(nid))==3
w.note_category.setCurrentText('인물/배경');w.save_draft();assert w.store.note(nid)[3]=='인물/배경'
w.archive_current_note();assert w.store.note(nid)[4]==1;w.archive_current_note();assert w.store.note(nid)[4]==0
# The read-only LoRA line appears only for a note with LoRA settings and follows every note_extra change.
assert w.lora_view.toPlainText()=='<lora:keep:1.00>' and not w.lora_box.isHidden() and w.lora_off.isHidden() and w.lora_view.isReadOnly()
plain=w.store.save_note('LoRA 없음',{'prompt':'plain','loras':[]});w.open_note_id(plain);assert w.lora_box.isHidden() and w.lora_view.toPlainText()==''
w.note_extra={**w.note_body(),'loras':[{'name':'off','enabled':False}]};assert not w.lora_box.isHidden() and w.lora_view.toPlainText()=='' and w.lora_off.text().endswith('off') and not w.lora_off.isHidden()
w.open_note_id(nid);assert w.lora_view.toPlainText()=='<lora:keep:1.00>' and w.lora_off.isHidden()
w.main_tabs.setCurrentIndex(1);assert not w.note_mode and w.lora_box.isHidden();w.main_tabs.setCurrentIndex(2);assert w.note_id==nid and not w.lora_box.isHidden()
history=RevisionDialog(w.store.revisions(nid),w);history.show();app.processEvents();assert history.revision_id is not None;history.reject()
resize=ResizeDialog(before,w);resize.show();resize.presets.setCurrentIndex(1);resize.mode.setCurrentIndex(1);app.processEvents();assert resize.settings()[:2]==(1024,1024)
if len(sys.argv)>1:resize.grab().save(str(Path(sys.argv[1])/'preview-resize.png'))
resize.reject()
mask=MaskDialog(before,parent=w);mask.show();app.processEvents();mask.canvas.fill(0)
point=mask.canvas.mapFromScene(QPointF(200,200))
QTest.mousePress(mask.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
QTest.mouseRelease(mask.canvas.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,point)
assert mask.canvas.result().getpixel((200,200))>0;mask.canvas.undo();assert mask.canvas.result().getpixel((200,200))==0
mask.canvas.fill(0);mask.canvas.paint(QPointF(200,200));mask.canvas.last=None
if len(sys.argv)>1:mask.grab().save(str(Path(sys.argv[1])/'preview-mask.png'))
mask.reject()
tone=ToneDialog(before,reference,.8,5,False,w);tone.show();deadline=time.monotonic()+20
while tone.job.isRunning() or tone.before is None:
    app.processEvents();time.sleep(.01);assert time.monotonic()<deadline
tone.strength.setValue(40);tone.split.setValue(50);app.processEvents()
if len(sys.argv)>1:tone.grab().save(str(Path(sys.argv[1])/'preview-tone.png'))
tone.reject()
compare=CompareDialog(before,reference,w);compare.show();compare.slider.setValue(75);app.processEvents();compare.reject()
w.tabs.setCurrentIndex(1);app.processEvents()
if len(sys.argv)>1:w.grab().save(str(Path(sys.argv[1])/'preview-notes.png'))
w.new_note();w.draft.setPlainText('unsaved new note');w.save_draft();assert w.note_id is not None
assert 'unsaved new note' in w.store.note(w.note_id)[2]
w.close()
while w.jobs:app.processEvents();time.sleep(.01)
app.processEvents()
print('PASS: note tree/category/autosave/archive/version restore with unknown fields, read-only LoRA line, resize presets, mask paint/undo, asynchronous tone preview, comparison slider')
