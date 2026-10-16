"""Exercise real note tab signals and metadata-to-work actions without personal data."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from PySide6.QtCore import QCoreApplication,QEvent,QPoint,QTimer,Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu
from unittest.mock import patch
from bmk_studio.app import Studio,configure_app
from test_metadata import graph

root=Path(tempfile.mkdtemp(prefix='bmk-documents-')).resolve()
app=QApplication([]);configure_app(app)

def close_window():
    app.processEvents()  # Finish queued layout/scroll restoration before deletion.
    assert w.close()
    # close() only hides the widget. Destroy it before the next Studio refreshes
    # all prompt highlighters and can restart autosave against its closed DB.
    w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()

w=Studio(root/'data');w.show()
meta=PngInfo();meta.add_text('parameters','actual output\nNegative prompt: original bad\nSteps: 12, Seed: 7');meta.add_text('prompt',json.dumps(graph()))
path=root/'image.png';Image.new('RGB',(64,64),'red').save(path,pnginfo=meta)
w.load(path);w.draft.setPlainText('image draft');w.save_draft()
first=w.store.save_note('first',{'prompt':'one','custom':{'retained':True}})
second=w.store.save_note('second',{'prompt':'two'})
w.open_note_id(first);w.draft.setPlainText('first edited')
w.open_note_id(second);w.draft.setPlainText('second edited')
w.note_tabs.setCurrentIndex(1);assert w.draft.toPlainText()=='first edited'
assert json.loads(w.store.note(second)[2])['prompt']=='second edited'
assert w.store.asset(path)[0]=='image draft'
w.main_tabs.setCurrentIndex(1);assert w.draft.toPlainText()=='image draft'
w.note_tabs.setCurrentIndex(2);w.close_document(2)
assert w.note_mode and w.draft.toPlainText()=='first edited'
w.main_tabs.setCurrentIndex(1)
assert w.draft.toPlainText()=='image draft';assert w.note_tabs.count()==2
w.open_note_id(first);w.draft.setPlainText('future')
revision=w.store.revisions(first)[-1][0];w.restore_note_version(revision)
assert w.draft.toPlainText()=='one';assert w.note_tabs.count()==2
assert json.loads(w.store.note(first)[2])['custom']=={'retained':True}
w.new_note();w.draft.setPlainText('new tab');w.main_tabs.setCurrentIndex(1)
assert w.draft.toPlainText()=='image draft';w.note_tabs.setCurrentIndex(2);assert w.draft.toPlainText()=='new tab'
w.main_tabs.setCurrentIndex(1);w.branch_choice.setCurrentIndex(1);w.use_branch()
assert w.draft.toPlainText()=='bird';assert w.positive.toPlainText()=='actual output'
assert '42' in w.branch_preview.toPlainText();assert '7' in w.generation_settings.toPlainText()
app.processEvents();w.tabs.setCurrentIndex(1);w.grab().save(str(root/'notes.png'))
w.tabs.setCurrentIndex(4);app.processEvents();w.grab().save(str(root/'metadata.png'))
w.open_note_id(first);close_window()
w=Studio(root/'data');assert w.note_tabs.count()==3;assert w.note_id==first
assert w.draft.toPlainText()=='one';close_window()
subprocess.run([sys.executable,'-c',
    "from PySide6.QtWidgets import QApplication; from bmk_studio.app import Studio; import sys; app=QApplication([]); w=Studio(sys.argv[1]); assert w.note_tabs.count()==3; assert w.note_id==sys.argv[2]; assert w.draft.toPlainText()=='one'; w.close()",
    str(root/'data'),first],check=True,cwd=Path(__file__).resolve().parents[1])

def context_menu(index,choice=None,enabled=(True,True,True,True)):
    """Send the tab's real context event, then click the popup action."""
    errors=[];seen=[];active=w.note_id
    def choose():
        menu=app.activePopupWidget()
        try:
            assert isinstance(menu,QMenu)
            actions=menu.actions();seen.extend(actions)
            assert [a.text() for a in actions]==['이 탭 닫기','오른쪽 탭 모두 닫기','왼쪽 탭 모두 닫기','나머지 탭 모두 닫기']
            assert tuple(a.isEnabled() for a in actions)==enabled
            assert w.note_id==active  # Right-click alone must not change the editor.
            if choice is None:menu.close()
            else:QTest.mouseClick(menu,Qt.MouseButton.LeftButton,pos=menu.actionGeometry(actions[choice]).center())
        except BaseException as exc:
            errors.append(exc)
            if isinstance(menu,QMenu):menu.close()
    app.processEvents();pos=w.note_tabs.tabRect(index).center()
    timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(choose);timer.start(0)
    QApplication.sendEvent(w.note_tabs,QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,w.note_tabs.mapToGlobal(pos)))
    timer.stop()
    if errors:raise errors[0]
    assert seen,'Context menu did not open'

def open_ids():
    return [w.note_tabs.tabData(i)['id'] for i in range(1,w.note_tabs.count())]

# Exercise inactive targets, removal on either side, active-tab removal and editor retention.
for case,(choice,target,active,remaining) in enumerate((
    (0,2,4,[0,2,3]),(0,2,2,[0,2,3]),(1,2,4,[0,1]),
    (2,3,1,[2,3]),(3,2,4,[1]),(3,2,2,[1]),
)):
    profile=root/f'menu-{case}';w=Studio(profile);w.show()
    ids=[w.store.save_note(f'note {i}',{'prompt':f'prompt {i}','custom':{'retained':i}}) for i in range(4)]
    for nid in ids:w.open_note_id(nid)
    w.note_tabs.setCurrentIndex(active);w.draft.insertPlainText('unsaved ')
    edited=w.draft.toPlainText();document=w.draft.document();cursor=w.draft.textCursor().position()
    w.draft_negative.setPlainText('unsaved negative');w.memo.setPlainText('unsaved memo')
    context_menu(target,choice)
    expected=[ids[i] for i in remaining]
    assert open_ids()==expected and w.note_id in expected
    assert not w.note_tabs.isTabVisible(0) and w.note_tabs.tabData(0)=={'id':None}
    if ids[active-1] in expected:
        assert w.note_id==ids[active-1] and w.draft.document() is document
        assert w.draft.textCursor().position()==cursor and w.draft.document().isUndoAvailable()
    body=json.loads(w.store.note(ids[active-1])[2])
    assert (body['prompt'],body['negative'],body['notes'])==(edited,'unsaved negative','unsaved memo')
    for i,nid in enumerate(ids):assert json.loads(w.store.note(nid)[2])['custom']=={'retained':i}
    state=w.store.state('documents');assert state['ids']==expected and state['active']==w.note_id
    close_window();w=Studio(profile)
    assert open_ids()==expected and w.note_id==state['active'];close_window()

# Boundaries, dismissal and empty space; closing the final draft saves it and opens an empty tab.
w=Studio(root/'menu-boundaries');w.show();w.main_tabs.setCurrentIndex(2)
context_menu(1,enabled=(True,False,False,False))
w.draft.setPlainText('last unsaved draft');w.note_extra['custom']={'last':True}
context_menu(1,0,enabled=(True,False,False,False))
assert open_ids()==[None] and w.note_mode and w.draft.toPlainText()==''
saved=w.store.note_entries();assert len(saved)==1
body=json.loads(saved[0][2]);assert body['prompt']=='last unsaved draft' and body['custom']=={'last':True}
w.open_note_id(saved[0][0]);context_menu(1,enabled=(True,True,False,True));context_menu(2,enabled=(True,False,True,True))
with patch('bmk_studio.app.QMenu.exec',return_value=None) as menu_exec:
    pos=QPoint(-10,-10)
    QApplication.sendEvent(w.note_tabs,QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,w.note_tabs.mapToGlobal(pos)))
    menu_exec.assert_not_called()
close_window()
print('PASS: multiple notes, context-menu close actions and boundaries, autosave, editor retention, restart, image draft separation, restore, new tab, branch copy and original priority; screenshots:',root)
