"""Packaged smoke gate; creates no records in the user's normal library."""
import json,sys,tempfile,time,traceback
from pathlib import Path

def run(args):
    global _application
    report=Path(args[0]).resolve();result={'passed':False,'frozen':bool(getattr(sys,'frozen',False))}
    try:
        import numpy as np
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo
        from PySide6.QtWidgets import QApplication
        from .app import Studio,configure_app
        from .core import fingerprint,save_derived,stitch_image,tone_restore
        from . import __version__
        from .update_network import configure_update_tls
        from PySide6.QtNetwork import QSslSocket
        configure_update_tls()
        assert QSslSocket.supportsSsl(), 'Packaged TLS backend unavailable'
        result['tls_backend']=QSslSocket.activeBackend()
        root=Path(tempfile.mkdtemp(prefix='bmk-bundle-test-')).resolve();result['data']=str(root);result['version']=__version__
        app=QApplication([]);_application=app;configure_app(app);w=Studio(root/'data');errors=[];w.error=errors.append;w.show()
        def wait(seconds=120):
            end=time.monotonic()+seconds
            while (w.jobs or w.library.search_pending) and time.monotonic()<end:app.processEvents();time.sleep(.02)
            if w.jobs or w.library.search_pending:raise RuntimeError('Background job timed out')
            if errors:raise RuntimeError('; '.join(errors))
        source=root/'sample.png';meta=PngInfo();meta.add_text('parameters','bird, blue sky\nNegative prompt: blur\nSteps: 20, Seed: 42')
        Image.new('RGB',(320,240),'#316c80').save(source,pnginfo=meta);before=fingerprint(source)
        w.add_paths([source]);wait();assert w.positive.toPlainText()=='bird, blue sky'
        from .advanced_diagnostics import run as advanced
        gpu_checks=False
        if '--model' in args:
            import torch
            gpu_checks=torch.cuda.is_available()
        result['advanced_checks']=advanced(root,w,gpu_checks);wait()
        from .discovery_diagnostics import run as discovery
        result['discovery_checks']=discovery(root,w,args[args.index('--semantic-model')+1] if '--semantic-model' in args else None);wait()
        assert w.library.count()==1 and not w.library_items[str(source)].icon().isNull()
        w.search.clear();result['advanced_checks'].append('disk_search_thumbnail')
        nid=w.store.save_note('diagnostic',{'prompt':'one','extra':{'keep':True}});w.open_note_id(nid);w.draft.setPlainText('two');w.save_draft();w.activate_document(0)
        w.set_box((20,30,80,100));w.apply_crop();assert w.current.size==(80,100)
        export=save_derived(w.current,root/'crop.png',{'source':str(source)})
        assert Path(str(export)+'.bmk.json').is_file()
        combined=stitch_image(Image.open(source),Image.new('RGBA',(80,100),(200,0,0,200)),(20,30,80,100),feather=4,offset=(2,3),angle=5)
        w.current=tone_restore(combined,Image.open(source),.3,3);w.crop_context=None;w.operations.append({'diagnostic_stitch':True})
        assert w.save_edit_session();w.copy_image();assert app.clipboard().mimeData().hasImage()
        if '--model' in args:
            model=args[args.index('--model')+1];w.model_path.setText(model);w.start_tags([str(source)]);wait()
            if not w.scores or len(w.scores['scores'])<=1000:
                raise RuntimeError('Tagging failed: '+w.job_log.toPlainText()+' | '+w.tag_status.text())
            result['gpu']={'device':str(w.tagger.device),'scores':len(w.scores['scores'])}
        assert fingerprint(source)==before
        expected=np.asarray(w.current).copy();w.grab().save(str(root/'application.png'));w.close();app.processEvents()
        from .data_location import activate_directory
        migration=activate_directory(root/'data',root/'migrated-data',True,root/'startup-location.json')
        assert migration['copied']>0 and (root/'data/library.sqlite3').is_file()
        w=Studio(root/'migrated-data');np.testing.assert_array_equal(np.asarray(w.current),expected)
        result['advanced_checks'].append('custom_data_copy_restart')
        assert json.loads(w.store.note(nid)[2])['extra']=={'keep':True};w.close();app.processEvents()
        assert 'folder_paths' not in sys.modules and 'comfy' not in sys.modules
        if getattr(sys,'frozen',False):
            bundle=Path(sys._MEIPASS).resolve()
            for name in ('bmk_studio.app','numpy','PIL','PySide6','OpenEXR','imagecodecs','tifffile','png'):
                Path(sys.modules[name].__file__).resolve().relative_to(bundle)
            if '--semantic-model' in args:
                for name in ('onnxruntime','tokenizers'):Path(sys.modules[name].__file__).resolve().relative_to(bundle)
        app.clipboard().clear();app.processEvents()
        result['passed']=True;result['checks']=['metadata','index','notes','crop_export','aligned_stitch','tone','checkpoint_restart','clipboard','source_hash','isolated_imports']
    except Exception:result['error']=traceback.format_exc()
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
