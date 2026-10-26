import os,sys,tempfile,time,json
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox,QMainWindow
from PySide6.QtCore import QTimer,QSettings,QCoreApplication,QEvent
from unittest.mock import patch
from contextlib import ExitStack
from bmk_studio.app import Studio,configure_app
from bmk_studio.note_transfer import NoteTransferDialog
root=Path(tempfile.mkdtemp(prefix='bmk-tabs-')).resolve();source=root/'image.png';Image.new('RGB',(400,500),'#537ba0').save(source)
guards=ExitStack()
guards.enter_context(patch('bmk_studio.app.QSettings',side_effect=lambda *args:QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)))
for name in ('reveal_in_explorer','open_default','copy_paths'):guards.enter_context(patch('bmk_studio.shell_actions.'+name))
guards.enter_context(patch('PySide6.QtWidgets.QMenu.exec',return_value=None))
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
w.main_tabs.setCurrentIndex(2);w.draft.insertPlainText(' persisted');w.save_draft();expected=w.draft.toPlainText();w.grab().save(str(root/'notes.png'));w.confirm_image_change=lambda:True

def close_window():
    app.processEvents();assert w.close();wait();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()

w.resize(1280,820);w.move(35,45);app.processEvents();w.notes_page.setSizes([410,850]);app.processEvents()
split=w.notes_page.sizes()
# Offscreen's small screen clamps restored geometry; compare against Qt's native restoration.
reference=QMainWindow();reference.setMinimumSize(1120,760);reference.restoreGeometry(w.saveGeometry());reference.show();app.processEvents();size=reference.size();position=reference.pos();reference.close();reference.deleteLater()
w.store.state('window',{'future':{'keep':True}});w.save_window_state();assert w.store.state('window')['future']=={'keep':True}
assert isinstance(w.store.state('window')['geometry'],str)
close_window();w=Studio(root/'user');w.show();app.processEvents()
assert w.main_tabs.currentIndex()==2 and w.draft.toPlainText()==expected
assert w.store.state('main_workspace')['notes_split']==split
assert w.size()==size and w.pos()==position,(w.size(),size,w.pos(),position)
assert abs(w.notes_page.sizes()[0]/sum(w.notes_page.sizes())-split[0]/sum(split))<.01
w.main_tabs.setCurrentIndex(1);assert w.draft.toPlainText()=='image work'
w.main_tabs.setCurrentIndex(2);w.showMaximized();app.processEvents();assert w.isMaximized()
close_window();w=Studio(root/'user');w.show();app.processEvents();assert w.isMaximized()
w.showNormal();app.processEvents();assert w.size()==size;close_window()

# Missing or corrupt state uses the existing size and the note splitter defaults.
from bmk_studio.core import Store
for n,geometry in enumerate((None,'invalid base64 !','bm90IGEgcXQgZ2VvbWV0cnk=')):
    profile=root/f'invalid-geometry-{n}';store=Store(profile)
    if geometry is not None:store.state('window',{'geometry':geometry})
    store.db.close();w=Studio(profile);assert (w.width(),w.height())==(1500,960);close_window()
w=Studio(root/'split-defaults');w.show();w.main_tabs.setCurrentIndex(2);app.processEvents()
for sizes in (None,[],[1],[1,2,3],[0,100],[-1,100],[True,100],[1.5,100],'300,1000'):
    w.notes_page.setSizes([300,1000]);default=w.notes_page.sizes()
    w.store.state('main_workspace',{'tab':2,'notes_split':sizes});w.notes_page.setSizes([600,700]);w.restore_main_workspace()
    assert w.notes_page.sizes()==default,(sizes,w.notes_page.sizes(),default)
close_window();guards.close()
print('PASS: top tabs, image/note buffers and undo, transfers and unknown fields, restart, window geometry/maximize, preserved state keys, note splitter and invalid-state fallbacks. Temporary artifacts:',root)
