"""Note folder sync in the real window: first connect, autosave to file, ComfyUI edits, conflicts, close flush."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,tempfile,time,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contextlib import ExitStack
from unittest.mock import patch
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication,QFormLayout,QWidget
from bmk_studio.app import Studio,configure_app
from bmk_studio.note_sync import SETTINGS_KEY,NoteFolderSync

root=Path(tempfile.mkdtemp(prefix='bmk-note-sync-')).resolve()
guards=ExitStack()
guards.enter_context(patch('bmk_studio.app.QSettings',side_effect=lambda *args:QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)))
app=QApplication([]);configure_app(app)
folder=root/'bmk_notes';(folder/'캐릭터').mkdir(parents=True)
(folder/'.bmk_meta.json').write_text('{"categories":[]}',encoding='utf-8')
def node_write(path,doc):
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',encoding='utf-8',newline='') as f:json.dump(doc,f,ensure_ascii=False,indent=1)
def read(rel):return json.loads((folder/rel).read_text(encoding='utf-8'))
def settle(w,timeout=30):
    deadline=time.monotonic()+timeout
    while w.jobs or w.note_sync_timer.isActive() or w.autosave.isActive():
        app.processEvents();time.sleep(.01);assert time.monotonic()<deadline,'sync did not settle'
    app.processEvents()

node_write(folder/'캐릭터'/'hero.json',{'prompt':'comfy hero','negative':'','loras':[],'notes':''})
w=Studio(root/'data');w.note_sync_timer.setInterval(50)
asked=[];answer=[True]
w.ask_note_sync=lambda text,info,accept,plan,reject='취소':asked.append((text,info,plan)) or answer[0]
assert not w.note_sync_panel.isVisibleTo(w)
# Settings rows: an unusable folder is refused before anything is saved.
holder=QWidget();form=QFormLayout(holder);values,problem=w.note_sync_settings_rows(form,holder)
assert values()==('',False) and problem() is None
w.new_note();w.note_title.setText('앱 노트');w.note_category.setCurrentText('MOSS');w.draft.setPlainText('from app');w.save_draft()
mine=w.note_id
# First connect asks with the plan, backs up the folder, then turns sync on.
answer[0]=False;w.apply_note_sync_settings(str(folder),True);settle(w)
assert len(asked)==1 and asked[0][2]['fresh'] and '폴더 → 앱 새 노트: 1개' in asked[0][1] and 'MOSS (1)' in asked[0][1]
assert not w.note_sync_enabled() and not (folder/'MOSS').exists() and len(w.store.note_entries())==1
answer[0]=True;w.apply_note_sync_settings(str(folder),True);settle(w)
assert w.note_sync_enabled() and w.note_sync_poll.isActive() and w.note_sync_panel.isVisibleTo(w)
assert read('MOSS/앱 노트.json')=={'prompt':'from app','negative':'','notes':''},read('MOSS/앱 노트.json')
assert {r[1]:r[3] for r in w.store.note_entries()}=={'앱 노트':'MOSS','hero':'캐릭터'}
backups=list((root/'data'/'note-sync-backups').glob('bmk_notes-*.zip'));assert len(backups)==1
with zipfile.ZipFile(backups[0]) as archive:assert set(archive.namelist())=={'.bmk_meta.json','캐릭터/hero.json'}
# Typing in the open note reaches the file after the pause.
w.open_note_id(mine);w.draft.setPlainText('typed in app');settle(w)
assert read('MOSS/앱 노트.json')['prompt']=='typed in app'
# A ComfyUI edit of the open note reloads the editor when nothing is typed.
node_write(folder/'MOSS'/'앱 노트.json',{'prompt':'edited in comfy','negative':'','loras':[],'notes':''})
w.run_note_sync(manual=True);settle(w)
assert w.draft.toPlainText()=='edited in comfy' and w.note_loaded==(w.note_id,w.note_state()),w.draft.toPlainText()
assert '다시 읽었습니다' in w.statusBar().currentMessage()
assert 'typed in app' in [json.loads(r[2])['prompt'] for r in w.store.revisions(mine)]
# Both sides changed: nothing is overwritten, the conflict is listed and settled from the file.
w.draft.setPlainText('app side');node_write(folder/'MOSS'/'앱 노트.json',{'prompt':'comfy side','negative':'','loras':[],'notes':''})
w.run_note_sync(manual=True);settle(w)
assert [c['kind'] for c in w.note_sync_conflicts]==['both'] and w.note_sync_conflict_button.isVisibleTo(w)
assert read('MOSS/앱 노트.json')['prompt']=='comfy side' and json.loads(w.store.note(mine)[2])['prompt']=='app side'
w.resolve_note_sync(w.note_sync_conflicts,'file');settle(w)
assert w.note_sync_conflicts==[] and not w.note_sync_conflict_button.isVisibleTo(w)
assert w.draft.toPlainText()=='comfy side' and json.loads(w.store.note(mine)[2])['prompt']=='comfy side'
# Autosaved while a sync job took the folder version: a conflict, not a silent overwrite of the ComfyUI edit.
node_write(folder/'MOSS'/'앱 노트.json',{'prompt':'comfy during job','negative':'','loras':[],'notes':''})
engine=NoteFolderSync(w.store,str(folder),{});plan=engine.plan()
w.note_sync_job=object();report=engine.apply(plan);assert report['updated']==[mine]
w.draft.setPlainText('typed during job');w.save_draft();assert w.note_sync_touched=={mine}
w.note_sync_job=None;w.note_sync_done(report);assert '충돌' in w.statusBar().currentMessage(),w.statusBar().currentMessage()
w.run_note_sync(manual=True);settle(w)
assert [c['kind'] for c in w.note_sync_conflicts]==['both'] and read('MOSS/앱 노트.json')['prompt']=='comfy during job'
assert json.loads(w.store.note(mine)[2])['prompt']=='typed during job'
w.resolve_note_sync(w.note_sync_conflicts,'app');settle(w)
assert w.note_sync_conflicts==[] and read('MOSS/앱 노트.json')['prompt']=='typed during job'
# Renaming in the app moves the file; archiving sends it to .trash.
w.note_title.setText('새 이름');settle(w)
assert (folder/'MOSS'/'새 이름.json').exists() and not (folder/'MOSS'/'앱 노트.json').exists()
w.archive_current_note();settle(w)
assert not (folder/'MOSS').exists() and any(p.name.endswith('_새 이름.json') for p in (folder/'.trash').iterdir())
# The last edit right before closing still reaches the folder.
hero=next(r[0] for r in w.store.note_entries() if r[1]=='hero');w.open_note_id(hero);w.draft.setPlainText('last words')
deadline=time.monotonic()+30
while not w.close():
    app.processEvents();time.sleep(.01);assert time.monotonic()<deadline
app.processEvents()
assert read('캐릭터/hero.json')['prompt']=='last words',read('캐릭터/hero.json')
# Turning sync off keeps the links and stops the timers.
w2=Studio(root/'data');assert w2.note_sync_enabled() and w2.note_sync_poll.isActive()
w2.apply_note_sync_settings(str(folder),False);assert not w2.note_sync_poll.isActive() and not w2.note_sync_panel.isVisibleTo(w2)
assert w2.store.state(SETTINGS_KEY)=={'folder':str(folder),'enabled':False}
assert w2.close();app.processEvents();guards.close()
print('PASS: first connect confirms and backs up; autosave writes the file; ComfyUI edits reload the open note; '
      'two-sided edits wait as a conflict and resolve from the file; a save during a sync job becomes a conflict; '
      'rename moves and archive trashes; close flushes the last edit')
