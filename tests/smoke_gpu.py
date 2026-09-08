import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app

app=QApplication([]);configure_app(app)
w=Studio(Path(tempfile.mkdtemp(prefix='bmk-gpu-ui-')))
errors=[];w.error=errors.append
w.add_paths([sys.argv[1]]);w.model_path.setText(sys.argv[2]);w.run_tags()
deadline=time.monotonic()+90
while w.jobs and time.monotonic()<deadline:
    app.processEvents();time.sleep(.02)
assert not w.jobs, 'Tagger timed out'
assert not errors, errors
assert w.scores and len(w.scores['scores'])>1000
assert w.tag_list.count()>0
assert w.store.db.execute('select count(*) from tags').fetchone()[0]==1
w.run_tags()
while w.jobs and time.monotonic()<deadline:app.processEvents();time.sleep(.02)
assert w.last_batch_summary['cached']==1, 'Second run should use score cache'
w.unload_tagger();assert w.tagger.loaded is None
w.close();app.processEvents()
print('PASS: GUI background GPU inference, score display, SQLite cache, cached rerun, model unload')
