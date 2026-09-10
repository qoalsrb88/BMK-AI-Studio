import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtWidgets import QApplication
from bmk_studio.app import Studio,configure_app

app=QApplication([]);configure_app(app);root=Path(tempfile.mkdtemp(prefix='bmk-safe-edit-')).resolve()
a=root/'a.png';b=root/'b.png';Image.new('RGB',(100,100),'red').save(a);Image.new('RGB',(120,80),'blue').save(b)
w=Studio(root/'data');w.load(a);assert not w.image_dirty()
w.set_box((5,5,50,50));w.apply_crop();assert w.image_dirty()
with patch.object(w,'confirm_image_change',return_value=False):
    assert w.load(b) is False and w.path==a and w.current.size==(50,50)
with patch('bmk_studio.app.QFileDialog.getSaveFileName',return_value=(str(root/'export.png'),'PNG')):
    assert w.export_image() and not w.image_dirty()
assert (root/'export.png.bmk.json').is_file()
w.load(b);assert w.path==b and not w.image_dirty()
w.close();app.processEvents()
print('PASS: unsaved image navigation cancellation, export checkpoint, successful navigation after export')
