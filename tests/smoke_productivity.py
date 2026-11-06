import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,copy,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QFileDialog
from PIL import Image
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import NOTE_IMPORT_CONFIRM
from bmk_studio.note_fields import NoteFieldsDialog
from bmk_studio.wildcard_dialog import WildcardDialog

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-productivity-')).resolve()
doc={'prompt':'original','loras':[{'name':'test','weight':1.0,'enabled':True,'unknown':{'x':[1,False]}}],'params':[{'node':'12','widget':'seed','type':'int','value':42,'future':'preserved'}],'ui':{'order':['prompt','loras'],'collapsed':{'future':True},'unknown':[1]},'extra':{'original':True}}
before=copy.deepcopy(doc);dialog=NoteFieldsDialog(doc)
assert dialog.document()==doc
dialog.loras.table.item(0,1).setText('0.75');dialog.params.table.item(0,4).setText('123')
dialog.flags['collapsed','prompt'][0].setChecked(True);dialog.save();result=dialog.result
assert result['loras'][0]['weight']==.75 and result['loras'][0]['unknown']==doc['loras'][0]['unknown']
assert result['params'][0]['value']==123 and result['params'][0]['future']=='preserved'
assert result['ui']['collapsed']=={'future':True,'prompt':True} and doc==before
wildcard=WildcardDialog(root/'wildcards','__color__ outfit','negative')
wildcard.name.setText('color');wildcard.entries.setPlainText('red\nblue');wildcard.save_file();wildcard.preview()
assert wildcard.result in ('red outfit','blue outfit') and wildcard.apply.isEnabled()
wildcard.target.setCurrentIndex(1);assert not wildcard.apply.isEnabled();wildcard.preview();assert wildcard.result=='negative'
w=Studio(root/'data');w.new_note()
def fill_note():
    dialog=app.activeModalWidget();dialog.loras.append({'name':'only LoRA','weight':1.0,'enabled':True});dialog.save()
QTimer.singleShot(0,fill_note);w.edit_note_fields();assert w.note_id and w.note_body()['loras'][0]['name']=='only LoRA'
source=root/'source.png';Image.new('RGB',(20,30)).save(source);w.load(source)
w.appearance['export_pattern']='{source}_{width}x{height}'
captured=[];original=QFileDialog.getSaveFileName
QFileDialog.getSaveFileName=lambda *args:(captured.append(args[2]) or str(root/'output.png'),'PNG')
try:assert w.export_image()
finally:QFileDialog.getSaveFileName=original
assert Path(captured[0]).name=='source_20x30.png' and (root/'output.png.bmk.json').exists()
# Note folder import: large imports ask first, trash/settings/workflows are skipped, re-import creates nothing.
folder=root/'bmk_notes';(folder/'.trash').mkdir(parents=True)
for i in range(NOTE_IMPORT_CONFIRM):(folder/f'note{i}.json').write_text(json.dumps({'prompt':f'p{i}','negative':'','notes':''}),encoding='utf-8')
(folder/'.bmk_meta.json').write_text('{"categories":[]}',encoding='utf-8');(folder/'.trash'/'gone.json').write_text('{"prompt":"x","negative":"","notes":""}',encoding='utf-8')
(folder/'workflow.json').write_text('{"nodes":[],"links":[]}',encoding='utf-8')
asked=[];reports=[];answer=[False];count=len(w.store.note_entries())
w.confirm_note_import=lambda plan:asked.append(plan) or answer[0]
w.show_note_import_report=lambda message,details:reports.append((message,details))
def import_and_wait():
    w.import_note_paths(None,str(folder));deadline=time.monotonic()+60
    while w.jobs:app.processEvents();time.sleep(.01);assert time.monotonic()<deadline
    app.processEvents();return w.statusBar().currentMessage()
assert '취소' in import_and_wait() and len(asked)==1 and len(asked[0]['import'])==NOTE_IMPORT_CONFIRM and asked[0]['base']==str(folder)
assert len(w.store.note_entries())==count and not reports
answer[0]=True;status=import_and_wait()
assert status==f'노트 가져오기: 성공 {NOTE_IMPORT_CONFIRM}개 / 건너뜀 3개 / 실패 0개',status
assert len(w.store.note_entries())==count+NOTE_IMPORT_CONFIRM and not any(r[1]=='gone' for r in w.store.note_entries())
assert len(reports)==1 and status in reports[0][0] and 'ComfyUI 워크플로' in reports[0][0] and '.trash' in reports[0][1]
status=import_and_wait()
assert len(asked)==2 and status==f'노트 가져오기: 성공 0개 / 건너뜀 {NOTE_IMPORT_CONFIRM+3}개 / 실패 0개',status
assert len(w.store.note_entries())==count+NOTE_IMPORT_CONFIRM and len(reports)==2
w.close();app.processEvents()
print('PASS: structured field edits retain unknown keys and no-op identity; extra-only note autosaved; wildcard save/seeded preview invalidation; actual export applies naming template with separate metadata; note folder import confirmation, skip report and no duplicate re-import')
