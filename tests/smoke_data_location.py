"""Settings-driven migration with dirty edits and fresh-process restoration."""
import os,sys,tempfile,time,json,subprocess
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QPushButton,QDialogButtonBox
from bmk_studio.app import Studio,configure_app
from bmk_studio.data_location import resolve_directory
from bmk_studio.core import fingerprint

app=QApplication([]);configure_app(app)
if '--restore' in sys.argv:
    config=Path(sys.argv[sys.argv.index('--restore')+1]);w=Studio(resolve_directory(config),location_config=config)
    assert w.current.size==(40,50) and w.draft.toPlainText()=='saved migration draft'
    assert w.path==w.store.root/'clipboard/source.png'
    assert w.store.notes()[0][1]=='preserved note'
    assert (w.store.root/'wildcards/color.txt').read_text()=='blue'
    w.close();app.processEvents();print('PASS: fresh process restores migrated dirty crop, clipboard source, draft, notes, wildcard');sys.exit(0)

root=Path(tempfile.mkdtemp(prefix='bmk-data-settings-')).resolve();old=root/'old';target=root/'chosen';config=root/'startup.json'
source=old/'clipboard/source.png';source.parent.mkdir(parents=True);Image.new('RGB',(100,120),'#739eae').save(source);before=fingerprint(source)
w=Studio(old,location_config=config);w.show();w.add_paths([source]);errors=[];w.error=errors.append
end=time.monotonic()+20
while w.jobs and time.monotonic()<end:app.processEvents();time.sleep(.01)
w.store.save_note('preserved note',{'prompt':'note','unknown':{'future':True}})
wild=old/'wildcards';wild.mkdir();(wild/'color.txt').write_text('blue')
w.set_box((10,20,40,50));w.apply_crop();w.draft.setPlainText('saved migration draft')
# Cancel leaves everything in place.
QTimer.singleShot(0,lambda:app.activeModalWidget().reject());assert not w.change_data_directory();assert not config.exists() and w.isVisible()
ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(1)
def choose_location():
    dialog=app.activeModalWidget();dialog.target.setText(str(target));dialog.controls.button(QDialogButtonBox.StandardButton.Save).click()
def settings_entry():
    dialog=app.activeModalWidget();QTimer.singleShot(0,choose_location)
    next(button for button in dialog.findChildren(QPushButton) if button.text()=='사용자 데이터 폴더 변경…').click()
QTimer.singleShot(0,settings_entry);w.open_settings();app.processEvents();timer.stop()
assert not errors and w.data_switch_ready and not w.isVisible() and ticks,errors
assert json.loads(config.read_text())['directory']==str(target) and fingerprint(source)==before
# Hide the old root to prove restoration is not silently depending on its files.
old.rename(root/'preserved-old')
result=subprocess.run([sys.executable,__file__,'--restore',str(config)],capture_output=True,timeout=30)
assert result.returncode==0,(result.stdout,result.stderr)
print('PASS: actual settings -> data directory dialog, cancellation, dirty-edit checkpoint, responsive background copy, close, atomic config and fresh-process restoration; old data retained')
