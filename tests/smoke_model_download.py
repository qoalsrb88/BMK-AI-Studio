"""Real HTTP/Qt worker installation using tiny synthetic model files."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time,threading,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from safetensors.numpy import save_file
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from bmk_studio.model_dialog import ModelDownloadDialog
from bmk_studio.model_download import install_model,official_manifest,download_file

root=Path(tempfile.mkdtemp(prefix='bmk-download-')).resolve();source=root/'http';source.mkdir()
(source/'config.json').write_text(json.dumps({'architecture':'synthetic-test-only'}));(source/'selected_tags.csv').write_text('name,category\ntest,0\n')
save_file({'weight':np.ones((2,2),dtype=np.float32)},str(source/'model.safetensors'))
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(source)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
manifest={'repo':'SmilingWolf/wd-eva02-large-tagger-v3','revision':'a'*40,'files':[]}
for file in source.iterdir():manifest['files'].append({'name':file.name,'size':file.stat().st_size,'algorithm':'sha256','digest':hashlib.sha256(file.read_bytes()).hexdigest(),'url':f'http://127.0.0.1:{server.server_port}/{file.name}'})
app=QApplication([]);dialog=ModelDownloadDialog(root/'models');dialog.manifest=manifest;dialog.show();ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(1)
try:
    dialog.start(True);end=time.monotonic()+20
    while dialog.job and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert dialog.job is None and dialog.installed,dialog.status.text()
    assert ticks and dialog.use.isEnabled()
    target=Path(dialog.installed);assert (target/'install_manifest.json').exists()
    assert install_model(root/'models',manifest)==str(target)
    (target/'config.json').write_text('keep existing corruption')
    try:install_model(root/'models',manifest);raise AssertionError('Should refuse existing corrupt installation')
    except ValueError:pass
    assert (target/'config.json').read_text()=='keep existing corruption'
finally:timer.stop();dialog.close();server.shutdown();server.server_close()
if '--online' in sys.argv:
    manifest=official_manifest('SmilingWolf/wd-eva02-large-tagger-v3')
    entry=next(file for file in manifest['files'] if file['name']=='config.json')
    download_file(entry,root/'official-config.json');assert json.loads((root/'official-config.json').read_text())['architecture']
    print('PASS: official anonymous metadata + immutable-revision config download + Git blob hash')
print('PASS: local HTTP download/install in Qt worker; live timer; safetensors validation; installed reuse; existing corrupt folder protected')
