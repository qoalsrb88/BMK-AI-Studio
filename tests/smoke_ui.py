"""Offscreen Qt smoke test: actual application widgets and persistence."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
from PySide6.QtWidgets import QApplication
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bmk_studio.app import Studio, configure_app

root=Path(tempfile.mkdtemp(prefix='bmk-ui-test-')).resolve()
image=Image.new('RGB',(900,1100),'#183344');draw=ImageDraw.Draw(image)
for y in range(1100):
    draw.line((0,y,900,y),fill=(20+int(y/55),48+int(y/32),68+int(y/30)))
draw.ellipse((180,120,720,660),fill='#ecc88c')
draw.polygon([(0,1000),(300,500),(500,840),(730,550),(900,950),(900,1100),(0,1100)],fill='#142a36')
meta=PngInfo();meta.add_text('parameters','mountain landscape, warm moonlight, quiet atmosphere\nNegative prompt: blur, low quality\nSteps: 24, Sampler: Euler, CFG scale: 6, Seed: 1234, Size: 900x1100')
path=root/'sample.png';image.save(path,pnginfo=meta)
app=QApplication([]);configure_app(app)
w=Studio(root/'data');w.show();w.add_paths([path]);app.processEvents()
assert 'mountain' in w.positive.toPlainText()
w.draft.setPlainText('edited draft');w.note_title.setText('Landscape / moonlight');w.save_note()
assert len(w.store.notes())==1
w.draft.setPlainText('1.2::red hair::');w.conversion.setCurrentText('NovelAI → ComfyUI');w.convert()
assert '(red hair:1.2)' in w.draft.toPlainText()
w.draft.undo();assert w.draft.toPlainText()=='1.2::red hair::'
w.set_box((100,100,200,300));w.apply_crop();assert w.current.size==(200,300)
w.undo();assert w.current.size==(900,1100)
w.copy_image();assert app.clipboard().mimeData().hasImage()
w.copy_file();assert app.clipboard().mimeData().hasUrls()
w.copy_text('clipboard test');assert app.clipboard().text()=='clipboard test'
w.viewer.display(w.current);w.tabs.setCurrentIndex(0);app.processEvents()
if len(sys.argv)>1:w.grab().save(sys.argv[1])
w.tabs.setCurrentIndex(3);app.processEvents()
if len(sys.argv)>1:w.grab().save(str(Path(sys.argv[1]).with_stem('preview-edit')))
w.close();app.processEvents()
assert 'comfy' not in sys.modules and 'folder_paths' not in sys.modules
print('PASS: Qt load, metadata, note save, crop, undo, three clipboard modes, no ComfyUI imports')
