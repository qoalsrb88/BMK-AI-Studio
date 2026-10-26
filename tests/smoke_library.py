import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,tempfile,io
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from PySide6.QtCore import Qt,QPoint,QSettings,QItemSelectionModel
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QSignalSpy,QTest
from PySide6.QtWidgets import QApplication,QWidget,QMenu
from bmk_studio.app import Studio,configure_app
from bmk_studio.core import fingerprint,file_stamp
from bmk_studio.library_view import LibraryView
from bmk_studio import shell_actions

root=Path(tempfile.mkdtemp(prefix='bmk-library-')).resolve()
class TestNavigation(QWidget):
    def __init__(self,panel):super().__init__()
    def sync(self):pass
    def refresh_quick(self):pass

patches=ExitStack()
patches.enter_context(patch('bmk_studio.app.QSettings',side_effect=lambda *args:QSettings(str(root/'qt.ini'),QSettings.Format.IniFormat)))
patches.enter_context(patch('bmk_studio.disk_browser.NavigationPane',TestNavigation))
exec_menu=Mock()
def make_menu(*args):
    menu=QMenu(*args);menu.exec=lambda *position:exec_menu(menu,*position);return menu
patches.enter_context(patch('bmk_studio.workspace.QMenu',side_effect=make_menu))
open_default=patches.enter_context(patch.object(shell_actions,'open_default',return_value=True))
reveal=patches.enter_context(patch.object(shell_actions,'reveal_in_explorer',return_value=True))
copy_paths=patches.enter_context(patch.object(shell_actions,'copy_paths',wraps=shell_actions.copy_paths))
context_select=patches.enter_context(patch.object(shell_actions,'select_for_context',wraps=shell_actions.select_for_context))

app=QApplication([]);configure_app(app)
view=LibraryView();view.resize(350,600)
buffer=io.BytesIO();Image.new('RGB',(96,96),'red').save(buffer,format='PNG');blob=buffer.getvalue()
start=time.perf_counter()
for i in range(20000):
    item=view.add_path(f'/synthetic/{i}.png',f'Image {i}');view.update_item(item,search=f'group{i%20} sample{i}',blob=blob)
insert_time=time.perf_counter()-start
assert view.records.decode_count==0
view.show();app.processEvents();assert len(view.records.icons)<256
start=time.perf_counter();view.set_query('group19 sample');app.processEvents();filter_time=time.perf_counter()-start
assert view.proxy.rowCount()==1000
view.set_query('nomatch');assert view.proxy.rowCount()==0
view.close()
path=root/'image.png';Image.new('RGB',(64,64)).save(path);before=fingerprint(path)
w=Studio(root/'data');w.add_paths([path]);w.show()
def wait(window=None):
    window=window or w
    deadline=time.monotonic()+15
    while (window.jobs or window.library.search_pending) and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
    assert not window.jobs and not window.library.search_pending
wait();w.draft.setPlainText('privateworkterm');w.save_draft();w.search.setText('privateworkterm');wait();assert w.library.proxy.rowCount()==1
result={'scores':[{'tag':'red_hair','category':0,'score':.9},{'tag':'unlikely','category':0,'score':.01}]}
w.store.record_tag_run(path,'fake',file_stamp(path),'cache',result)
w.update_library_search(str(path));w.search.setText('red hair');wait();assert w.library.proxy.rowCount()==1
w.search.setText('unlikely');wait();assert w.library.proxy.rowCount()==0
w.search.clear();record=w.store.indexed_images()[0];w.remove_library_paths([path]);w.index_ready(record)
assert w.library.count()==0 and fingerprint(path)==before and w.store.asset(path)[0]=='privateworkterm'
w.add_paths([path],False,False);assert w.library.count()==0
w.close();app.processEvents();w=Studio(root/'data');assert w.library.count()==0
w.add_paths([path]);wait();assert w.library.count()==1
w.search.setText('red hair');wait();assert w.library.proxy.rowCount()==1
w.close();app.processEvents()

def context_checks(paged):
    folder=root/('paged' if paged else 'memory');target=folder/'target';target.mkdir(parents=True)
    paths=[target/name for name in ('a.png','b, 둘.png','c.png')]
    for source in paths:Image.new('RGB',(64,64),'blue').save(source)
    hashes={source:fingerprint(source) for source in paths}
    window=Studio(folder/'data');library=window.library
    if not paged:library.database=None;library.pages=None
    window.add_paths(paths,open_first=False);window.show();wait(window);app.processEvents()
    missing=target/'missing.png';item=library.add_path(str(missing),missing.name);window.library_items[str(missing)]=item
    library.doItemsLayout()
    expected=['즐겨찾기 추가','즐겨찾기 해제 (별점도 해제)','개인 별점 · 모델 rating과 별개','컬렉션에 추가','',
              '태깅 대기열에 추가','목록에서 제거 · 원본 유지','','기본 앱으로 열기','탐색기에서 위치 열기',
              '파일 탐색 탭에서 이 폴더 열기','경로 복사','파일명 복사']
    def select(*rows):
        library.clearSelection()
        for row in rows:library.selectionModel().select(library.proxy.index(row,0),QItemSelectionModel.SelectionFlag.Select)
        if rows:library.selectionModel().setCurrentIndex(library.proxy.index(rows[0],0),QItemSelectionModel.SelectionFlag.NoUpdate)
    def context(row=None):
        index=library.proxy.index(row,0) if row is not None else None
        position=library.visualRect(index).center() if index is not None else QPoint(library.viewport().width()-5,library.viewport().height()-5)
        assert library.indexAt(position).isValid()==(row is not None)
        exec_menu.reset_mock();context_select.reset_mock()
        clicked=QSignalSpy(library.clicked);opened=QSignalSpy(library.itemClicked)
        with patch.object(window,'load') as load:
            QTest.mouseClick(library.viewport(),Qt.MouseButton.RightButton,Qt.KeyboardModifier.NoModifier,position)
            event=QContextMenuEvent(QContextMenuEvent.Reason.Mouse,position,library.viewport().mapToGlobal(position))
            QApplication.sendEvent(library.viewport(),event)
            load.assert_not_called();assert clicked.count()==0 and opened.count()==0
        exec_menu.assert_called_once();menu=exec_menu.call_args.args[0]
        if row is not None:context_select.assert_called_once_with(library,index)
        else:context_select.assert_not_called()
        return menu,{entry.text():entry for entry in menu.actions()}
    select(0,1);menu,items=context(1)
    assert set(window.selection_paths())=={str(paths[0]),str(paths[1])}
    assert [entry.text() for entry in menu.actions()]==expected
    assert [entry.isSeparator() for entry in menu.actions()]==[not label for label in expected]
    assert not items['기본 앱으로 열기'].isEnabled() and items['탐색기에서 위치 열기'].isEnabled()
    assert items['목록에서 제거 · 원본 유지'].shortcut().toString()=='Del'
    assert len(items['개인 별점 · 모델 rating과 별개'].menu().actions())==6
    assert not items['컬렉션에 추가'].menu().actions()[0].isEnabled()
    selected=window.selection_paths();items['경로 복사'].trigger()
    copy_paths.assert_called_with(selected,names=False);assert app.clipboard().text()=='\n'.join(selected)
    assert window.statusBar().currentMessage()=='경로 2개를 복사했습니다.'
    items['파일명 복사'].trigger();copy_paths.assert_called_with(selected,names=True)
    assert app.clipboard().text()=='\n'.join(Path(value).name for value in selected)
    assert window.statusBar().currentMessage()=='파일명 2개를 복사했습니다.'
    reveal.reset_mock();items['탐색기에서 위치 열기'].trigger();reveal.assert_called_once_with(str(paths[1]))
    menu,items=context(2);assert window.selection_paths()==[str(paths[2])]
    assert all(items[label].isEnabled() for label in expected[8:11])
    open_default.reset_mock();items['기본 앱으로 열기'].trigger();open_default.assert_called_once_with(str(paths[2]))
    with patch.object(shell_actions,'open_default',return_value=False):items['기본 앱으로 열기'].trigger()
    assert window.statusBar().currentMessage()=='파일을 찾을 수 없습니다: c.png'
    exec_menu.reset_mock();window.selection_actions.click();exec_menu.assert_called_once()
    assert [entry.text() for entry in exec_menu.call_args.args[0].actions()]==expected
    select();exec_menu.reset_mock();window.selection_menu();exec_menu.assert_not_called()
    menu,items=context(3)
    assert all(not items[label].isEnabled() for label in expected[8:11]) and items['경로 복사'].isEnabled()
    items['경로 복사'].trigger();assert app.clipboard().text()==str(missing)
    menu,items=context();assert [entry.text() for entry in menu.actions()]==['모두 선택','목록 제거 되돌리기']
    assert items['모두 선택'].shortcut().toString()=='Ctrl+A' and not items['목록 제거 되돌리기'].isEnabled()
    items['모두 선택'].trigger();assert len(window.selection_paths())==4
    # Two scans started by tab activation must not overwrite the final requested folder.
    old=folder/'old';old.mkdir();Image.new('RGB',(8,8)).save(old/'old.png');panel=window.disk_browser;panel.state['folder']=str(old)
    menu,items=context(1)
    with patch.object(window,'run_discovery') as run:
        items['파일 탐색 탭에서 이 폴더 열기'].trigger()
        assert window.main_tabs.currentIndex()==0 and panel.active
        scans=list(run.call_args_list);assert len(scans)>=2
        scans[-1].args[2](scans[-1].args[1](type('Job',(),{'isInterruptionRequested':lambda self:False})()))
        for call in reversed(scans[:-1]):call.args[2]((([(str(old/'old.png'),'old.png',False,0,0)],0),None))
        assert panel.folder==str(target) and {row[1] for row in panel.model.rows}=={source.name for source in paths}
    panel.scan_job=None;window.main_tabs.setCurrentIndex(1);app.processEvents()
    menu,items=context(0);items['파일 탐색 탭에서 이 폴더 열기'].trigger();wait(window)
    assert panel.folder==str(target) and window.main_tabs.currentIndex()==0
    window.main_tabs.setCurrentIndex(1);app.processEvents();select(0,1);library.setFocus();app.processEvents();assert library.hasFocus()
    for modifier in (Qt.KeyboardModifier.ControlModifier,Qt.KeyboardModifier.ShiftModifier,Qt.KeyboardModifier.AltModifier):
        QTest.keyClick(library,Qt.Key.Key_Delete,modifier);assert library.count()==4 and not window.removal_history
    QTest.keyClick(library,Qt.Key.Key_Delete);assert library.count()==2 and len(window.removal_history)==1
    assert '2개 항목을 목록에서 제거했습니다.' in window.statusBar().currentMessage()
    menu,items=context();assert items['목록 제거 되돌리기'].isEnabled();items['목록 제거 되돌리기'].trigger();wait(window)
    assert library.count()==4 and not window.removal_history
    select(0);window.search.setFocus();window.search.setText('c.png');window.search.setCursorPosition(0)
    QTest.keyClick(window.search,Qt.Key.Key_Delete);assert window.search.text()=='.png' and library.count()==4 and not window.removal_history
    wait(window);window.search.clear();wait(window);select(0)
    window.image_view_modes.setCurrentIndex(1);app.processEvents();window.draft.setFocus();window.draft.setPlainText('xy')
    QTest.keyClick(window.draft,Qt.Key.Key_Delete);assert window.draft.toPlainText()=='y' and library.count()==4 and not window.removal_history
    window.image_view_modes.setCurrentIndex(0);app.processEvents();select(0);library.setFocus();app.processEvents()
    with patch.object(window,'load') as load:
        QTest.keyClick(library,Qt.Key.Key_Right);assert load.called
        load.reset_mock();QTest.keyClick(library,Qt.Key.Key_Return);assert load.called
    menu,items=context(0);items['목록에서 제거 · 원본 유지'].trigger();assert library.count()==3
    window.undo_library_removal();wait(window);assert library.count()==4
    select(next(r for r in range(library.proxy.rowCount()) if library.proxy.index(r,0).data(Qt.ItemDataRole.UserRole)!=str(missing)))
    library.setFocus();QTest.keyClick(library,Qt.Key.Key_Delete,Qt.KeyboardModifier.KeypadModifier);assert library.count()==3 and len(window.removal_history)==1
    window.undo_library_removal();wait(window);assert library.count()==4
    select();library.setFocus();QTest.keyClick(library,Qt.Key.Key_Delete);assert not window.removal_history
    assert all(fingerprint(source)==digest for source,digest in hashes.items())
    window.close();app.processEvents()

context_checks(True);context_checks(False)
patches.close()
print(f'PASS: 20,000 records, lazy bounded thumbnail cache; insertion {insert_time:.2f}s, filter {filter_time:.2f}s; work/tag search; remove/restart/stale-index/watch exclusion; explicit re-add; source hash preserved')
print('PASS: paged/memory context menus, right-click selection without loading, shell/copy actions, stale folder scans, Delete/undo, search/editor focus and arrow/Enter keys; all source hashes preserved')
