"""Windows bundle entry point; diagnostics use isolated synthetic data."""
import multiprocessing
import sys
import os
import traceback
from pathlib import Path

if __name__=='__main__':
    multiprocessing.freeze_support()
    if len(sys.argv)==3 and sys.argv[1]=='--apply-update':
        from bmk_studio.update_install import main as apply_update
        sys.exit(apply_update(sys.argv[2]))
    if '--self-test' in sys.argv:
        os.environ['QT_QPA_PLATFORM']='offscreen'
        from bmk_studio.diagnostics import run
        sys.exit(run(sys.argv[sys.argv.index('--self-test')+1:]))
    try:
        from bmk_studio.app import main
        main()
    except Exception:
        root=Path(os.environ.get('BMK_STUDIO_DATA',Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BMK-AI-Studio'))
        root.mkdir(parents=True,exist_ok=True);log=root/'startup-error.log';log.write_text(traceback.format_exc(),encoding='utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(log),'BMK AI Studio 시작 오류',16)
        sys.exit(1)
