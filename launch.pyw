import sys
import traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    from bmk_studio.app import main
    main()
except Exception:
    import os
    root=Path(os.environ.get('BMK_STUDIO_DATA',Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BMK-AI-Studio'))
    root.mkdir(parents=True,exist_ok=True)
    (root/'startup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
    import ctypes
    ctypes.windll.user32.MessageBoxW(None,str(root/'startup-error.log'),'BMK AI Studio 시작 오류',16)
