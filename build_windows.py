"""Build a new Windows bundle; never replace an existing application folder."""
import importlib.metadata as metadata
import json,os,shutil,subprocess,sys,uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    from bmk_studio import __version__
    from bmk_studio.update_install import UPDATE_PROTOCOL
    destination=(ROOT/os.environ.get('BMK_BUILD_FOLDER','package')).resolve()
    destination.relative_to(ROOT)
    bundle=destination/'BMK-AI-Studio'
    if bundle.exists():raise FileExistsError('Choose a new BMK_BUILD_FOLDER; existing bundles are preserved.')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip())
    if os.environ.get('BMK_RELEASE_BUILD')=='1' and dirty:raise RuntimeError('Release builds require a clean source commit.')
    work=ROOT/'build'/('windows-'+uuid.uuid4().hex);work.mkdir(parents=True)
    licenses=work/'third_party_licenses';licenses.mkdir()
    inventory=[]
    for dist in metadata.distributions():
        name=dist.metadata['Name']
        inventory.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License','')})
        for item in dist.files or []:
            if not any(part.lower().startswith(('license','copying','notice')) for part in item.parts):continue
            src=Path(dist.locate_file(item))
            if src.is_file() and src.suffix.lower() not in ('.py','.pyc','.pyd','.dll'):
                target=licenses/name/str(item).replace('..','_');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    (licenses/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copy2(python_license,licenses/'PYTHON-LICENSE.txt')
    version=tuple(int(v) for v in __version__.split('.'))+(0,)
    version_file=work/'version-info.txt'
    version_file.write_text(f'''VSVersionInfo(ffi=FixedFileInfo(filevers={version!r}, prodvers={version!r}, mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName','qoalsrb88'),StringStruct('FileDescription','BMK AI Studio'),StringStruct('FileVersion','{__version__}'),StringStruct('ProductName','BMK AI Studio'),StringStruct('ProductVersion','{__version__}'),StringStruct('OriginalFilename','BMK-AI-Studio.exe'),StringStruct('LegalCopyright','Copyright 2026 qoalsrb88')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])''',encoding='utf-8')
    env=os.environ.copy();env['PYINSTALLER_CONFIG_DIR']=str(work/'cache')
    # Do not resolve DLLs from unrelated tools (for example Poppler/Conda ICU)
    # on the caller's PATH. Qt uses the compatible Windows ICU implementation.
    windows=Path(os.environ.get('WINDIR',r'C:\Windows'))
    env['PATH']=os.pathsep.join(map(str,(Path(sys.executable).parent,Path(sys.base_prefix),windows/'System32',windows)))
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH'):
        env.pop(key,None)
    command=[sys.executable,'-m','PyInstaller','--onedir','--windowed','--noupx','--name','BMK-AI-Studio',
        '--distpath',str(destination),'--workpath',str(work),'--specpath',str(work),
        '--version-file',str(version_file),'--additional-hooks-dir',str(ROOT/'scripts/pyinstaller_hooks'),
        '--collect-all','timm','--collect-all','safetensors','--copy-metadata','torch','--copy-metadata','torchvision',
        '--collect-all','imagecodecs','--collect-all','OpenEXR','--collect-all','tokenizers',
        '--copy-metadata','huggingface_hub','--copy-metadata','timm',
        '--add-data',str(licenses)+':third_party_licenses',
        '--add-data',str(ROOT/'bmk_studio/vendor/BMK_LICENSE.txt')+':bmk_studio/vendor',
        '--exclude-module','folder_paths','--exclude-module','comfy',str(ROOT/'package_entry.py')]
    vision=Path(metadata.distribution('torchvision').locate_file('torchvision'))
    for binary in sorted(vision.iterdir()):
        if binary.suffix.lower() in ('.pyd','.dll'):command.extend(['--add-binary',str(binary)+':torchvision'])
    destination.mkdir(parents=True,exist_ok=True)
    with (destination/'build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    for source,target in [('LICENSE','LICENSE'),('THIRD_PARTY_NOTICES.md','THIRD_PARTY_NOTICES.md'),
                          ('docs/BINARY_README.md','README.txt'),('docs/DEPENDENCY_SOURCES.md','DEPENDENCY_SOURCES.md')]:
        shutil.copy2(ROOT/source,bundle/target)
    shutil.copytree(ROOT/'docs/licenses',bundle/'licenses')
    import torch
    from PySide6.QtCore import qVersion
    info={'version':__version__,'source_commit':revision,'source_dirty':dirty,'python':sys.version.split()[0],
          'qt':qVersion(),'torch':torch.__version__,'cuda':torch.version.cuda,'signed':False,
          'model_weights_included':False,'repository':'https://github.com/qoalsrb88/BMK-AI-Studio','update_protocol':UPDATE_PROTOCOL}
    (bundle/'build-info.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    print(bundle/'BMK-AI-Studio.exe',flush=True)

if __name__=='__main__':main()
