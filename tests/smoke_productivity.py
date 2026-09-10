import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QFileDialog
from PIL import Image
from bmk_studio.app import Studio,configure_app
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
w.close();app.processEvents()
print('PASS: structured field edits retain unknown keys and no-op identity; extra-only note autosaved; wildcard save/seeded preview invalidation; actual export applies naming template with separate metadata')
