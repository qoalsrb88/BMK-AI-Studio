"""Repeatable source validation; no private profile or local model required."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SMOKES=('updates','ui','ux','browser','discovery','disk_browser','explorer_reflow','main_tabs','crop','data_location','documents','edit_safety','editors','sessions','stitch','library','paged_library','recovery','relink','queue','productivity','model_download','color','cancel')
def main():
    env=os.environ.copy();env['QT_QPA_PLATFORM']='offscreen'
    commands=[('unit',[sys.executable,'-m','unittest','discover','-s','tests'])]+[(name,[sys.executable,f'tests/smoke_{name}.py']) for name in SMOKES]
    for name,command in commands:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
        output=result.stdout.decode('utf-8',errors='replace');print(name, 'PASS' if result.returncode==0 else 'FAIL',flush=True)
        if result.returncode or 'Traceback' in output:print(output);return 1
    print('Unit tests and 24 Qt suites passed. GPU/model and bundled tests are separate.');return 0
if __name__=='__main__':sys.exit(main())
