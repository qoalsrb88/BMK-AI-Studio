import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,tempfile,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint,file_stamp
from bmk_studio.library_view import LibraryView

app=QApplication([]);configure_app(app)
view=LibraryView();view.resize(350,600)
buffer=io.BytesIO();Image.new('RGB',(96,96),'red').save(buffer,format='PNG');blob=buffer.getvalue()
start=time.perf_counter()
for i in range(20000):
    item=view.add_path(f'/synthetic/{i}.png',f'Image {i}');view.update_item(item,search=f'group{i%20} sample{i}',blob=blob)
insert_time=time.perf_counter()-start
assert view.records.decode_count==0
view.show();app.processEvents();assert len(view.records.icons)<256
start=time.perf_counter();view.set_query('group19 sample');app.processEvents();filter_time=time.perf_counter()-start
assert view.proxy.rowCount()==1000
view.set_query('nomatch');assert view.proxy.rowCount()==0
view.close()
root=Path(tempfile.mkdtemp(prefix='bmk-library-')).resolve();path=root/'image.png';Image.new('RGB',(64,64)).save(path);before=fingerprint(path)
w=Studio(root/'data');w.add_paths([path]);w.show()
def wait():
    deadline=time.monotonic()+15
    while (w.jobs or w.library.search_pending) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not w.jobs and not w.library.search_pending
wait();w.draft.setPlainText('privateworkterm');w.save_draft();w.search.setText('privateworkterm');wait();assert w.library.proxy.rowCount()==1
result={'scores':[{'tag':'red_hair','category':0,'score':.9},{'tag':'unlikely','category':0,'score':.01}]}
w.store.record_tag_run(path,'fake',file_stamp(path),'cache',result)
w.update_library_search(str(path));w.search.setText('red hair');wait();assert w.library.proxy.rowCount()==1
w.search.setText('unlikely');wait();assert w.library.proxy.rowCount()==0
w.search.clear();record=w.store.indexed_images()[0];w.remove_library_paths([path]);w.index_ready(record)
assert w.library.count()==0 and fingerprint(path)==before and w.store.asset(path)[0]=='privateworkterm'
w.add_paths([path],False,False);assert w.library.count()==0
w.close();app.processEvents();w=Studio(root/'data');assert w.library.count()==0
w.add_paths([path]);wait();assert w.library.count()==1
w.search.setText('red hair');wait();assert w.library.proxy.rowCount()==1
w.close();app.processEvents()
print(f'PASS: 20,000 records, lazy bounded thumbnail cache; insertion {insert_time:.2f}s, filter {filter_time:.2f}s; work/tag search; remove/restart/stale-index/watch exclusion; explicit re-add; source hash preserved')
