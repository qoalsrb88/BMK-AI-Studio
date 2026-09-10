"""Exercise real note tab signals and metadata-to-work actions without personal data."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app
from test_metadata import graph

root=Path(tempfile.mkdtemp(prefix='bmk-documents-')).resolve()
app=QApplication([]);configure_app(app)
w=Studio(root/'data');w.show()
meta=PngInfo();meta.add_text('parameters','actual output\nNegative prompt: original bad\nSteps: 12, Seed: 7');meta.add_text('prompt',json.dumps(graph()))
path=root/'image.png';Image.new('RGB',(64,64),'red').save(path,pnginfo=meta)
w.load(path);w.draft.setPlainText('image draft');w.save_draft()
first=w.store.save_note('first',{'prompt':'one','custom':{'retained':True}})
second=w.store.save_note('second',{'prompt':'two'})
w.open_note_id(first);w.draft.setPlainText('first edited')
w.open_note_id(second);w.draft.setPlainText('second edited')
w.note_tabs.setCurrentIndex(1);assert w.draft.toPlainText()=='first edited'
assert json.loads(w.store.note(second)[2])['prompt']=='second edited'
assert w.store.asset(path)[0]=='image draft'
w.main_tabs.setCurrentIndex(1);assert w.draft.toPlainText()=='image draft'
w.note_tabs.setCurrentIndex(2);w.close_document(2)
assert w.note_mode and w.draft.toPlainText()=='first edited'
w.main_tabs.setCurrentIndex(1)
assert w.draft.toPlainText()=='image draft';assert w.note_tabs.count()==2
w.open_note_id(first);w.draft.setPlainText('future')
revision=w.store.revisions(first)[-1][0];w.restore_note_version(revision)
assert w.draft.toPlainText()=='one';assert w.note_tabs.count()==2
assert json.loads(w.store.note(first)[2])['custom']=={'retained':True}
w.new_note();w.draft.setPlainText('new tab');w.main_tabs.setCurrentIndex(1)
assert w.draft.toPlainText()=='image draft';w.note_tabs.setCurrentIndex(2);assert w.draft.toPlainText()=='new tab'
w.main_tabs.setCurrentIndex(1);w.branch_choice.setCurrentIndex(1);w.use_branch()
assert w.draft.toPlainText()=='bird';assert w.positive.toPlainText()=='actual output'
assert '42' in w.branch_preview.toPlainText();assert '7' in w.generation_settings.toPlainText()
app.processEvents();w.tabs.setCurrentIndex(1);w.grab().save(str(root/'notes.png'))
w.tabs.setCurrentIndex(4);app.processEvents();w.grab().save(str(root/'metadata.png'))
w.open_note_id(first);w.close();app.processEvents()
w=Studio(root/'data');assert w.note_tabs.count()==3;assert w.note_id==first
assert w.draft.toPlainText()=='one';w.close();app.processEvents()
subprocess.run([sys.executable,'-c',
    "from PySide6.QtWidgets import QApplication; from bmk_studio.app import Studio; import sys; app=QApplication([]); w=Studio(sys.argv[1]); assert w.note_tabs.count()==3; assert w.note_id==sys.argv[2]; assert w.draft.toPlainText()=='one'; w.close()",
    str(root/'data'),first],check=True,cwd=Path(__file__).resolve().parents[1])
print('PASS: multiple notes, tab close, image draft separation, restore, new tab, branch copy and original priority; screenshots:',root)
