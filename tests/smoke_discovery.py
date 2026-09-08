"""Qt follow-up UX plus optional real multilingual ONNX inference."""
import os,sys,json,tempfile,time,io
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,PngImagePlugin
from PySide6.QtCore import Qt,QTimer,QMimeData,QPoint,QPointF,QDate
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QDateEdit,QComboBox,QCheckBox,QPushButton,QLineEdit,QListWidget,QTreeWidget,QInputDialog
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint
from bmk_studio.collection_drop import MIME
from bmk_studio.background import JobCenter

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-discovery-'));w=Studio(root/'user');w.show();errors=[];w.error=errors.append
def drain():
    deadline=time.monotonic()+40
    while (w.jobs or w.library.search_pending or w.library.large.timer.isActive()) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    app.processEvents();assert not w.jobs and not w.library.search_pending and not errors,errors
paths=[]
for n,prompt in enumerate(['A rainy city street at night with neon lights','A sunny beach with blue sea','A cute cat sleeping on a sofa']):
    image=Image.new('RGB',(600,800),'#60a5b0' if n<2 else '#b03020');ImageDraw.Draw(image).ellipse((30,80,500,600),fill='#193547')
    metadata=PngImagePlugin.PngInfo();metadata.add_text('parameters',prompt+'\nNegative prompt: blur\nSteps: 20, Seed: 1')
    if n<2:metadata.add_text('Creation Time',f'2026-09-0{n+1}T12:00:00Z')
    path=root/f'{n}.png';image.save(path,pnginfo=metadata);paths.append(str(path))
hashes=[fingerprint(p) for p in paths];w.add_paths(paths);drain()
w.search.setText('rai');w.request_completion();drain();assert 'rainy' in w.completion_model.stringList();w.completer.popup().hide();w.clear_browser_filters();drain()
def dates():
    dialog=app.activeModalWidget();kind=dialog.findChild(QComboBox);kind.setCurrentIndex(kind.findData('generated'))
    boxes=dialog.findChildren(QCheckBox);boxes[0].setChecked(True)
    dates=dialog.findChildren(QDateEdit);dates[0].setDate(QDate(2026,9,1));dates[1].setDate(QDate(2026,9,1))
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
QTimer.singleShot(100,dates);w.date_dialog();drain();assert w.library.proxy.rowCount()==1
w.date_filters={'date_kind':'generated','date_unknown':True};w.apply_browser_filters();drain();assert w.library.proxy.rowCount()==1 and w.library.proxy.index(0,0).data(Qt.ItemDataRole.UserRole)==paths[2]
w.clear_browser_filters();drain()
with patch.object(QInputDialog,'getText',return_value=('Drop collection',True)):w.new_collection()
w.collection_drop.show();app.processEvents();mime=QMimeData();mime.setData(MIME,json.dumps(paths[:2]+['not-a-library-file']).encode());position=w.collection_drop.visualItemRect(w.collection_drop.item(0)).center()
enter=QDragEnterEvent(position,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);app.sendEvent(w.collection_drop.viewport(),enter);assert enter.isAccepted()
drop=QDropEvent(QPointF(position),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier);app.sendEvent(w.collection_drop.viewport(),drop);assert drop.isAccepted()
assert w.store.db.execute('SELECT count(*) FROM collection_items').fetchone()[0]==2
w.delete_collection('Drop collection');w.undo_deleted_collection();drain();assert w.library.proxy.rowCount()==2
w.clear_browser_filters();w.thumbnail_slider.setValue(384);app.processEvents();drain()
blobs=w.store.db.execute('SELECT thumbnail FROM large_thumbnails').fetchall();assert blobs
assert all(160<max(Image.open(io.BytesIO(blob)).size)<=512 for blob, in blobs)
assert len(w.library.records.icons)<=64
# Similar groups show candidates and explicitly select the group in the gallery.
timer=QTimer();timer.setInterval(20)
def dismiss_similarity():
    dialog=app.activeModalWidget()
    if dialog and dialog.windowTitle()=='시각적으로 비슷한 후보':
        tree=dialog.findChild(QTreeWidget);assert tree.topLevelItemCount()==1;tree.setCurrentItem(tree.topLevelItem(0))
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='선택 후보를 갤러리에서 보기').click()
timer.timeout.connect(dismiss_similarity);timer.start()
with patch.object(QInputDialog,'getInt',return_value=(8,True)):w.find_similar()
drain();timer.stop();assert w.library.proxy.rowCount()==2
w.clear_browser_filters();drain()
# Safe cancellation through the common job center.
outcomes=[]
def slow(job):
    while not job.isInterruptionRequested():job.msleep(5)
    return True
job=w.run_discovery('cancel probe',slow,outcomes.append);center=JobCenter(w)
def cancel():
    center.refresh()
    for n in range(center.tree.topLevelItemCount()):
        item=center.tree.topLevelItem(n)
        if item.data(0,Qt.ItemDataRole.UserRole)==id(job):center.tree.setCurrentItem(item);break
    center.cancel();center.accept()
QTimer.singleShot(20,cancel);center.exec();drain();assert outcomes==[True]
# Cancelling an index job must also stop the remaining batches.
from bmk_studio.library import IndexJob
def hold_index(job):
    while not job.isInterruptionRequested():job.msleep(5)
with patch.object(IndexJob,'run',hold_index):
    w.pending_index={str(root/f'queued-{n}.png') for n in range(80)};w.start_index();job=w.index_job;center=JobCenter(w)
    QTimer.singleShot(20,cancel);center.exec();drain();assert not w.pending_index and w.index_job is None and w.index_cancelled
w.add_paths(paths,False);drain();assert not w.index_cancelled
# A worker can start while the data-folder dialog is open; do not copy concurrently.
transfer_jobs=[]
def folder_with_worker():
    dialog=app.activeModalWidget();transfer_jobs.append(w.run_discovery('transfer guard',slow,lambda result:None))
    dialog.target.setText(str(root/'not-activated'));dialog.controls.button(QDialogButtonBox.StandardButton.Save).click()
QTimer.singleShot(0,folder_with_worker);assert not w.change_data_directory()
assert errors and not w.library.stopped and not w.location_config.exists();errors.clear()
transfer_jobs[0].requestInterruption();drain()
def cancelled_download(job):
    while not job.isInterruptionRequested():job.msleep(5)
    raise RuntimeError('취소된 다운로드 실험')
cancelled=w.run_discovery('download cancel probe',cancelled_download,lambda result:None);cancelled.requestInterruption();drain()
assert w.completed_jobs[-1]==('download cancel probe','취소됨')
if '--model' in sys.argv:
    w.search.setText('a');drain();assert w.library.proxy.rowCount()==3
    model=str(Path(sys.argv[sys.argv.index('--model')+1]).resolve());results=[]
    def semantic_input():
        dialog=app.activeModalWidget();edits=dialog.findChildren(QLineEdit);edits[0].setText('비 오는 밤의 도시 거리');edits[1].setText(model)
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='현재 갤러리 결과 안에서 검색').click()
    def semantic_result():
        dialog=app.activeModalWidget()
        if dialog and dialog.windowTitle()=='의미 검색 결과':
            items=dialog.findChild(QListWidget);results.append(items.item(0).data(Qt.ItemDataRole.UserRole) if items.count() else None);dialog.accept()
    timer.timeout.disconnect();timer.timeout.connect(semantic_result);timer.start();QTimer.singleShot(0,semantic_input);w.semantic_dialog();drain();timer.stop()
    assert results==[paths[0]],results
w.clear_browser_filters();drain()
w.collection_drop.hide();app.processEvents();w.grab().save(str(root/'discovery.png'));assert hashes==[fingerprint(p) for p in paths]
w.delete_collection('Drop collection');w.save_draft();drain();w.close();app.processEvents();w=Studio(root/'user');w.show();drain();w.undo_deleted_collection();drain()
assert w.library.proxy.rowCount()==2 and w.store.state('last_deleted_collection')=={}
w.close();app.processEvents();print('PASS: autocomplete, explicit/unknown date range, real collection MIME drop, persistent delete undo, 512px cache, visual groups, job-center cancellation, originals, restart'+(' and real Korean/English semantic ranking' if '--model' in sys.argv else '')+'; captures: '+str(root))
