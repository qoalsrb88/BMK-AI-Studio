"""Exercise real note tab signals and metadata-to-work actions without personal data."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,tempfile,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from PySide6.QtCore import QCoreApplication,QEvent,QPoint,Qt,QSettings
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMenu
from contextlib import ExitStack
from unittest.mock import patch,Mock
from bmk_studio.app import Studio,configure_app
from test_metadata import graph

root=Path(tempfile.mkdtemp(prefix='bmk-documents-')).resolve()
guards=ExitStack()
guards.enter_context(patch('bmk_studio.app.QSettings',side_effect=lambda *args:QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)))
for name in ('reveal_in_explorer','open_default','copy_paths'):guards.enter_context(patch('bmk_studio.shell_actions.'+name))
guards.enter_context(patch('PySide6.QtWidgets.QMenu.exec',return_value=None))
def make_menu(*args):
    menu=QMenu(*args);menu.exec=Mock(return_value=None);return menu
guards.enter_context(patch('bmk_studio.app.QMenu',side_effect=make_menu))
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
    "from PySide6.QtWidgets import QApplication; from PySide6.QtCore import QSettings; from unittest.mock import patch; from bmk_studio.app import Studio; import sys; patch('bmk_studio.app.QSettings',side_effect=lambda *args:QSettings(sys.argv[1]+'/settings.ini',QSettings.Format.IniFormat)).start(); app=QApplication([]); w=Studio(sys.argv[1]); assert w.note_tabs.count()==3; assert w.note_id==sys.argv[2]; assert w.draft.toPlainText()=='one'; w.close()",
    str(root/'data'),first],check=True,cwd=Path(__file__).resolve().parents[1])

def context_menu(index,choice=None,enabled=(True,True,True,True)):
    """Send the real context event, inspecting and triggering a patched menu."""
    seen=[];errors=[];active=w.note_id
    def choose(menu,*args):
        actions=menu.actions();seen.extend(actions)
        assert [a.text() for a in actions]==['이 탭 닫기','오른쪽 탭 모두 닫기','왼쪽 탭 모두 닫기','나머지 탭 모두 닫기','모든 탭 닫기','','닫은 탭 다시 열기']
        assert tuple(a.isEnabled() for a in actions[:4])==enabled
        assert actions[-1].shortcut().toString()=='Ctrl+Shift+T'
        assert w.note_id==active
        if choice is not None:actions[choice].trigger()
    app.processEvents();pos=w.note_tabs.tabRect(index).center()
    def create(*args):
        menu=make_menu(*args)
        def execute(*args):
            try:choose(menu,*args)
            except BaseException as exc:errors.append(exc)
        menu.exec=Mock(side_effect=execute);return menu
    with patch('bmk_studio.app.QMenu',side_effect=create):
        QApplication.sendEvent(w.note_tabs,QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,w.note_tabs.mapToGlobal(pos)))
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
    assert not w.note_tabs.isTabVisible(0) and w.note_tabs.tabData(0)=={'id':None,'image':True}
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
with patch.object(w,'make_note_tab_menu',wraps=w.make_note_tab_menu) as menu_builder:
    pos=QPoint(-10,-10)
    QApplication.sendEvent(w.note_tabs,QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,w.note_tabs.mapToGlobal(pos)))
    menu_builder.assert_called_once_with(-1)
close_window()

# Moving an active or inactive tab must not reload the editor or save into its old slot.
w=Studio(root/'moving');w.show()
ids=[w.store.save_note(f'move {i}',{'prompt':f'body {i}','custom':{'i':i}}) for i in range(3)]
for nid in ids:w.open_note_id(nid)
w.note_tabs.setCurrentIndex(2);w.draft.insertPlainText('before move ');document=w.draft.document()
app.processEvents();start=w.note_tabs.tabRect(2).center();end=w.note_tabs.tabRect(3).center()
QTest.mousePress(w.note_tabs,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(w.note_tabs,end,20);QTest.mouseRelease(w.note_tabs,Qt.MouseButton.LeftButton,pos=end)
assert open_ids()==[ids[0],ids[2],ids[1]] and w.document_index==3 and w.note_id==ids[1]
assert w.draft.document() is document and w.draft.toPlainText()=='before move body 1'
w.note_title.setText('moved title');w.draft.insertPlainText('after move ');QTest.qWait(750)
assert w.store.note(ids[1])[1]=='moved title' and json.loads(w.store.note(ids[1])[2])['prompt']==w.draft.toPlainText()
assert [w.store.note(nid)[1] for nid in (ids[0],ids[2])]==['move 0','move 2']
assert [json.loads(w.store.note(nid)[2])['prompt'] for nid in (ids[0],ids[2])]==['body 0','body 2']
w.note_tabs.moveTab(1,2);assert w.note_id==ids[1] and w.document_index==3
w.note_tabs.moveTab(3,0);assert w.note_tabs.tabData(0).get('image') and w.note_id==ids[1] and w.document_index==1
assert w.draft.document() is document
w.note_tabs.moveTab(0,2);assert w.note_tabs.tabData(0).get('image') and w.note_id==ids[1]
expected_order=open_ids();w.save_draft();close_window();w=Studio(root/'moving');w.show()
assert open_ids()==expected_order and w.note_id==ids[1]
# An unsaved note's held editor follows its tab index even while image mode is active.
w.new_note();blank=w.document_index;w.draft.insertPlainText('temporary');w.draft.undo();blank_doc=w.draft.document()
w.main_tabs.setCurrentIndex(1);assert ('note',blank) in w.editor_contexts
w.note_tabs.moveTab(blank,1);assert w.last_note_index==1 and ('note',1) in w.editor_contexts
w.main_tabs.setCurrentIndex(2);assert w.note_id is None and w.document_index==1 and w.draft.document() is blank_doc
assert w.draft.document().isRedoAvailable()
close_window()

# Session-only reopen stack skips archived, missing and already-open notes, and is bounded.
w=Studio(root/'reopen');w.show()
ids=[w.store.save_note(f'reopen {i}',{'prompt':str(i)}) for i in range(12)]
for nid in ids:w.open_note_id(nid);w.close_document(w.document_index)
assert w.closed_note_ids==ids[-10:]
w.open_note_id(ids[-1]);w.store.archive_note(ids[-2]);w.closed_note_ids.append('missing')
w.reopen_note();assert w.note_id==ids[-3]
w.close_document(w.document_index);w.open_note_id(ids[-3]);w.close_document(w.document_index)
assert w.closed_note_ids.count(ids[-3])==1
w.new_note();before=list(w.closed_note_ids);w.close_document(w.document_index);assert w.closed_note_ids==before
w.open_note_id(ids[0]);app.processEvents();index=w.document_index
QTest.mouseClick(w.note_tabs,Qt.MouseButton.MiddleButton,pos=w.note_tabs.tabRect(index).center())
assert ids[0] not in open_ids() and w.closed_note_ids[-1]==ids[0]
w.close_document(0);assert w.note_tabs.tabData(0).get('image')
menu=w.make_note_tab_menu(-1);assert [a.text() for a in menu.actions()]==['새 노트','닫은 탭 다시 열기','모든 탭 닫기'];assert menu.actions()[0].shortcut().toString()=='Ctrl+N';menu.actions()[-1].trigger();menu.deleteLater()
assert open_ids()==[None] and w.note_mode and not w.draft.toPlainText()
close_window();w=Studio(root/'reopen');assert not w.closed_note_ids;close_window()

# All three editors retain window shortcuts; note-only shortcuts release image mode.
w=Studio(root/'shortcuts');w.show();w.activateWindow();app.processEvents()
ids=[w.store.save_note(f'key {i}',{'prompt':str(i)}) for i in range(3)]
for nid in ids:w.open_note_id(nid)
for editor in (w.draft,w.draft_negative,w.memo):
    w.note_tabs.setCurrentIndex(3);editor.setFocus();app.processEvents();assert editor.hasFocus()
    QTest.keyClick(editor,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier);assert w.document_index==1
    editor.setFocus();QTest.keyClick(editor,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);assert w.document_index==3
    editor.setFocus();QTest.keyClick(editor,Qt.Key.Key_W,Qt.KeyboardModifier.ControlModifier);assert ids[-1] not in open_ids()
    editor.setFocus();QTest.keyClick(editor,Qt.Key.Key_T,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);assert w.note_id==ids[-1]
    editor.setFocus();QTest.keyClick(editor,Qt.Key.Key_N,Qt.KeyboardModifier.ControlModifier);assert w.note_id is None and w.note_tabs.count()==5
    editor.setFocus();QTest.keyClick(editor,Qt.Key.Key_W,Qt.KeyboardModifier.ControlModifier);assert w.note_tabs.count()==4
for main in (0,1):
    w.main_tabs.setCurrentIndex(main);app.processEvents()
    assert all(not w.note_shortcuts[key].isEnabled() for key in ('Ctrl+W','Ctrl+Tab','Ctrl+Shift+Tab'))
    w.setFocus();QTest.keyClick(w,Qt.Key.Key_N,Qt.KeyboardModifier.ControlModifier);assert w.main_tabs.currentIndex()==2 and w.note_id is None
w.main_tabs.setCurrentIndex(1);w.tabs.setCurrentIndex(0);w.positive.setFocus();app.processEvents()
QTest.keyClick(w.positive,Qt.Key.Key_Tab,Qt.KeyboardModifier.ControlModifier);assert w.tabs.currentIndex()==1
w.open_note_id(ids[-1]);w.close_document(w.document_index);w.main_tabs.setCurrentIndex(1);w.draft.setFocus();QTest.keyClick(w.draft,Qt.Key.Key_T,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
assert w.main_tabs.currentIndex()==2 and w.note_id==ids[-1]
close_window()

def tree_item(nid=None,folder=None):
    def visit(parent):
        for i in range(parent.childCount()):
            item=parent.child(i)
            if (nid and item.data(0,Qt.ItemDataRole.UserRole)==nid) or (folder and item.data(0,Qt.ItemDataRole.UserRole+1)==folder):return item
            found=visit(item)
            if found:return found
    return visit(w.notes.invisibleRootItem())

w=Studio(root/'tree');w.show();w.main_tabs.setCurrentIndex(2)
first=w.store.save_note('tree first',{'prompt':'first','custom':{'nested':[1,False]}},category='Characters/Clothes')
second=w.store.save_note('tree second',{'prompt':'second','future':[{'x':3}]},category='Other')
w.refresh_notes();tree_item(folder='/Characters').setExpanded(False)
assert w.store.state('note_tree')=={'collapsed':['/Characters']}
w.note_search.setText('tree first');assert tree_item(folder='/Characters').isExpanded()
tree_item(folder='/Characters').setExpanded(False);tree_item(folder='/Characters').setExpanded(True)
assert w.store.state('note_tree')=={'collapsed':['/Characters']}
w.note_search.clear();assert not tree_item(folder='/Characters').isExpanded()
w.refresh_notes();assert not tree_item(folder='/Characters').isExpanded()
close_window();w=Studio(root/'tree');w.show();assert not tree_item(folder='/Characters').isExpanded()
w.expand_note_folders(True);w.open_note_id(first);w.open_note_id(second);w.refresh_notes();app.processEvents()
item=tree_item(first);pos=w.notes.visualItemRect(item).center()
QTest.mouseClick(w.notes.viewport(),Qt.MouseButton.RightButton,pos=pos);assert w.note_id==second
with patch('bmk_studio.shell_actions.select_for_context',wraps=__import__('bmk_studio.shell_actions',fromlist=['select_for_context']).select_for_context) as select_context:
    w.note_tree_context_menu(pos);select_context.assert_called_once()
assert w.note_id==second and w.notes.currentItem().data(0,Qt.ItemDataRole.UserRole)==first
menu=w.make_note_tree_menu(tree_item(first));assert [a.text() for a in menu.actions()]==['열기','이름 바꾸기…','복제','보관함으로 옮기기','','버전 이력','JSON 내보내기']
assert menu.actions()[1].shortcut().toString()=='F2';menu.deleteLater()
before=json.loads(w.store.note(first)[2]);revisions=len(w.store.revisions(first))
with patch('bmk_studio.app.QInputDialog.getText',return_value=('renamed first',True)) as prompt:
    w.notes.setFocus();QTest.keyClick(w.notes,Qt.Key.Key_F2);prompt.assert_called_once();assert prompt.call_args.kwargs['text']=='tree first'
assert w.store.note(first)[1]=='renamed first' and json.loads(w.store.note(first)[2])==before and len(w.store.revisions(first))==revisions+1
assert w.note_id==second and w.note_tabs.tabText(2)=='renamed first'
w.open_note_id(first);w.refresh_notes();w.notes.setCurrentItem(tree_item(first));w.draft.insertPlainText('unsaved ')
with patch('bmk_studio.app.QInputDialog.getText',return_value=('active renamed',True)):w.rename_tree_note()
assert w.note_title.text()=='active renamed';w.save_draft();assert w.store.note(first)[1]=='active renamed'
for title,ok in (('',True),('active renamed',True),('ignored',False)):
    count=len(w.store.revisions(first))
    with patch('bmk_studio.app.QInputDialog.getText',return_value=(title,ok)):w.rename_tree_note()
    assert len(w.store.revisions(first))==count
with patch('bmk_studio.app.QInputDialog.getText') as prompt:
    w.draft.setFocus();QTest.keyClick(w.draft,Qt.Key.Key_F2);prompt.assert_not_called()
before=json.loads(w.store.note(first)[2]);count=len(w.store.revisions(first));w.duplicate_tree_note(first);duplicate=w.note_id
assert duplicate!=first and w.store.note(duplicate)[1]=='active renamed 사본' and w.store.note(duplicate)[3]=='Characters/Clothes'
assert json.loads(w.store.note(duplicate)[2])==before and len(w.store.revisions(first))==count
w.archive_tree_note(first);assert w.store.note(first)[4] and '보관함으로' in w.statusBar().currentMessage()
w.show_archived.setChecked(True);menu=w.make_note_tree_menu(tree_item(first));assert menu.actions()[3].text()=='보관함에서 복구';menu.actions()[3].trigger();menu.deleteLater()
assert not w.store.note(first)[4] and w.statusBar().currentMessage()=='노트를 복구했습니다.'
w.show_archived.setChecked(False)
for label,method in [('버전 이력','note_history'),('JSON 내보내기','export_note')]:
    with patch.object(w,method) as callback:
        menu=w.make_note_tree_menu(tree_item(second));next(a for a in menu.actions() if a.text()==label).trigger();assert w.note_id==second;callback.assert_called_once();menu.deleteLater()
menu=w.make_note_tree_menu(tree_item(folder='/Characters/Clothes'));assert [a.text() for a in menu.actions()]==['이 폴더에 새 노트 만들기','','모두 펼치기','모두 접기'];menu.actions()[0].trigger();menu.deleteLater()
assert w.note_category.currentText()=='Characters/Clothes';count=len(w.store.note_entries());w.save_draft();assert w.note_id is None and len(w.store.note_entries())==count
w.new_folder_note('/미분류');assert not w.note_category.currentText()
menu=w.make_note_tree_menu(None);assert [a.text() for a in menu.actions()]==['새 노트','','모두 펼치기','모두 접기'];menu.actions()[-1].trigger();menu.deleteLater()
assert '/Characters/Clothes' in w.store.state('note_tree')['collapsed']
# Re-selecting the current note on refresh must not re-expand its collapsed folder, visibly or on the next show.
w.open_note_id(second);w.refresh_notes();w.notes.setCurrentItem(tree_item(second));tree_item(folder='/Other').setExpanded(False);app.processEvents()
w.refresh_notes();app.processEvents();assert not tree_item(folder='/Other').isExpanded()
w.main_tabs.setCurrentIndex(1);app.processEvents();w.refresh_notes();w.main_tabs.setCurrentIndex(2);app.processEvents()
assert not tree_item(folder='/Other').isExpanded() and '/Other' in w.store.state('note_tree')['collapsed']
# Ctrl+N and Ctrl+Shift+T from the image screen keep the image editor's undo history, like a normal tab switch.
w.main_tabs.setCurrentIndex(1);w.load(path);app.processEvents();w.draft.insertPlainText(' image edit');assert w.draft.document().isUndoAvailable()
tabs=w.note_tabs.count();w.note_shortcuts['Ctrl+N'].trigger();assert w.main_tabs.currentIndex()==2 and w.note_tabs.count()==tabs+1 and w.note_id is None
w.main_tabs.setCurrentIndex(1);assert w.draft.document().isUndoAvailable()
w.main_tabs.setCurrentIndex(2);w.close_document(next(i for i in range(1,w.note_tabs.count()) if w.note_tabs.tabData(i).get('id')==second))
w.main_tabs.setCurrentIndex(1);w.note_shortcuts['Ctrl+Shift+T'].trigger();assert w.main_tabs.currentIndex()==2 and w.note_id==second
w.main_tabs.setCurrentIndex(1);assert w.draft.document().isUndoAvailable()
close_window();guards.close()
print('PASS: note tab menus, reorder/autosave/restart, reopen stack, middle close, editor shortcuts, tree menus, rename/duplicate/history preservation and persistent folder collapse; temporary artifacts:',root)
