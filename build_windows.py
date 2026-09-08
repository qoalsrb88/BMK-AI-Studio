"""Build a one-folder Windows bundle with its own Python, Qt and AI runtime."""
import importlib.metadata as metadata
import json,os,shutil,subprocess,sys
from pathlib import Path

root=Path(__file__).resolve().parent
destination=root/os.environ.get('BMK_BUILD_FOLDER','package')
licenses=root/'third_party_licenses';licenses.mkdir(exist_ok=True)
inventory=[]
for dist in metadata.distributions():
    name=dist.metadata['Name'];inventory.append({'name':name,'version':dist.version,'license':dist.metadata.get('License-Expression') or dist.metadata.get('License','')})
    for item in dist.files or []:
        if not any(part.lower().startswith(('license','copying','notice')) for part in item.parts):continue
        src=Path(dist.locate_file(item))
        if src.is_file() and src.suffix.lower() not in ('.py','.pyc','.pyd','.dll'):
            dest=licenses/name/str(item).replace('..','_');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
(licenses/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
env=os.environ.copy();env['PYINSTALLER_CONFIG_DIR']=str(root/'build-cache')
command=[sys.executable,'-m','PyInstaller','--onedir','--windowed','--noupx','--name','BMK-AI-Studio',
         '--distpath',str(destination),'--workpath',str(root/'build'),'--specpath',str(root/'build'),
         '--collect-all','timm','--collect-all','safetensors','--copy-metadata','torch','--copy-metadata','torchvision',
         '--collect-all','imagecodecs','--collect-all','OpenEXR',
         '--collect-all','onnxruntime','--collect-all','tokenizers',
         '--copy-metadata','huggingface_hub','--copy-metadata','timm',
         '--add-data',str(licenses)+':third_party_licenses',
         '--add-data',str(root/'bmk_studio/vendor/BMK_LICENSE.txt')+':bmk_studio/vendor',
         '--exclude-module','folder_paths','--exclude-module','comfy',str(root/'package_entry.py')]
# torchvision 0.29 uses _C_stable/image_stable; older hooks only name _C/image.
vision=Path(metadata.distribution('torchvision').locate_file('torchvision'))
for binary in sorted(vision.iterdir()):
    if binary.suffix.lower() in ('.pyd','.dll'):command.extend(['--add-binary',str(binary)+':torchvision'])
with (root/'build-windows.log').open('w',encoding='utf-8') as log:
    subprocess.run(command,env=env,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
print(destination/'BMK-AI-Studio/BMK-AI-Studio.exe')
