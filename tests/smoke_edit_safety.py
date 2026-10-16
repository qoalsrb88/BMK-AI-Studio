import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import Store
from bmk_studio.prompt_highlight import refresh_all

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-safe-edit-')).resolve()
a=root/'a.png';b=root/'b.png';Image.new('RGB',(100,100),'red').save(a);Image.new('RGB',(120,80),'blue').save(b)
w=Studio(root/'data');w.load(a);assert not w.image_dirty()
w.set_box((5,5,50,50));w.apply_crop();assert w.image_dirty()
with patch.object(w,'confirm_image_change',return_value=False):
    assert w.load(b) is False and w.path==a and w.current.size==(50,50)
with patch('bmk_studio.app.QFileDialog.getSaveFileName',return_value=(str(root/'export.png'),'PNG')):
    assert w.export_image() and not w.image_dirty()
assert (root/'export.png.bmk.json').is_file()
w.load(b);assert w.path==b and not w.image_dirty()
w.show();nid=w.store.save_note('shutdown note',{'prompt':'{original}','custom':{'keep':True}})
w.open_note_id(nid);w.draft.setPlainText('{after cancelled close}')
with patch.object(w,'confirm_image_change',return_value=False):
    assert not w.close() and not w.closed and w.isVisible()
QTest.qWait(750)
assert json.loads(w.store.note(nid)[2])['prompt']=='{after cancelled close}'
w.draft.setPlainText('{saved on close}');assert w.close()
assert w.closed and not any(timer.isActive() for timer in (w.autosave,w.recovery_timer,w.workspace_timer))
# A later window/theme refresh can rehighlight a still-live, closed editor.
# Exercise the queued autosave, not just a direct call to its slot.
with patch('sys.excepthook') as callback_errors:
    refresh_all();assert w.autosave.isActive();QTest.qWait(750)
    assert not w.autosave.isActive();assert w.close()
    callback_errors.assert_not_called()
saved=Store(root/'data')
try:
    body=json.loads(saved.note(nid)[2]);assert body['prompt']=='{saved on close}' and body['custom']=={'keep':True}
finally:saved.db.close()
print('PASS: image navigation cancellation, export checkpoint, cancelled close autosave, final note save, closed-window timer safety and repeated close')
