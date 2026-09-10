"""Install, validate, reject overwrite, uninstall; retain user-created sentinel files."""
import argparse,json,subprocess,time
from pathlib import Path
from package_release import inspect_bundle,digest
from probe_bundle import probe

def validate(installer,bundle,evidence):
    installer=Path(installer).resolve();bundle=Path(bundle).resolve();evidence=Path(evidence).resolve()
    if evidence.exists():raise FileExistsError('Choose a new evidence directory')
    evidence.mkdir(parents=True)
    target=evidence/'installed';target.mkdir()
    report=inspect_bundle(bundle)
    args=[str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/DIR='+str(target)]
    install=subprocess.run(args+['/LOG='+str(evidence/'install.log')],timeout=300)
    if install.returncode:raise RuntimeError('Installation failed')
    for item in report['files']:
        if digest(target/item['path'])!=item['sha256']:raise RuntimeError('Installed content differs')
    sentinel=target/'user-created-file.txt';sentinel.write_text('Keep user files',encoding='utf-8')
    retry=subprocess.run(args+['/LOG='+str(evidence/'refused-reinstall.log')],timeout=30)
    if retry.returncode==0 or sentinel.read_text()!='Keep user files':raise RuntimeError('Overwrite protection failed')
    probe(target,evidence/'probe')
    uninstaller=target/'unins000.exe'
    if not uninstaller.is_file():raise RuntimeError('Missing uninstaller')
    removed=subprocess.run([str(uninstaller),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',
                            '/LOG='+str(evidence/'uninstall.log')],timeout=300)
    deadline=time.monotonic()+30
    while (target/'BMK-AI-Studio.exe').exists() and time.monotonic()<deadline:time.sleep(.1)
    if removed.returncode or (target/'BMK-AI-Studio.exe').exists():raise RuntimeError('Uninstall failed')
    if sentinel.read_text()!='Keep user files':raise RuntimeError('User file was removed')
    result={'passed':True,'installer_sha256':digest(installer),'installed_files_verified':report['file_count'],
            'nonempty_directory_refused':True,'user_file_preserved_after_uninstall':True,
            'isolated_frozen_probe':True,'another_physical_pc':False}
    (evidence/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer');parser.add_argument('bundle');parser.add_argument('evidence')
    args=parser.parse_args();validate(args.installer,args.bundle,args.evidence)

