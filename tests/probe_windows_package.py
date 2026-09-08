"""Inspect only a newly created private-data test instance, then close it normally."""
import ctypes,json,os,subprocess,sys,tempfile,time
from ctypes import wintypes
from pathlib import Path

exe=Path(sys.argv[1]).resolve();root=Path(tempfile.mkdtemp(prefix='bmk-native-probe-'))
env=os.environ.copy();env['BMK_STUDIO_DATA']=str(root/'data')
for key in ('PYTHONPATH','PYTHONHOME','QT_QPA_PLATFORM'):env.pop(key,None)
env['PATH']=os.environ.get('WINDIR','C:\\Windows')+'\\System32'
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
process=subprocess.Popen([str(exe),*sys.argv[2:]],cwd=root,env=env,startupinfo=startup)
user=ctypes.windll.user32;callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
found=[]
def callback(hwnd,param):
    pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if pid.value==process.pid:
        text=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,text,512)
        if text.value.startswith('BMK AI Studio'):found.append((hwnd,text.value))
    return True
try:
    end=time.monotonic()+20
    while not found and process.poll() is None and time.monotonic()<end:
        user.EnumWindows(callback_type(callback),0);time.sleep(.1)
    if not found:raise RuntimeError(f'No native app window; exit={process.poll()}, data={root}')
    user.PostMessageW(wintypes.HWND(found[0][0]),0x0010,0,0)
    code=process.wait(timeout=15)
    assert code==0 and not (root/'data/startup-error.log').exists()
    print(json.dumps({'passed':True,'title':found[0][1],'exit':code,'isolated_path':True,'data':str(root)},ensure_ascii=False))
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=10)
