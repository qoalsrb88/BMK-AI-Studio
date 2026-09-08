"""Browsing, selection and personal organization UI; no source-file mutations."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QPushButton,
    QLineEdit,QCheckBox,QInputDialog,QMenu,QListView,QDialog,QListWidget,QListWidgetItem,QPlainTextEdit,QDialogButtonBox)
from .organize import set_favorites,set_rating

def line(*widgets):
    host=QWidget();layout=QHBoxLayout(host);layout.setContentsMargins(0,0,0,0)
    for widget in widgets:layout.addWidget(widget)
    return host

def action(text,callback):
    widget=QPushButton(text);widget.clicked.connect(callback);return widget

class WorkspaceMixin:
    def viewer_actions(self):
        menu=QMenu(self)
        for label,callback in [('원본 보기',self.show_original),('작업본 보기',self.show_current),('전후 비교',self.compare_images),('이미지 복사',self.copy_image),('원본 파일 복사',self.copy_file),('편집 작업 보관',self.save_edit_session),('보관한 편집 작업 열기',self.open_edit_sessions)]:menu.addAction(label,callback)
        menu.exec(self.cursor().pos())

    def pin_compare(self):
        if not self.path:return
        self.compare_path=str(self.path);self.compare_button.setText('A/B 비교');self.compare_button.setToolTip('A: '+str(self.path))
        self.statusBar().showMessage('A 고정: '+self.path.name+' · 다른 이미지를 선택하고 A/B 비교를 누르세요.',5000)

    def compare_selection(self):
        first=getattr(self,'compare_path',None);second=str(self.path) if self.path else None
        if not first or not second or first==second:self.statusBar().showMessage('A를 고정한 뒤 다른 이미지 B를 선택하세요.');return
        from .core import inspect_image,load_image,file_stamp
        from .compare_browser import BrowserCompareDialog
        def read():
            result=[]
            for path in (first,second):
                stamp=file_stamp(path);info=inspect_image(path);image=load_image(path);image.thumbnail((2048,2048))
                if file_stamp(path)!=stamp:raise ValueError('비교 이미지를 읽는 중 파일이 변경되었습니다.')
                result.append((path,info,image))
            return result
        def show(result):
            if not self.closing_requested and str(self.path)==second and self.compare_path==first:BrowserCompareDialog(*result,self).exec()
        self.task(read,show)

    def build_browser_controls(self,layout):
        self.scope=QComboBox()
        for label,key in [('전체 이미지 정보','all'),('파일명','filename'),('원본 프롬프트','positive'),('원본 네거티브','negative'),('작업 텍스트','work'),('추정 태그','tags')]:self.scope.addItem(label,key)
        layout.addWidget(self.scope)
        self.filter_panel=QWidget();form=QVBoxLayout(self.filter_panel);form.setContentsMargins(0,0,0,0)
        self.source_filter=QLineEdit();self.source_filter.setPlaceholderText('출처에 포함된 말 (예: ComfyUI)')
        self.models_filter=QLineEdit();self.models_filter.setPlaceholderText('기록된 모델·LoRA 이름');self.models_filter.setToolTip('ComfyUI 그래프에 기록된 후보도 포함합니다. 실제 실행 분기를 확정하지 않습니다.')
        self.pixels_filter=QComboBox()
        for label,value in [('모든 해상도',0),('1 MP 이상',1000000),('4 MP 이상',4000000),('16 MP 이상',16000000)]:self.pixels_filter.addItem(label,value)
        self.days_filter=QComboBox()
        for label,value in [('파일 수정일 전체',0),('파일 수정일 최근 7일',7),('파일 수정일 최근 30일',30)]:self.days_filter.addItem(label,value)
        self.aspect_filter=QComboBox()
        for label,key in [('모든 종횡비',''),('세로','portrait'),('가로','landscape'),('정사각','square'),('크기 정보 없음','unknown')]:self.aspect_filter.addItem(label,key)
        self.tagged_filter=QComboBox()
        for label,key in [('태깅 여부 전체',''),('태깅 완료','yes'),('미태깅','no')]:self.tagged_filter.addItem(label,key)
        self.favorite_filter=QCheckBox('즐겨찾기만')
        self.rating_filter=QComboBox();self.rating_filter.addItem('개인 별점 전체',0)
        for n in range(1,6):self.rating_filter.addItem(f'★ {n} 이상',n)
        for widget in (self.source_filter,self.models_filter,self.aspect_filter,self.pixels_filter,self.days_filter,self.tagged_filter,self.favorite_filter,self.rating_filter):form.addWidget(widget)
        self.filter_panel.hide();toggle=action('상세 필터',lambda:self.filter_panel.setVisible(not self.filter_panel.isVisible()))
        layout.addWidget(line(toggle,action('모두 해제',self.clear_browser_filters)));layout.addWidget(self.filter_panel)
        self.collection_filter=QComboBox();self.refresh_collections()
        layout.addWidget(self.collection_filter)
        layout.addWidget(line(action('컬렉션 만들기',self.new_collection),action('관리',self.collection_menu)))
        self.saved_search=QComboBox();self.saved_search.addItem('저장된 검색 선택',None)
        self.refresh_saved_searches();layout.addWidget(self.saved_search)
        layout.addWidget(line(action('검색 저장',self.save_search),action('검색 삭제',self.delete_search)))
        self.filter_summary=QLabel('전체 이미지');self.filter_summary.setWordWrap(True);layout.addWidget(self.filter_summary)
        self.scope.currentIndexChanged.connect(self.apply_browser_filters)
        self.source_filter.textChanged.connect(self.apply_browser_filters)
        self.models_filter.textChanged.connect(self.apply_browser_filters)
        for combo in (self.aspect_filter,self.pixels_filter,self.days_filter,self.tagged_filter,self.rating_filter,self.collection_filter):combo.currentIndexChanged.connect(self.apply_browser_filters)
        self.favorite_filter.toggled.connect(self.apply_browser_filters)
        self.saved_search.activated.connect(self.restore_search)
        self.build_discovery_controls(layout)

    def browser_filters(self):
        values={'scope':self.scope.currentData(),'source':self.source_filter.text().strip(),'aspect':self.aspect_filter.currentData(),
                'models':self.models_filter.text().strip(),'pixels':self.pixels_filter.currentData(),'days':self.days_filter.currentData(),
                'tagged':self.tagged_filter.currentData(),'favorite':self.favorite_filter.isChecked(),'rating':self.rating_filter.currentData(),'collection':self.collection_filter.currentData()}
        return {key:value for key,value in {**values,**self.date_filters}.items() if value and value!='all'}

    def apply_browser_filters(self,*args):
        if not hasattr(self,'library'):return
        self.library.filters=self.browser_filters();self.library.set_query(self.search.text())
        labels=[]
        if self.search.text().strip():labels.append('검색: '+self.search.text())
        if self.scope.currentData()!='all':labels.append(self.scope.currentText())
        if self.source_filter.text().strip():labels.append('출처: '+self.source_filter.text().strip())
        if self.models_filter.text().strip():labels.append('모델·LoRA 후보: '+self.models_filter.text().strip())
        for widget in (self.aspect_filter,self.pixels_filter,self.days_filter,self.tagged_filter,self.rating_filter,self.collection_filter):
            if widget.currentData():labels.append(widget.currentText())
        if self.favorite_filter.isChecked():labels.append('즐겨찾기')
        if self.date_filters:labels.append(('생성일' if self.date_filters.get('date_kind')=='generated' else '수정일')+' '+('미상' if self.date_filters.get('date_unknown') else self.date_filters.get('date_from','')+' ~ '+self.date_filters.get('date_to','')))
        if self.library.transient_paths is not None:labels.append(f'발견 결과 {len(self.library.transient_paths)}개 안에서 검색 · 모두 해제로 복귀')
        self.filter_summary.setText(' · '.join(labels) or '전체 이미지')

    def clear_browser_filters(self):
        self.date_filters={};self.library.transient_paths=None
        self.source_filter.clear();self.models_filter.clear();self.search.clear();self.favorite_filter.setChecked(False);self.saved_search.setCurrentIndex(0)
        for widget in (self.scope,self.aspect_filter,self.pixels_filter,self.days_filter,self.tagged_filter,self.rating_filter,self.collection_filter):widget.setCurrentIndex(0)
        self.apply_browser_filters()

    def refresh_collections(self):
        selected=self.collection_filter.currentData();self.collection_filter.blockSignals(True);self.collection_filter.clear();self.collection_filter.addItem('모든 컬렉션',None)
        for name, in self.store.db.execute('SELECT name FROM collections ORDER BY name'):self.collection_filter.addItem(name,name)
        self.collection_filter.setCurrentIndex(max(0,self.collection_filter.findData(selected)));self.collection_filter.blockSignals(False)
        if hasattr(self,'collection_drop'):
            self.collection_drop.clear();self.collection_drop.addItems([name for name, in self.store.db.execute('SELECT name FROM collections ORDER BY name')])

    def new_collection(self):
        name,ok=QInputDialog.getText(self,'컬렉션 만들기','이름 (원본 파일 위치는 유지됩니다)')
        if ok and name.strip():
            with self.store.db:self.store.db.execute('INSERT OR IGNORE INTO collections VALUES(?)',(name.strip(),))
            self.refresh_collections();self.statusBar().showMessage('컬렉션 생성 완료 · 이미지 선택 후 추가하거나 드롭 영역으로 드래그하세요.',5000)

    def collection_menu(self):
        name=self.collection_filter.currentData()
        menu=QMenu(self)
        if name:
            menu.addAction('선택 이미지를 이 컬렉션에서 빼기',lambda:self.assign_collection(name,False))
            menu.addAction('컬렉션 이름 변경',lambda:self.rename_collection(name))
            menu.addAction('컬렉션 삭제 · 원본 유지',lambda:self.delete_collection(name))
        if self.store.state('last_deleted_collection'):menu.addAction('마지막 컬렉션 삭제 복원',self.undo_deleted_collection)
        if not menu.actions():self.statusBar().showMessage('관리할 컬렉션을 먼저 선택하세요.');return
        menu.exec(self.cursor().pos())

    def rename_collection(self,old):
        name,ok=QInputDialog.getText(self,'컬렉션 이름 변경','이름',text=old)
        if not ok or not name.strip() or name.strip()==old:return
        name=name.strip()
        if self.store.db.execute('SELECT 1 FROM collections WHERE name=?',(name,)).fetchone():self.error('이미 같은 이름의 컬렉션이 있습니다.');return
        with self.store.db:
            self.store.db.execute('UPDATE collections SET name=? WHERE name=?',(name,old));self.store.db.execute('UPDATE collection_items SET name=? WHERE name=?',(name,old))
        searches=self.store.state('saved_searches') or {}
        for value in searches.values():
            if value.get('filters',{}).get('collection')==old:value['filters']['collection']=name
        self.store.state('saved_searches',searches);self.refresh_collections();self.collection_filter.setCurrentIndex(self.collection_filter.findData(name))

    def selection_paths(self):return [item.path for item in self.library.selectedItems()]

    def selection_menu(self):
        paths=self.selection_paths()
        if not paths:return
        menu=QMenu(self)
        menu.addAction('즐겨찾기 추가',lambda:self.mark_favorite(True));menu.addAction('즐겨찾기 해제 (별점도 해제)',lambda:self.mark_favorite(False))
        ratings=menu.addMenu('개인 별점 · 모델 rating과 별개')
        for n in range(6):ratings.addAction('별점 해제' if n==0 else '★'*n,lambda checked=False,value=n:self.rate_selection(value))
        collections=menu.addMenu('컬렉션에 추가')
        for name, in self.store.db.execute('SELECT name FROM collections ORDER BY name'):collections.addAction(name,lambda checked=False,value=name:self.assign_collection(value,True))
        if not collections.actions():collections.addAction('왼쪽에서 컬렉션을 먼저 만드세요').setEnabled(False)
        menu.addSeparator();menu.addAction('태깅 대기열에 추가',self.enqueue_selected);menu.addAction('목록에서 제거 · 원본 유지',self.remove_library_selection)
        menu.exec(self.cursor().pos())

    def mark_favorite(self,on):
        paths=self.selection_paths();set_favorites(self.store.db,paths,on);self.refresh_favorite_badges();self.library.refresh_query();self.update_workspace_status()
        self.statusBar().showMessage(f'{len(paths)}개 즐겨찾기 '+('추가' if on else '해제'),4000)

    def rate_selection(self,n):
        paths=self.selection_paths();set_rating(self.store.db,paths,n);self.refresh_favorite_badges();self.library.refresh_query();self.update_workspace_status()

    def refresh_favorite_badges(self):
        self.library.favorite_ratings=dict(self.store.db.execute('SELECT path,rating FROM favorites'))
        if self.library.count():self.library.records.dataChanged.emit(self.library.records.index(0),self.library.records.index(self.library.count()-1),[Qt.ItemDataRole.DisplayRole])

    def assign_collection(self,name,on):
        paths=self.selection_paths()
        with self.store.db:
            sql='INSERT OR IGNORE INTO collection_items VALUES(?,?)' if on else 'DELETE FROM collection_items WHERE name=? AND path=?'
            self.store.db.executemany(sql,[(name,path) for path in paths])
        self.library.refresh_query();self.statusBar().showMessage(f'{len(paths)}개 · {name} '+('추가' if on else '소속 해제'),4000)

    def refresh_saved_searches(self):
        self.saved_search.clear();self.saved_search.addItem('저장된 검색 선택',None)
        for name in sorted(self.store.state('saved_searches') or {}):self.saved_search.addItem(name,name)

    def save_search(self):
        name,ok=QInputDialog.getText(self,'검색 저장','새 검색 이름')
        if not ok or not name.strip():return
        values=self.store.state('saved_searches') or {};name=name.strip()
        if name in values:self.error('같은 이름이 있습니다. 다른 이름으로 저장하세요.');return
        values[name]={'query':self.search.text(),'filters':self.browser_filters()};self.store.state('saved_searches',values);self.refresh_saved_searches()

    def delete_search(self):
        name=self.saved_search.currentData();values=self.store.state('saved_searches') or {}
        if name in values:values.pop(name);self.store.state('saved_searches',values);self.refresh_saved_searches()

    def restore_search(self,*args):
        value=(self.store.state('saved_searches') or {}).get(self.saved_search.currentData())
        if not value:return
        self.set_browser_state(value)

    def set_browser_state(self,value):
        filters=value.get('filters',{});self.search.setText(value.get('query',''));self.source_filter.setText(filters.get('source',''));self.models_filter.setText(filters.get('models',''));self.favorite_filter.setChecked(bool(filters.get('favorite')))
        self.date_filters={key:filters[key] for key in ('date_kind','date_from','date_to','date_unknown') if key in filters}
        name=filters.get('collection')
        if name and self.collection_filter.findData(name)<0:self.collection_filter.addItem('[없는 컬렉션] '+name,name)
        for key,widget in [('scope',self.scope),('aspect',self.aspect_filter),('pixels',self.pixels_filter),('days',self.days_filter),('tagged',self.tagged_filter),('rating',self.rating_filter),('collection',self.collection_filter)]:widget.setCurrentIndex(max(0,widget.findData(filters.get(key))))
        self.apply_browser_filters()

    def switch_workspace(self,*args):
        if not hasattr(self,'workspace_mode'):return
        old=getattr(self,'active_workspace',None)
        if old:
            self.workspace_positions[old]=[self.library.horizontalScrollBar().value(),self.library.verticalScrollBar().value()]
            self.workspace_sizes[old]=self.main_splitter.sizes()
        mode=self.workspace_mode.currentData();self.active_workspace=mode;browsing=mode=='browse'
        self.main_splitter.setVisible(mode!='disk');self.disk_browser.setVisible(mode=='disk');self.disk_browser.set_active(mode=='disk')
        self.workspace_to_main(mode)
        if mode=='disk':
            self.library.large.pause();return
        self.preview_panel.setVisible(not browsing)
        self.library.setViewMode(QListView.ViewMode.IconMode);self.library.setMovement(QListView.Movement.Static)
        self.library.setFlow(QListView.Flow.LeftToRight);self.library.setWrapping(browsing);self.library.setResizeMode(QListView.ResizeMode.Adjust)
        size=self.thumbnail_slider.value() if browsing else 64
        self.library.setMinimumHeight(110 if browsing else size+70);self.library.setMaximumHeight(16777215 if browsing else size+80)
        self.library.set_thumbnail_size(size);self.library.setWordWrap(False)
        self.main_splitter.setSizes(self.workspace_sizes.get(mode,[265,850,370]))
        def restore():
            x,y=self.workspace_positions.get(mode,[0,0]);self.library.horizontalScrollBar().setValue(x);self.library.verticalScrollBar().setValue(y)
            if mode=='work' and not getattr(self,'workspace_has_fit',False):self.viewer.fit();self.workspace_has_fit=True
        QTimer.singleShot(0,restore)

    def initialize_workspace(self):
        state=self.store.state('browser_workspace') or {};self.workspace_positions=state.get('positions',{});self.workspace_sizes=state.get('sizes',{})
        self.refresh_favorite_badges()
        self.set_browser_state(state);self.note_search.setText(state.get('note_query',''))
        self.workspace_mode.setCurrentIndex(max(0,self.workspace_mode.findData(state.get('mode','browse'))));self.switch_workspace()
        self.workspace_timer=QTimer(self);self.workspace_timer.setInterval(500);self.workspace_timer.timeout.connect(self.update_workspace_status);self.workspace_timer.start()
        self.library.selectionModel().selectionChanged.connect(self.update_workspace_status)
        self.library.searching.connect(self.update_workspace_status)
        self.update_workspace_status()

    def save_browser_state(self):
        if not hasattr(self,'active_workspace'):return
        mode=self.active_workspace;self.workspace_positions[mode]=[self.library.horizontalScrollBar().value(),self.library.verticalScrollBar().value()];self.workspace_sizes[mode]=self.main_splitter.sizes()
        self.disk_browser.save();self.save_main_workspace()
        self.store.state('browser_workspace',{'query':self.search.text(),'filters':self.browser_filters(),'note_query':self.note_search.text(),'mode':mode,'positions':self.workspace_positions,'sizes':self.workspace_sizes})

    def update_workspace_status(self,*args):
        if self.closing_requested:return
        paths=self.selection_paths();self.selection_label.setText(f'선택 {len(paths)}개')
        self.selection_actions.setEnabled(bool(paths))
        self.browser_count.setText(f'{self.library.proxy.rowCount()} / {self.library.count()}개'+(' · 검색 중' if self.library.search_pending else ''))
        text='텍스트 저장 대기' if self.autosave.isActive() else '텍스트 저장됨'
        if self.path:
            state=self.edit_state();text+=' · '+('이미지 미내보내기' if self.operations and state!=self.exported_state else '이미지 변경 없음 / 내보내기 완료')
            if self.checkpoint_state==state and self.operations:text+=' · 편집 보관됨'
            if self.recovery_saved.get(str(self.path))==state:text+=' · 현재 편집 복구본 저장됨'
            fav=self.store.db.execute('SELECT rating FROM favorites WHERE path=?',(str(self.path),)).fetchone()
            if fav:text+=' · 즐겨찾기'+(' ★'+str(fav[0]) if fav[0] else '')
        self.save_status.setText(text)
        jobs=[]
        if self.index_job or self.pending_index:jobs.append(f'색인 대기 {len(self.pending_index)}')
        if self.tag_busy or self.queue_running:jobs.append('태깅 진행 중')
        if self.library.search_pending:jobs.append('검색 중')
        if self.watch_toggle.isChecked():jobs.append('폴더 감시 중')
        if self.jobs:jobs.append(f'백그라운드 작업 {len(self.jobs)}개')
        self.jobs_status.setText(' · '.join(jobs) or '작업 대기')

    def prompt_snippets(self):
        dialog=QDialog(self);dialog.setWindowTitle('프롬프트 조각 · 기존 노트에서 가져오기');dialog.resize(650,600);layout=QVBoxLayout(dialog)
        search=QLineEdit();search.setPlaceholderText('노트 검색');layout.addWidget(search);items=QListWidget();layout.addWidget(items)
        preview=QPlainTextEdit();preview.setReadOnly(True);layout.addWidget(preview)
        pins=set(self.store.state('pinned_notes') or [])
        def populate():
            items.clear();preview.clear()
            records=self.store.note_entries(search.text())
            for nid,title,body,category,*rest in sorted(records,key=lambda r:(r[0] not in pins,r[1])):
                item=QListWidgetItem(('★ ' if nid in pins else '')+title+(' · '+category if category else ''));item.setData(Qt.ItemDataRole.UserRole,nid);items.addItem(item)
        def selected():
            item=items.currentItem();record=self.store.note(item.data(Qt.ItemDataRole.UserRole)) if item else None
            return json.loads(record[2]).get('prompt','') if record else ''
        def pin():
            item=items.currentItem()
            if not item:return
            nid=item.data(Qt.ItemDataRole.UserRole);pins.remove(nid) if nid in pins else pins.add(nid);self.store.state('pinned_notes',sorted(pins));populate()
        def use(replace=False):
            text=selected()
            if not text:return
            from .app import replace_text
            existing=self.draft.toPlainText();replace_text(self.draft,text if replace else existing+('\n' if existing else '')+text);dialog.accept()
        search.textChanged.connect(populate);items.currentItemChanged.connect(lambda *args:preview.setPlainText(selected()));populate()
        layout.addWidget(line(action('고정 / 해제',pin),action('현재 프롬프트에 추가',use),action('현재 프롬프트 교체',lambda:use(True))))
        layout.addWidget(QLabel('현재 열린 작업/노트에 적용 · 원문 문법 유지 · Ctrl+Z로 되돌리기'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()
