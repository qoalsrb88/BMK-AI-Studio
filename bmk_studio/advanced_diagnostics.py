"""Exercise optional codecs and new modules from within the frozen runtime."""
import hashlib
import numpy as np
from PIL import Image

def run(root,window,gpu=False):
    import OpenEXR,png,tifffile
    from safetensors.numpy import save_file
    from .color import native_pixels,normalize_source,srgb_profile
    from .core import fingerprint,save_derived,tone_restore
    from .gpu_tone import tone_restore_cuda
    from .metadata import comfy_branches
    from .model_download import verify_file
    from .model_dialog import ModelDownloadDialog
    from .note_fields import NoteFieldsDialog
    from .prompt_tools import expand_wildcards,export_stem
    checks=[]
    pixels=np.arange(4*5*3,dtype=np.uint16).reshape(4,5,3)*1000
    for codec in ('lzw','deflate','zstd'):
        path=root/(codec+'.tif');tifffile.imwrite(path,pixels,photometric='rgb',compression=codec)
        np.testing.assert_array_equal(native_pixels(path)[0],pixels)
    path=root/'16bit.png'
    with path.open('wb') as stream:png.Writer(5,4,greyscale=False,bitdepth=16).write(stream,pixels.reshape(4,-1))
    np.testing.assert_array_equal(native_pixels(path)[0],pixels)
    path=root/'hdr.exr';values=np.full((4,5,3),4.,np.float32)
    with OpenEXR.File({}, {'RGB':values}) as file:file.write(str(path))
    before=fingerprint(path);image,record=normalize_source(path,mode='hdr')
    target=save_derived(image,root/'normalized.png',record)
    with Image.open(target) as exported:assert exported.info['icc_profile'] and 225<exported.getpixel((0,0))[0]<240
    assert fingerprint(path)==before
    icc=root/'icc.png';Image.new('RGBA',(5,4),(40,90,160,100)).save(icc,icc_profile=srgb_profile())
    assert normalize_source(icc)[0].getpixel((0,0))==(40,90,160,100)
    checks.extend(['compressed_tiff_codecs','16bit_png','exr_sdr_export','icc_alpha'])
    wild=root/'wildcards';wild.mkdir();(wild/'color.txt').write_text('red\nblue',encoding='utf-8')
    assert expand_wildcards('__color__ dress',wild,3)[0] in ('red dress','blue dress')
    assert export_stem('{source}_{width}x{height}','one.png',(5,4))=='one_5x4'
    doc={'prompt':'','loras':[{'name':'x','weight':1.,'enabled':True,'unknown':[1]}]}
    fields=NoteFieldsDialog(doc);assert fields.document()==doc;fields.close()
    dialog=ModelDownloadDialog(root/'models');dialog.close()
    weights=root/'tiny.safetensors';save_file({'w':np.ones((2,2),np.float32)},str(weights))
    assert verify_file(weights,{'size':weights.stat().st_size,'algorithm':'sha256','digest':hashlib.sha256(weights.read_bytes()).hexdigest()})
    checks.extend(['wildcards_naming','structured_notes','model_dialog_safetensors'])
    branches=comfy_branches({'prompt':{'c':{'class_type':'CLIPTextEncode','inputs':{'text':['s',0]}},'s':{'class_type':'ComfySwitchNode','inputs':{'switch':True,'on_true':'chosen','on_false':['s',0]}},'k':{'class_type':'KSampler','inputs':{'positive':['c',0],'seed':1}}}})
    assert branches[0]['positive'][0]['text']=='chosen' and not branches[0]['warnings']
    checks.append('dynamic_switch')
    from PySide6.QtCore import Qt,QPointF
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    window.crop_toggle.setChecked(True);viewer=window.viewer;viewer.actual_size();QApplication.processEvents()
    start=viewer.mapFromScene(QPointF(20,20));finish=viewer.mapFromScene(QPointF(180,160))
    QTest.mousePress(viewer.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
    QTest.mouseMove(viewer.viewport(),finish);QApplication.processEvents()
    assert window.box==(20,20,160,140) and viewer.crop_rect==window.box
    QTest.mouseRelease(viewer.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,finish)
    window.crop_toggle.setChecked(False);window.set_box((0,0,*window.current.size));viewer.fit()
    checks.append('interactive_crop_live')
    if gpu:
        a=Image.new('RGBA',(23,19),(50,60,70,128));b=Image.new('RGB',(23,19),(90,80,70))
        np.testing.assert_allclose(np.asarray(tone_restore_cuda(a,b,.7,4)),np.asarray(tone_restore(a,b,.7,4)),atol=1)
        checks.append('cuda_tone')
    window.thumbnail_slider.setValue(112)
    window.search.setText('bird')
    checks.append('thumbnail_slider')
    return checks
