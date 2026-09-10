"""Real Qt browser interactions, failure recovery, classifications and restart."""
import os,sys,time,tempfile,json
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,PngImagePlugin
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QInputDialog,QPushButton
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint
from bmk_studio.compare_browser import BrowserCompareDialog

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-browser-')).resolve();w=Studio(root/'data');w.show()
def drain():
    end=time.monotonic()+30
    while (w.jobs or w.library.search_pending) and time.monotonic()<end:app.processEvents();time.sleep(.01)
    app.processEvents();assert not w.jobs and not w.library.search_pending
paths=[]
for n in range(24):
    path=root/f'image{n:02}.png';meta=PngImagePlugin.PngInfo();meta.add_text('parameters',f'portrait unique{n}\nNegative prompt: blur\nSteps: 20, Seed: {n}, Model: test')
    Image.new('RGB',(240,360) if n%2 else (360,240),(30+n*7,120,160)).save(path,pnginfo=meta);paths.append(path)
hashes=[fingerprint(p) for p in paths];w.add_paths(paths);drain()
nid=w.store.save_note('lighting note',{'prompt':'(soft light:1.2)','future':{'keep':True}});w.refresh_notes()
w.search.setText('unique3');drain();assert w.library.proxy.rowCount()==1 and w.notes.topLevelItemCount()==1
w.note_search.setText('missing-note');assert w.notes.topLevelItemCount()==0 and w.library.proxy.rowCount()==1
w.note_search.clear();w.search.clear();drain()
# Accepted migration fails: search and autosave must work without restarting.
errors=[];w.error=errors.append
def accept_location():
    dialog=app.activeModalWidget();dialog.target.setText(str(root/'new'));dialog.controls.button(QDialogButtonBox.StandardButton.Save).click()
with patch('bmk_studio.data_location.activate_directory',side_effect=OSError('simulated copy failure')):
    QTimer.singleShot(0,accept_location);assert not w.change_data_directory()
assert errors and not w.library.stopped and w.recovery_timer.isActive()
w.search.setText('unique3');drain();assert w.library.proxy.rowCount()==1
w.draft.setPlainText('after failed migration');w.save_draft();assert w.store.asset(w.path)[0]=='after failed migration'
# Scope and conjunction; metadata-negative search is distinct from positive.
w.scope.setCurrentIndex(w.scope.findData('positive'));w.search.setText('blur');drain();assert w.library.proxy.rowCount()==0
w.scope.setCurrentIndex(w.scope.findData('negative'));drain();assert w.library.proxy.rowCount()==24
w.clear_browser_filters();w.aspect_filter.setCurrentIndex(w.aspect_filter.findData('portrait'));drain();assert w.library.proxy.rowCount()==12
w.models_filter.setText('test');w.days_filter.setCurrentIndex(1);drain();assert w.library.proxy.rowCount()==12
w.pixels_filter.setCurrentIndex(1);drain();assert w.library.proxy.rowCount()==0
w.clear_browser_filters();drain();w.library_items[str(paths[3])].setSelected(True);w.mark_favorite(True);w.rate_selection(4)
with patch.object(QInputDialog,'getText',return_value=('Candidates',True)):w.new_collection()
drain();w.clear_browser_filters();drain();w.library_items[str(paths[3])].setSelected(True);w.assign_collection('Candidates',True)
w.favorite_filter.setChecked(True);w.rating_filter.setCurrentIndex(w.rating_filter.findData(4));w.collection_filter.setCurrentIndex(w.collection_filter.findData('Candidates'));drain();assert w.library.proxy.rowCount()==1
assert w.library.proxy.index(0,0).data().startswith('★4 ')
with patch.object(QInputDialog,'getText',return_value=('Portrait picks',True)):w.save_search()
w.clear_browser_filters();drain();w.saved_search.setCurrentIndex(w.saved_search.findData('Portrait picks'));w.restore_search();drain();assert w.library.proxy.rowCount()==1
# Same selection and editable pixels survive workspace switches.
w.library_items[str(paths[3])].setSelected(True);before=w.current.tobytes();selected=w.selection_paths();w.workspace_mode.setCurrentIndex(1);app.processEvents();w.viewer.scale(1.5,1.5);scale=w.viewer.transform().m11()
w.workspace_mode.setCurrentIndex(0);app.processEvents();w.workspace_mode.setCurrentIndex(1);app.processEvents()
assert w.selection_paths()==selected and w.current.tobytes()==before and w.viewer.transform().m11()==scale
w.tabs.setCurrentIndex(3);w.crop_toggle.setChecked(True);w.edit_tool.setCurrentIndex(3);assert not w.crop_toggle.isChecked() and w.edit_pages.currentIndex()==3
# Snippet insertion keeps exact syntax and supports undo.
w.draft.setPlainText('base');w.store.state('pinned_notes',[nid])
def insert_snippet():
    dialog=app.activeModalWidget();from PySide6.QtWidgets import QListWidget
    dialog.findChild(QListWidget).setCurrentRow(0)
    next(b for b in dialog.findChildren(QPushButton) if b.text()=='현재 프롬프트에 추가').click()
QTimer.singleShot(0,insert_snippet);w.prompt_snippets();assert w.draft.toPlainText()=='base\n(soft light:1.2)';w.draft.undo();assert w.draft.toPlainText()=='base'
from bmk_studio.core import inspect_image,load_image
comparison=BrowserCompareDialog((str(paths[0]),inspect_image(paths[0]),load_image(paths[0])),(str(paths[1]),inspect_image(paths[1]),load_image(paths[1])),w);comparison.show();app.processEvents()
comparison.canvases[0].scale(1.5,1.5);comparison.synchronize(comparison.canvases[0]);assert comparison.canvases[1].transform().m11()>0;comparison.close()
w.clear_browser_filters();w.workspace_mode.setCurrentIndex(0);w.thumbnail_slider.setValue(128);drain();app.processEvents();w.grab().save(str(root/'gallery.png'))
w.workspace_mode.setCurrentIndex(1);w.edit_tool.setCurrentIndex(0);app.processEvents();w.grab().save(str(root/'work.png'))
w.save_draft();w.close();app.processEvents();w=Studio(root/'data');drain()
assert w.active_workspace=='work' and w.store.state('saved_searches')['Portrait picks']
assert w.store.db.execute('SELECT rating FROM favorites WHERE path=?',(str(paths[3]),)).fetchone()[0]==4
assert w.store.db.execute('SELECT path FROM collection_items WHERE name=?',('Candidates',)).fetchone()[0]==str(paths[3])
assert hashes==[fingerprint(p) for p in paths];w.close();app.processEvents()
print('PASS: failed transfer resumes search/autosave, independent searches, scope/filter conjunction, favorites/collections/saved-search restart, workspace selection/zoom, contextual edit tools, exact snippet undo, A/B sync, source hashes; captures:',root)
