import os,sys,tempfile,time,json
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox
from PySide6.QtCore import QTimer
from bmk_studio.app import Studio,configure_app
from bmk_studio.note_transfer import NoteTransferDialog
root=Path(tempfile.mkdtemp(prefix='bmk-tabs-'));source=root/'image.png';Image.new('RGB',(400,500),'#537ba0').save(source)
app=QApplication([]);configure_app(app);w=Studio(root/'user');w.show();w.add_paths([source])
def wait():
    end=time.monotonic()+20
    while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
    app.processEvents();assert not w.jobs
wait();w.draft.setPlainText('image work');w.draft.insertPlainText(' undo');original=w.draft.toPlainText();w.draft_negative.setPlainText('image negative');w.set_box((20,30,120,140));w.apply_crop();wait();size=w.current.size
w.main_tabs.setCurrentIndex(2);assert w.note_mode and w.draft.isVisible() and w.notes_page.isVisible() and not w.main_splitter.isVisible();assert w.store.asset(source)[0]==original
w.note_title.setText('independent note');w.note_category.setCurrentText('Characters/Clothes');w.draft.setPlainText('note prompt');w.draft_negative.setPlainText('note negative');w.note_extra['future']={'keep':[1,2]};w.main_tabs.setCurrentIndex(0);nid=w.note_tabs.tabData(1)['id'];assert json.loads(w.store.note(nid)[2])['prompt']=='note prompt';assert w.current.size==size
w.main_tabs.setCurrentIndex(1);assert w.draft.toPlainText()==original and w.draft_negative.toPlainText()=='image negative';assert w.draft.document().isUndoAvailable();w.draft.undo();assert w.draft.toPlainText()=='image work'
w.main_tabs.setCurrentIndex(2);assert w.draft.toPlainText()=='note prompt' and w.note_extra['future']=={'keep':[1,2]};w.main_tabs.setCurrentIndex(1)
# Commit transfer through actual dialog controls and keep the image context.
def save_dialog():
    d=app.activeModalWidget();assert isinstance(d,NoteTransferDialog);d.folder.setCurrentText('Characters/Clothes');d.target.setCurrentIndex(d.target.findData(nid));
    for check,key,editor in d.sections:check.setChecked(check.text()=='작업 프롬프트')
    d.buttons.button(QDialogButtonBox.StandardButton.Save).click()
QTimer.singleShot(0,save_dialog);w.save_image_to_note();assert w.main_tabs.currentIndex()==1 and w.draft.toPlainText()=='image work';body=json.loads(w.store.note(nid)[2]);assert body['prompt']=='note prompt\n\nimage work' and body['future']=={'keep':[1,2]} and str(source) in body['notes']
w.open_saved_note.click();assert w.main_tabs.currentIndex()==2 and w.draft.toPlainText()==body['prompt']
def send_dialog():
    d=app.activeModalWidget();next(b for b in d.buttons() if b.text()=='기존 내용에 추가').click()
QTimer.singleShot(0,send_dialog);w.note_to_image();assert w.main_tabs.currentIndex()==1 and w.draft.toPlainText().startswith('image work\n\nnote prompt');w.draft.undo();assert w.draft.toPlainText()=='image work'
w.main_tabs.setCurrentIndex(2);w.draft.insertPlainText(' persisted');w.save_draft();expected=w.draft.toPlainText();w.grab().save(str(root/'notes.png'));w.confirm_image_change=lambda:True;w.close();wait();w=Studio(root/'user');w.show();assert w.main_tabs.currentIndex()==2 and w.draft.toPlainText()==expected;w.main_tabs.setCurrentIndex(1);assert w.draft.toPlainText()=='image work';w.close();wait();print('PASS: top tabs, independent image/note buffers and undo, crop preservation, folders and append transfer, unknown fields, reverse send/undo, restart. Capture:',root)
