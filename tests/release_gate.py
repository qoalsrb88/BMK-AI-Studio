"""Run source release checks with bounded subprocesses and durable evidence."""
import json,subprocess,sys,time,os
from pathlib import Path

root=Path(__file__).resolve().parents[1]
model=sys.argv[1] if len(sys.argv)>1 else None
checks=[('unit',['-m','unittest','discover','-s','tests','-v'])]
names=['ui','cancel','editors','edit_safety','documents','library','sessions','stitch','ux','recovery','relink','productivity','model_download','queue','color','paged_library','crop','data_location']
checks += [(name,['tests/smoke_'+name+'.py']) for name in names]
checks += [('samples',['tests/smoke_samples.py',str(root/'ImageSample')])]
if model:
    checks += [(name,['tests/smoke_'+name+'.py',model]) for name in ('precision','workflow')]
    checks += [('gpu_tone',['tests/smoke_gpu_tone.py'])]
report=[];out=root/os.environ.get('BMK_VALIDATION_FOLDER','validation-current');out.mkdir(exist_ok=True)
for name,args in checks:
    start=time.monotonic()
    try:
        result=subprocess.run([sys.executable,*args],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
        (out/(name+'.log')).write_bytes(result.stdout)
        report.append({'name':name,'exit':result.returncode,'seconds':round(time.monotonic()-start,2)})
    except subprocess.TimeoutExpired as exc:
        (out/(name+'.log')).write_bytes(exc.stdout or b'')
        report.append({'name':name,'exit':'timeout','seconds':240})
    (out/'source-gate.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(name,report[-1]['exit'],flush=True)
sys.exit(int(any(row['exit']!=0 for row in report)))
