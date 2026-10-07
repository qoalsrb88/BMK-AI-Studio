"""Version-isolated installation, pre-launch verification and preserved data recovery."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from . import __version__,update_config
from .authenticode import normalize_thumbprint,verify_publisher
from .update_download import verify_installable
from .updates import version_tuple

UPDATE_PROTOCOL=1


def update_root():return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BMK-AI-Studio-updates'


def save_json(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())


def prepare_install(downloaded,data_directory):
    if not getattr(sys,'frozen',False) or downloaded.get('verified') is not True:
        raise ValueError('서명 확인된 실행 배포본에서만 자동 설치할 수 있습니다.')
    thumbprint=normalize_thumbprint(update_config.SIGNING_THUMBPRINT)
    path=Path(downloaded['path']).resolve(strict=True);folder=path.parent
    if folder.parent!=update_root().resolve():raise ValueError('Unexpected update directory')
    asset=downloaded['asset']
    from .update_assets import current_flavor
    if current_flavor()!=asset['flavor']:raise ValueError('자동 설치는 현재 실행판과 같은 종류만 지원합니다.')
    if version_tuple(asset['version'])<=version_tuple(__version__):raise ValueError('Newer release required')
    # This second verification runs in the worker after the app has exited.
    plan={'schema':UPDATE_PROTOCOL,'installer':str(path),'size':asset['size'],'sha256':asset['sha256'],
          'publisher':thumbprint,'version':asset['version'],'flavor':asset['flavor'],
          'previous':str(Path(sys.executable).resolve()),'parent_pid':os.getpid(),
          'data_directory':str(Path(data_directory).resolve()),'created':time.time()}
    target=folder/('install-'+uuid.uuid4().hex+'.json');save_json(target,plan);return target


@contextmanager
def external_environment():
    env=os.environ.copy();env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QML2_IMPORT_PATH','BMK_STUDIO_DATA','QT_QPA_PLATFORM'):
        env.pop(key,None)
    env['PATH']=str(Path(os.environ.get('WINDIR','C:/Windows'))/'System32')
    frozen=bool(getattr(sys,'frozen',False)) and os.name=='nt'
    if frozen:ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:yield env
    finally:
        if frozen:ctypes.windll.kernel32.SetDllDirectoryW(str(sys._MEIPASS))


def launch_worker(plan):
    with external_environment() as env:
        subprocess.Popen([sys.executable,'--apply-update',str(plan)],env=env,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)


def wait_parent(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x00100000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return
        raise RuntimeError('Cannot confirm previous application exit')
    try:
        if kernel.WaitForSingleObject(handle,300000)!=0:raise RuntimeError('Previous application is still running')
    finally:kernel.CloseHandle(handle)


def read_plan(path):
    path=Path(path).resolve(strict=True)
    if path.parent.parent!=update_root().resolve() or path.stat().st_size>16384:raise ValueError('Invalid update plan location')
    plan=json.loads(path.read_text(encoding='utf-8'))
    if plan.get('schema')!=UPDATE_PROTOCOL or type(plan.get('parent_pid')) is not int or plan['parent_pid']<=0 or plan['parent_pid']==os.getpid():
        raise ValueError('Invalid update plan')
    if not isinstance(plan.get('created'),(int,float)) or not 0<=time.time()-plan['created']<=600:raise ValueError('Expired update plan')
    if plan.get('publisher')!=normalize_thumbprint(update_config.SIGNING_THUMBPRINT):raise ValueError('Unexpected publisher')
    if Path(plan['previous']).resolve()!=Path(sys.executable).resolve():raise ValueError('Unexpected previous application')
    if Path(plan['installer']).resolve().parent!=path.parent:raise ValueError('Installer outside staging directory')
    if any((path.parent/name).exists() for name in ('installation-started.json','installation-result.json')):
        raise ValueError('Update request already processed')
    if version_tuple(plan['version'])<=version_tuple(__version__) or plan['flavor'] not in ('CPU','NVIDIA'):
        raise ValueError('Invalid target release')
    return path,plan


def notify_ready(path,data_directory):
    path=Path(path).resolve()
    if path.name!='ready.json' or path.parent.parent!=update_root().resolve():raise ValueError('Invalid readiness path')
    save_json(path,{'version':__version__,'protocol':UPDATE_PROTOCOL,'data_directory':str(Path(data_directory).resolve())})


def apply_update(path):
    from .data_location import lock_directory,copy_data,validate_existing
    path,plan=read_plan(path);folder=path.parent;data=Path(plan['data_directory']).resolve(strict=True)
    # Exclusive claim also prevents two workers that read the plan concurrently.
    save_json(folder/'installation-started.json',{'pid':os.getpid(),'started':time.time()})
    previous=Path(plan['previous']);backup=folder/'data-backup';launched=False;lock=None;can_restart=False
    receipt={'installed':False,'previous_preserved':True,'data_directory':str(data)}
    try:
        wait_parent(plan['parent_pid'])
        lock=lock_directory(data);can_restart=True;validate_existing(data)
        verify_installable(plan['installer'],plan['size'],plan['sha256'],plan['publisher'])
        if data in folder.parents or folder in data.parents or data==folder:raise ValueError('Update and user data directories overlap')
        copy_data(data,backup);receipt['backup']=str(backup)
        target=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Programs'/'BMK-AI-Studio'/(plan['version']+'-'+plan['flavor']+'-'+uuid.uuid4().hex[:8])
        if target.exists():raise FileExistsError('Installation target already exists')
        if data==target or data in target.parents or target in data.parents:raise ValueError('Installation overlaps user data')
        with external_environment() as env:
            result=subprocess.run([plan['installer'],'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/TASKS=',
                                   '/DIR='+str(target),'/LOG='+str(folder/'setup.log')],env=env,timeout=600)
            if result.returncode:raise RuntimeError('Installer failed')
            executable=target/'BMK-AI-Studio.exe';verify_publisher(executable,plan['publisher'])
            info=json.loads((target/'build-info.json').read_text(encoding='utf-8'))
            if (info.get('version')!=plan['version'] or info.get('update_protocol')!=UPDATE_PROTOCOL
                    or ('NVIDIA' if info.get('cuda') else 'CPU')!=plan['flavor']):
                raise ValueError('Installed version or data compatibility does not match')
            report=folder/'self-test.json';probe_env=dict(env,QT_QPA_PLATFORM='offscreen',CUDA_VISIBLE_DEVICES='-1')
            check=subprocess.run([str(executable),'--self-test',str(report)],env=probe_env,timeout=300)
            checked=json.loads(report.read_text(encoding='utf-8'))
            if check.returncode or checked.get('passed') is not True or checked.get('version')!=plan['version']:
                raise RuntimeError('Installed application self-test failed')
            lock.unlock();lock=None
            ready=folder/'ready.json'
            child=subprocess.Popen([str(executable),'--user-directory',str(data),'--update-ready',str(ready)],env=env)
            launched=True;deadline=time.monotonic()+60
            while not ready.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.1)
            if not ready.exists():
                if child.poll() is None:
                    receipt['startup_pending']=True
                    raise RuntimeError('New application is still starting; previous version was not started concurrently')
                # Preserve the attempted new profile. Restore service on a separate,
                # verified copy rather than overwriting any user's files.
                receipt['recovery_directory']=str(backup)
                subprocess.Popen([str(previous),'--user-directory',str(backup)],env=env)
                raise RuntimeError('New application exited; previous version restarted on the preserved backup')
            value=json.loads(ready.read_text(encoding='utf-8'))
            if (value.get('version')!=plan['version'] or value.get('protocol')!=UPDATE_PROTOCOL
                    or value.get('data_directory')!=str(data)):
                raise RuntimeError('Unexpected startup confirmation')
            receipt.update(installed=True,version=plan['version'],directory=str(target))
    except Exception as exc:
        receipt['error']=str(exc)
        if lock is not None:lock.unlock();lock=None
        if can_restart and not launched:
            with external_environment() as env:subprocess.Popen([str(previous),'--user-directory',str(data)],env=env)
    finally:
        if lock is not None:lock.unlock()
        save_json(folder/'installation-result.json',receipt)
    return receipt


def main(path):
    try:
        result=apply_update(path)
        if not result.get('installed'):
            ctypes.windll.user32.MessageBoxW(None,'업데이트를 완료하지 못했습니다. 이전 버전과 데이터는 보존했습니다.\n'+str(Path(path).parent/'installation-result.json'),'BMK AI Studio 업데이트',16)
        return 0 if result.get('installed') else 1
    except Exception:
        ctypes.windll.user32.MessageBoxW(None,'업데이트 요청을 확인하지 못했습니다. 기존 바로가기로 앱을 다시 실행하세요.','BMK AI Studio 업데이트',16)
        return 1
