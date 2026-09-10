"""Run a frozen application with an isolated profile and OS-only PATH."""
import argparse,json,os,subprocess
from pathlib import Path

def probe(bundle, output):
    bundle=Path(bundle).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError('Choose a new evidence directory')
    output.mkdir(parents=True)
    env=os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH','BMK_STUDIO_DATA','CUDA_VISIBLE_DEVICES'):
        env.pop(key,None)
    env['PATH']=str(Path(os.environ['WINDIR'])/'System32')
    env['QT_QPA_PLATFORM']='offscreen'
    env['BMK_STUDIO_DATA']=str(output/'private-profile')
    env['CUDA_VISIBLE_DEVICES']='-1'
    report=output/'diagnostic.json'
    result=subprocess.run([str(bundle/'BMK-AI-Studio.exe'),'--self-test',str(report)],
                          cwd=output,env=env,capture_output=True,timeout=300)
    (output/'output.log').write_bytes(result.stdout+result.stderr)
    data=json.loads(report.read_text(encoding='utf-8'))
    passed=result.returncode==0 and data.get('passed') is True and data.get('frozen') is True
    receipt={'passed':passed,'exit':result.returncode,'cuda_hidden':True,'isolated_path':True,
             'another_physical_pc':False,'version':data.get('version')}
    (output/'probe.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))
    if not passed:raise RuntimeError('Frozen compatibility probe failed')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle');parser.add_argument('output')
    args=parser.parse_args();probe(args.bundle,args.output)

