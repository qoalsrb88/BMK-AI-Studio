"""Disk browser integration: navigation, isolated previews and explicit registration."""
import os,sys,time,tempfile
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from PySide6.QtWidgets import QApplication,QPushButton,QMenu
from PySide6.QtCore import Qt,QItemSelectionModel,QModelIndex,QPoint,QSettings,QStandardPaths,QEvent
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint
from bmk_studio import shell_actions
root=Path(tempfile.mkdtemp(prefix='bmk-disk-')).resolve();folder=root/'images';folder.mkdir();(folder/'child').mkdir()
os.environ['LOCALAPPDATA']=str(root/'local');os.environ['BMK_STUDIO_DATA']=str(root/'user')
guards=ExitStack();guards.enter_context(patch('bmk_studio.app.QSettings',side_effect=lambda *args:QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)))
guards.enter_context(patch('bmk_studio.explorer_navigation.Path.home',return_value=root))
guards.enter_context(patch.object(QStandardPaths,'writableLocation',return_value=str(root)))
reveal=guards.enter_context(patch.object(shell_actions,'reveal_in_explorer',return_value=True));open_default=guards.enter_context(patch.object(shell_actions,'open_default',return_value=True))
copy_paths=guards.enter_context(patch.object(shell_actions,'copy_paths',wraps=shell_actions.copy_paths));select_context=guards.enter_context(patch.object(shell_actions,'select_for_context',wraps=shell_actions.select_for_context))
guards.enter_context(patch.object(QMenu,'exec',new=lambda *args:None))
def menu_stub(*args):
    # Shiboken instances can cache exec; route the instance through the patched class method.
    menu=QMenu(*args);menu.exec=lambda *values:QMenu.exec(menu,*values);return menu
guards.enter_context(patch('bmk_studio.disk_browser.QMenu',side_effect=menu_stub))
meta=PngInfo();meta.add_text('parameters','rainy city\nNegative prompt: blur\nSteps: 20, Seed: 1')
a=folder/'A.png';b=folder/'B.png';Image.new('RGB',(320,240),'red').save(a,pnginfo=meta);Image.new('RGB',(120,180),'blue').save(b);(folder/'text.txt').write_text('leave alone');Image.new('RGB',(20,20),'green').save(folder/'child/C.png')
hashes={str(p):fingerprint(p) for p in folder.rglob('*') if p.is_file()}
app=QApplication([]);configure_app(app);w=Studio(root/'user');w.resize(1400,900);w.show();errors=[];w.error=errors.append

def wait(check):
    end=time.monotonic()+25
    while time.monotonic()<end:
        app.processEvents();time.sleep(.01)
        if check():return
    raise AssertionError('Timeout '+str(errors))
w.workspace_mode.setCurrentIndex(2);d=w.disk_browser;assert d.isVisible() and not w.main_splitter.isVisible()
d.address.setText(str(folder));d.address.returnPressed.emit();wait(lambda:d.folder==str(folder) and not d.scan_job)
assert len(d.model.rows)==3 and w.library.count()==0
assert not w.store.db.execute('SELECT 1 FROM image_index').fetchone()
def index(name):
    return next(d.proxy.index(i,0) for i in range(d.proxy.rowCount()) if d.proxy.data(d.proxy.index(i,0),Qt.ItemDataRole.UserRole)[1]==name)
def select(*names):
    d.view.selectionModel().clear()
    for name in names:d.view.selectionModel().select(index(name),QItemSelectionModel.SelectionFlag.Select)
    if names:d.view.selectionModel().setCurrentIndex(index(names[0]),QItemSelectionModel.SelectionFlag.NoUpdate)
def selected():return {row[1] for row in d.selected_rows()}
def popup(view,idx=QModelIndex(),choose=None):
    if idx.isValid():view.scrollTo(idx);pos=view.visualRect(idx).center();pos.setX(min(pos.x(),view.viewport().width()-5))
    else:pos=QPoint(view.viewport().width()-4,view.viewport().height()-4);assert not view.indexAt(pos).isValid()
    captured=[]
    def inspect(menu,*args):
        captured.append([(item.text(),item.isEnabled(),item.shortcut().toString()) if not item.isSeparator() else None for item in menu.actions()])
        if choose:next(item for item in menu.actions() if item.text()==choose).trigger()
    with patch.object(QMenu,'exec',new=inspect):
        QTest.mouseClick(view.viewport(),Qt.MouseButton.RightButton,pos=pos)
        event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,pos,view.viewport().mapToGlobal(pos));app.sendEvent(view.viewport(),event)
    assert len(captured)==1,captured
    return captured[0]
def enabled(items,label):return next(item[1] for item in items if item and item[0]==label)
def labels(items):return [item[0] if item else None for item in items]
file_labels=['라이브러리에 추가','프롬프트를 노트에 저장…',None,'기본 앱으로 열기','탐색기에서 위치 열기','경로 복사','파일 이름 복사']
folder_labels=['열기','즐겨찾는 경로에 추가',None,'탐색기에서 열기','경로 복사']
d.view.setCurrentIndex(index('A.png'));wait(lambda:'rainy city' in d.metadata.toPlainText())
assert d.viewer.image_rect.width()==320 and w.path is None and w.library.count()==0
wait(lambda:str(a) in d.icons);assert d.cache.is_dir()
d.search.setText('B');assert d.proxy.rowCount()==1;d.search.clear();d.sort.setCurrentIndex(1);assert d.proxy.data(d.proxy.index(0,0),Qt.ItemDataRole.UserRole)[2]
d.toggle_favorite();assert str(folder) in d.state['favorites']
# Right-click preserves a selection containing the target and replaces an outside selection.
select('A.png','B.png');items=popup(d.view,index('B.png'),'경로 복사')
assert labels(items)==file_labels and selected()=={'A.png','B.png'}
assert enabled(items,'라이브러리에 추가') and not enabled(items,'프롬프트를 노트에 저장…') and not enabled(items,'기본 앱으로 열기')
assert set(app.clipboard().text().splitlines())=={str(a),str(b)} and w.statusBar().currentMessage()=='경로 2개를 복사했습니다.'
items=popup(d.view,index('child'));assert labels(items)==folder_labels and selected()=={'child'} and not d.add.isEnabled()
items=popup(d.view,index('A.png'),'기본 앱으로 열기');assert selected()=={'A.png'} and all(item[1] for item in items if item)
open_default.assert_called_once_with(str(a))
popup(d.view,index('A.png'),'탐색기에서 위치 열기');reveal.assert_called_with(str(a))
select('A.png','child');items=popup(d.view,index('A.png'),'경로 복사')
assert set(app.clipboard().text().splitlines())=={str(a),str(folder/'child')} and not enabled(items,'프롬프트를 노트에 저장…')
popup(d.view,index('A.png'),'파일 이름 복사');assert set(app.clipboard().text().splitlines())=={'A.png','child'}
assert w.statusBar().currentMessage()=='파일 이름 2개를 복사했습니다.'
with patch.object(w,'add_paths') as add_paths:
    popup(d.view,index('A.png'),'라이브러리에 추가');add_paths.assert_called_once_with([str(a)],open_first=False)
select('A.png')
with patch.object(w,'save_image_to_note') as save_note:
    popup(d.view,index('A.png'),'프롬프트를 노트에 저장…');save_note.assert_called_once_with(True)
d.preview_timer.stop();d.viewer.display(None)
popup(d.view,index('A.png'),'프롬프트를 노트에 저장…');assert w.statusBar().currentMessage()=='먼저 이미지 미리보기를 완료하세요.'
# A stale current item must not send another selected image's prompt to the note.
select('B.png');d.view.selectionModel().setCurrentIndex(index('A.png'),QItemSelectionModel.SelectionFlag.NoUpdate)
with patch.object(w,'save_image_to_note') as save_note:
    assert d.save_selected_prompt() and d.preview_path==str(b);save_note.assert_called_once_with(True)
select('A.png','B.png');items=popup(d.view)
assert labels(items)==['새로 고침','모두 선택',None,'탐색기에서 열기','경로 복사','즐겨찾는 경로에서 제거'] and not selected()
assert {item[0]:item[2] for item in items if item and item[2]}=={'새로 고침':'F5','모두 선택':'Ctrl+A','경로 복사':'Ctrl+Shift+C'}
popup(d.view,choose='경로 복사');assert app.clipboard().text()==str(folder)
popup(d.view,choose='탐색기에서 열기');reveal.assert_called_with(str(folder))
popup(d.view,choose='모두 선택');assert selected()=={'A.png','B.png','child'}
with patch.object(d,'navigate') as navigate:
    popup(d.view,choose='새로 고침');navigate.assert_called_once_with(str(folder),refresh=True)
old_folder=d.folder;d.folder='';d.update_navigation();items=popup(d.view)
assert all(not enabled(items,name) for name in ('새로 고침','탐색기에서 열기','경로 복사','즐겨찾는 경로에 추가'))
d.folder=old_folder;d.update_navigation()
# Favorite edits refresh both navigation lists; clicked(bool) keeps the toolbar's current-folder target.
def favorite_present(path):
    return d.favorites.findData(path)>0,any(d.navigation.quick.item(i).data(Qt.ItemDataRole.UserRole)==path for i in range(d.navigation.quick.count()))
popup(d.view,index('child'),'즐겨찾는 경로에 추가');assert favorite_present(str(folder/'child'))==(True,True)
assert labels(popup(d.view,index('child')))[1]=='즐겨찾는 경로에서 제거'
popup(d.view,index('child'),'즐겨찾는 경로에서 제거');assert favorite_present(str(folder/'child'))==(False,False)
favorite_button=next(button for button in d.findChildren(QPushButton) if button.text()=='☆ 경로 저장 / 해제')
favorite_button.click();assert favorite_present(str(folder))==(False,False)
favorite_button.click();assert favorite_present(str(folder))==(True,True)
popup(d.view,choose='즐겨찾는 경로에서 제거');assert favorite_present(str(folder))==(False,False)
popup(d.view,choose='즐겨찾는 경로에 추가');assert favorite_present(str(folder))==(True,True)
# Tree and quick-list right clicks never emit the left-click navigation signal.
nav=d.navigation;tree_index=nav.fs.index(str(folder/'child'))
wait(lambda:tree_index.isValid() and not nav.tree.visualRect(tree_index).isEmpty())
for view,idx,path in [(nav.tree,tree_index,str(folder/'child')),(nav.quick,nav.quick.model().index(0,0),str(root))]:
    clicked=[];view.clicked.connect(clicked.append)
    with patch.object(d,'navigate') as navigate:
        items=popup(view,idx);assert labels(items)==folder_labels and not clicked and items[-1][2]=='';navigate.assert_not_called()
        popup(view,idx,'열기');navigate.assert_called_once_with(path)
    popup(view,idx,'경로 복사');assert app.clipboard().text()==path
    popup(view,idx,'탐색기에서 열기');reveal.assert_called_with(path)
    popup(view,idx,'즐겨찾는 경로에 추가');assert path in d.state['favorites'] and favorite_present(path)==(True,True)
    idx=nav.fs.index(path) if view is nav.tree else nav.quick.model().index(0,0)
    assert labels(popup(view,idx))[1]=='즐겨찾는 경로에서 제거'
    popup(view,idx,'즐겨찾는 경로에서 제거');assert path not in d.state['favorites'] and d.favorites.findData(path)==-1
    view.clicked.disconnect(clicked.append)
with patch.object(d,'navigate') as navigate:
    nav.tree.scrollTo(tree_index);pos=nav.tree.visualRect(tree_index).center();pos.setX(min(pos.x(),nav.tree.viewport().width()-5))
    QTest.mouseClick(nav.tree.viewport(),Qt.MouseButton.LeftButton,pos=pos);navigate.assert_called_once_with(nav.fs.filePath(tree_index))
# Actual keys retain the panel scope and do not double-activate Enter or double-click.
w.activateWindow();d.view.setFocus();app.processEvents();select('A.png','B.png')
QTest.keyClick(d.view,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
assert set(app.clipboard().text().splitlines())=={str(a),str(b)}
d.view.selectionModel().clear();QTest.keyClick(d.view,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);assert app.clipboard().text()==str(folder)
QTest.keyClick(d.view,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);assert selected()=={'A.png','B.png','child'}
assert all(item.shortcutContext()==Qt.ShortcutContext.WidgetWithChildrenShortcut for item in (d.refresh_action,d.select_all_action,d.copy_paths_action))
with patch.object(d,'navigate') as navigate:
    QTest.keyClick(d.view,Qt.Key.Key_F5);navigate.assert_called_once_with(str(folder),refresh=True);navigate.reset_mock()
    select('A.png');QTest.keyClick(d.view,Qt.Key.Key_Return);QTest.keyClick(d.view,Qt.Key.Key_Enter);navigate.assert_not_called()
    select('child');QTest.keyClick(d.view,Qt.Key.Key_Return);navigate.assert_called_once_with(str(folder/'child'));navigate.reset_mock()
    QTest.keyClick(d.view,Qt.Key.Key_Enter);navigate.assert_called_once_with(str(folder/'child'));navigate.reset_mock()
    pos=d.view.visualRect(index('child')).center();QTest.mouseClick(d.view.viewport(),Qt.MouseButton.LeftButton,pos=pos);QTest.mouseDClick(d.view.viewport(),Qt.MouseButton.LeftButton,pos=pos)
    navigate.assert_called_once_with(str(folder/'child'))
d.search.setFocus();d.search.setText('A')
with patch.object(d,'navigate') as navigate:QTest.keyClick(d.search,Qt.Key.Key_Return);navigate.assert_not_called()
d.search.clear()
# Missing targets leave source, clipboard and library untouched and report the common status text.
gone=folder/'gone.png';Image.new('RGB',(10,10),'white').save(gone);d.navigate(d.folder,refresh=True);wait(lambda:not d.scan_job)
select('gone.png');d.preview_timer.stop();gone.unlink();copy_paths.reset_mock()
with patch.object(w,'add_paths') as add_paths,patch.object(w,'save_image_to_note') as save_note:
    assert d.add_selected() is False and d.save_selected_prompt() is False and d.copy_selection() is False
    add_paths.assert_not_called();save_note.assert_not_called();copy_paths.assert_not_called()
assert w.statusBar().currentMessage()=='파일을 찾을 수 없습니다: gone.png'
for default,mock in [(False,reveal),(True,open_default)]:
    mock.return_value=False;assert d.shell_open(str(gone),default) is False;assert w.statusBar().currentMessage()=='파일을 찾을 수 없습니다: gone.png';mock.return_value=True
with patch.object(d,'navigate') as navigate:
    assert d.open_folder(str(root/'missing')) is False and d.toggle_favorite(str(root/'missing')) is False;navigate.assert_not_called()
assert w.statusBar().currentMessage()=='파일을 찾을 수 없습니다: missing'
# Stale favorites stay removable, matching ignores case, and drive roots keep a readable name.
stale=root/'stale';stale.mkdir();assert d.toggle_favorite(str(stale)) and d.toggle_favorite(str(stale).upper()) and str(stale) not in d.state['favorites']
d.toggle_favorite(str(stale));stale.rmdir();assert d.toggle_favorite(str(stale)) and str(stale) not in d.state['favorites'] and favorite_present(str(stale))==(False,False)
d.paths_exist(['Q:\\']);assert w.statusBar().currentMessage()=='파일을 찾을 수 없습니다: Q:\\'
# Ctrl+A in read-only preview text selects that text, not the thumbnails.
d.view.clearSelection();d.metadata.setPlainText('line one\nline two');d.info_tabs.setCurrentIndex(2);app.processEvents();d.metadata.setFocus();app.processEvents()
QTest.keyClick(d.metadata,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);assert d.metadata.textCursor().hasSelection() and not d.view.selectedIndexes()
d.view.setFocus();app.processEvents();QTest.keyClick(d.view,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);assert len(d.view.selectedIndexes())==d.proxy.rowCount()>0
# A modifier-free key resets Qt's remembered Ctrl state before later selection checks.
QTest.keyClick(d.view,Qt.Key.Key_Escape);d.view.clearSelection()
d.navigate(d.folder,refresh=True);wait(lambda:not d.scan_job);assert select_context.call_count>0
d.activate(index('child'));wait(lambda:d.folder==str(folder/'child') and not d.scan_job);assert len(d.model.rows)==1
d.back.click();wait(lambda:d.folder==str(folder) and not d.scan_job);d.forward.click();wait(lambda:d.folder==str(folder/'child') and not d.scan_job)
next(b for b in d.findChildren(QPushButton) if b.text()=='↑ 상위').click();wait(lambda:d.folder==str(folder) and not d.scan_job)
d.navigate(str(root/'missing'));wait(lambda:not d.scan_job);assert d.folder==str(folder) and '열 수 없습니다' in d.status.text()
Image.new('RGB',(10,10),'white').save(folder/'new.png');d.navigate(d.folder,refresh=True);wait(lambda:not d.scan_job);assert len(d.model.rows)==4
# Rapid changes discard an obsolete scan and preview.
d.navigate(str(folder/'child'));d.navigate(str(folder));wait(lambda:not d.scan_job and d.folder==str(folder));assert len(d.model.rows)==4
d.view.setCurrentIndex(index('A.png'));d.view.setCurrentIndex(index('B.png'));wait(lambda:'B.png' in d.label.text() and d.viewer.image_rect.width()==120)
assert w.path is None and w.library.count()==0
# Register only the selected image; library editing state stays untouched.
d.add.click();wait(lambda:w.library.count()==1 and not w.jobs);assert str(b) in w.library_items and w.path is None
w.workspace_mode.setCurrentIndex(0);assert w.main_splitter.isVisible() and not d.isVisible()
copy_paths.reset_mock();w.viewer.setFocus();QTest.keyClick(w.viewer,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier);copy_paths.assert_not_called()
w.workspace_mode.setCurrentIndex(2);assert d.folder==str(folder)
d.size.setValue(200);w.grab().save(str(root/'disk-light.png'));d.save();w.workspace_mode.setCurrentIndex(0);wait(lambda:not w.jobs);w.close();app.processEvents();w.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
w=Studio(root/'user');w.show();w.workspace_mode.setCurrentIndex(2);d=w.disk_browser;wait(lambda:d.folder==str(folder) and not d.scan_job);assert str(folder) in d.state['favorites'] and d.size.value()==200 and w.library.count()==1
assert all(fingerprint(p)==h for p,h in hashes.items());assert {p.name for p in folder.iterdir()}=={'child','A.png','B.png','text.txt','new.png'}
w.close();wait(lambda:not w.jobs);app.processEvents();assert not errors,errors;w.deleteLater()
app.sendPostedEvents(None,QEvent.Type.DeferredDelete);guards.close()
print('PASS: thumbnail/folder/blank/tree/quick context menus, selection preservation, shell mocks, multiline copy, favorite synchronization, scoped shortcuts, single activation, missing paths, address/history/parent-folder navigation, refresh, filters/sort, lazy thumbnails, metadata, stale results, favorites/restart, explicit-only registration, source preservation. Capture:',root/'disk-light.png')
