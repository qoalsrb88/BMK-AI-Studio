"""100k disk records; no eager compressed thumbnails or metadata strings in the view."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from bmk_studio.core import Store
from bmk_studio.library_view import LibraryView

root=Path(tempfile.mkdtemp(prefix='bmk-paged-'));store=Store(root);blob=io.BytesIO();Image.new('RGB',(96,96),'red').save(blob,format='PNG');blob=blob.getvalue()
with store.db:store.db.executemany('INSERT INTO image_index VALUES(?,?,?,?)',((f'/synthetic/{i}.png','stamp',f'group{i%20} '+'metadata '*128,blob) for i in range(100000)))
app=QApplication([]);view=LibraryView(store.root/'library.sqlite3');start=time.monotonic();view.add_references(store.indexed_references());elapsed=time.monotonic()-start
assert view.count()==100000 and view.pages.reads==0
assert all(not item.blob and item.search==item.title.casefold() for item in view.records.rows)
view.resize(350,600);view.show();app.processEvents();assert len(view.pages.pages)<=8 and len(view.records.icons)<=256
for i in range(0,100000,3000):view.item(i).icon()
assert len(view.pages.pages)<=8 and sum(len(page) for page in view.pages.pages.values())<=512 and len(view.records.icons)<=256
ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(1)
view.set_query('group19 metadata');start=time.monotonic()
while view.search_pending and time.monotonic()-start<30:app.processEvents();time.sleep(.005)
assert not view.search_pending and view.proxy.rowCount()==5000 and ticks
view.set_query('group18');view.set_query('doesnotexist')
start=time.monotonic()
while view.search_pending and time.monotonic()-start<30:app.processEvents();time.sleep(.005)
assert view.proxy.rowCount()==0
# Deterministic completion race: thread exits while GUI delivery is deliberately paused.
view.set_query('group19 metadata');view.search_timer.stop();view.start_search()
assert view.search_job.wait(30000)
assert view.search_pending, 'Queued GUI results must still count as pending'
app.processEvents();assert view.proxy.rowCount()==5000 and not view.search_pending
timer.stop();view.stop_search();view.close();store.db.close()
print(f'PASS: 100,000 lightweight refs loaded in {elapsed:.2f}s; compressed pages <=512 records, decoded icons <=256; worker SQL metadata search, live timer and stale query suppression')
