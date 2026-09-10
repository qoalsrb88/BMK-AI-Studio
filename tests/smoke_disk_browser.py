"""Disk browser integration: navigation, isolated previews and explicit registration."""
import os,sys,time,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtCore import Qt,QItemSelectionModel
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint
root=Path(tempfile.mkdtemp(prefix='bmk-disk-')).resolve();folder=root/'images';folder.mkdir();(folder/'child').mkdir()
meta=PngInfo();meta.add_text('parameters','rainy city\nNegative prompt: blur\nSteps: 20, Seed: 1')
a=folder/'A.png';b=folder/'B.png';Image.new('RGB',(320,240),'red').save(a,pnginfo=meta);Image.new('RGB',(120,180),'blue').save(b);(folder/'text.txt').write_text('leave alone');Image.new('RGB',(20,20),'green').save(folder/'child/C.png')
hashes={str(p):fingerprint(p) for p in folder.rglob('*') if p.is_file()}
app=QApplication([]);configure_app(app);w=Studio(root/'user');w.resize(1400,900);w.show();errors=[];w.error=errors.append

def wait(check):
    end=time.monotonic()+25
    while time.monotonic()<end:
        app.processEvents();time.sleep(.01)
        if check():return
    raise AssertionError('Timeout '+str(errors))
w.workspace_mode.setCurrentIndex(2);d=w.disk_browser;assert d.isVisible() and not w.main_splitter.isVisible()
d.address.setText(str(folder));d.address.returnPressed.emit();wait(lambda:d.folder==str(folder) and not d.scan_job)
assert len(d.model.rows)==3 and w.library.count()==0
assert not w.store.db.execute('SELECT 1 FROM image_index').fetchone()
def index(name):
    return next(d.proxy.index(i,0) for i in range(d.proxy.rowCount()) if d.proxy.data(d.proxy.index(i,0),Qt.ItemDataRole.UserRole)[1]==name)
d.view.setCurrentIndex(index('A.png'));wait(lambda:'rainy city' in d.metadata.toPlainText())
assert d.viewer.image_rect.width()==320 and w.path is None and w.library.count()==0
wait(lambda:str(a) in d.icons);assert d.cache.is_dir()
d.search.setText('B');assert d.proxy.rowCount()==1;d.search.clear();d.sort.setCurrentIndex(1);assert d.proxy.data(d.proxy.index(0,0),Qt.ItemDataRole.UserRole)[2]
d.toggle_favorite();assert str(folder) in d.state['favorites']
d.activate(index('child'));wait(lambda:d.folder==str(folder/'child') and not d.scan_job);assert len(d.model.rows)==1
d.back.click();wait(lambda:d.folder==str(folder) and not d.scan_job);d.forward.click();wait(lambda:d.folder==str(folder/'child') and not d.scan_job)
next(b for b in d.findChildren(QPushButton) if b.text()=='↑ 상위').click();wait(lambda:d.folder==str(folder) and not d.scan_job)
d.navigate(str(root/'missing'));wait(lambda:not d.scan_job);assert d.folder==str(folder) and '열 수 없습니다' in d.status.text()
Image.new('RGB',(10,10),'white').save(folder/'new.png');d.navigate(d.folder,refresh=True);wait(lambda:not d.scan_job);assert len(d.model.rows)==4
# Rapid changes discard an obsolete scan and preview.
d.navigate(str(folder/'child'));d.navigate(str(folder));wait(lambda:not d.scan_job and d.folder==str(folder));assert len(d.model.rows)==4
d.view.setCurrentIndex(index('A.png'));d.view.setCurrentIndex(index('B.png'));wait(lambda:'B.png' in d.label.text() and d.viewer.image_rect.width()==120)
assert w.path is None and w.library.count()==0
# Register only the selected image; library editing state stays untouched.
d.add.click();wait(lambda:w.library.count()==1 and not w.jobs);assert str(b) in w.library_items and w.path is None
w.workspace_mode.setCurrentIndex(0);assert w.main_splitter.isVisible() and not d.isVisible();w.workspace_mode.setCurrentIndex(2);assert d.folder==str(folder)
d.size.setValue(200);w.grab().save(str(root/'disk-light.png'));d.save();w.workspace_mode.setCurrentIndex(0);wait(lambda:not w.jobs);w.close();app.processEvents()
w=Studio(root/'user');w.show();w.workspace_mode.setCurrentIndex(2);d=w.disk_browser;wait(lambda:d.folder==str(folder) and not d.scan_job);assert str(folder) in d.state['favorites'] and d.size.value()==200 and w.library.count()==1
assert all(fingerprint(p)==h for p,h in hashes.items());assert {p.name for p in folder.iterdir()}=={'child','A.png','B.png','text.txt','new.png'}
w.close();wait(lambda:not w.jobs);app.processEvents();assert not errors,errors
print('PASS: address/history/parent-folder navigation, refresh, filters/sort, lazy thumbnails, metadata, stale results, favorites/restart, explicit-only registration, source preservation. Capture:',root/'disk-light.png')
