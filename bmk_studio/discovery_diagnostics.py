"""Frozen-package coverage for discovery, with optional real local model."""
import json,time,io
from pathlib import Path
from PIL import Image
from .core import Store
from .discovery import completions,generated_date

def run(root,window,model=None):
    from PySide6.QtWidgets import QApplication
    checks=[];window.clear_browser_filters();window.workspace_mode.setCurrentIndex(0);window.thumbnail_slider.setValue(384)
    deadline=time.monotonic()+30
    while (window.jobs or window.library.large.timer.isActive()) and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
    assert not window.jobs
    # A visible source requests its demand thumbnail during paint.
    window.library.viewport().update();QApplication.processEvents()
    deadline=time.monotonic()+30
    while (window.jobs or window.library.large.timer.isActive()) and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
    blob=window.store.db.execute('SELECT thumbnail FROM large_thumbnails WHERE path=?',(str(window.path),)).fetchone()
    assert blob and max(Image.open(io.BytesIO(blob[0])).size)>160
    assert 'bird' in completions(window.library.database,'bi','positive')
    assert generated_date('x\n{"raw":{"creation time":"2026-09-08t00:00:00z"}}')=='2026-09-08'
    checks.extend(['demand_large_thumbnail','completion','explicit_creation_date'])
    if model:
        from .semantic import search
        store=Store(root/'semantic-test');paths=[]
        texts=['A rainy city street at night with neon lights','A sunny beach with blue sea','A cute cat sleeping on a sofa']
        for n,text in enumerate(texts):
            path=str(root/f'semantic-{n}.png');paths.append(path);store.index_image(path,'stamp','image\n'+json.dumps({'positive':text}),b'')
        try:
            result=search(store.root/'library.sqlite3',paths,'비 오는 밤의 도시 거리',model)
            assert result['matches'][0][1]==paths[0] and result['matches'][0][0]>.6
            second=search(store.root/'library.sqlite3',paths,'비 오는 밤의 도시 거리',model);assert result['matches']==second['matches']
        finally:store.db.close()
        checks.extend(['real_multilingual_onnx_cpu','semantic_cache_reuse'])
    # Read-only disk mode must never implicitly register its preview source.
    disk_root=root/'disk-only';disk_root.mkdir(exist_ok=True);disk_source=disk_root/'unregistered.png';Image.new('RGB',(72,96),'orange').save(disk_source)
    count=window.library.count();original_path=window.path;window.workspace_mode.setCurrentIndex(2);panel=window.disk_browser;panel.navigate(str(disk_root))
    deadline=time.monotonic()+20
    while (panel.scan_job or not panel.model.rows) and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
    assert len(panel.model.rows)==1
    panel.view.setCurrentIndex(panel.proxy.index(0,0));deadline=time.monotonic()+20
    while panel.viewer.pixmap_item is None and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
    assert panel.viewer.image_rect.width()==72 and window.library.count()==count and window.path==original_path
    assert not window.store.db.execute('SELECT 1 FROM image_index WHERE path=?',(str(disk_source),)).fetchone()
    deadline=time.monotonic()+20
    while (str(disk_source) not in panel.icons or panel.thumb_job) and time.monotonic()<deadline:QApplication.processEvents();time.sleep(.01)
    shot=panel.view.viewport().grab().toImage();area=panel.view.visualRect(panel.proxy.index(0,0)).adjusted(12,6,-12,-34)
    assert any(shot.pixelColor(x,y).red()>200 and 100<shot.pixelColor(x,y).green()<200 and shot.pixelColor(x,y).blue()<50 for x in range(max(0,area.left()),min(shot.width(),area.right()),4) for y in range(max(0,area.top()),min(shot.height(),area.bottom()),4))
    assert all(size>0 for size in panel.split.sizes()) and panel.navigation.fs.isReadOnly()
    checks.append('explorer_first_paint_and_readonly_tree')
    window.workspace_mode.setCurrentIndex(0);checks.append('disk_folder_preview_no_registration')
    before=window.draft.toPlainText();window.main_tabs.setCurrentIndex(2);assert window.draft.isVisible()
    window.note_title.setText('Independent packaged note');window.draft.setPlainText('standalone note');window.main_tabs.setCurrentIndex(1);assert window.draft.toPlainText()==before
    from .note_transfer import NoteTransferDialog
    dialog=NoteTransferDialog(window,str(window.path),[('원본 프롬프트','prompt','bundle transfer',True)]);dialog.commit();assert dialog.saved_id
    body=json.loads(window.store.note(dialog.saved_id)[2]);assert body['prompt']=='bundle transfer' and body['_studio_image_transfers'][0]['source_image']==str(window.path)
    checks.append('top_tabs_note_isolation_and_explicit_save')
    window.thumbnail_slider.setValue(112);return checks
