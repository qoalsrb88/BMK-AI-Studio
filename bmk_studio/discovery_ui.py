"""Follow-up discovery tools integrated into the local workspace."""
import json,calendar
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QDate,QStringListModel
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QComboBox,QDateEdit,QCheckBox,QDialogButtonBox,
    QListWidget,QListWidgetItem,QTreeWidget,QTreeWidgetItem,QLineEdit,QSpinBox,QCompleter,QFileDialog,QInputDialog)
from .workspace import line,action
from .background import ManagedJob,JobCenter
from .collection_drop import CollectionDropList

class DiscoveryMixin:
    def run_discovery(self,title,fn,callback):
        job=ManagedJob(title,fn,self);self.jobs.append(job)
        job.result.connect(lambda result:self.safe(lambda:callback(result)) if not self.closing_requested else None)
        job.failed.connect(lambda error:self.statusBar().showMessage(error,8000) if job.outcome=='취소됨' else self.error(error))
        def finish():
            self.jobs.remove(job);self.completed_jobs=(getattr(self,'completed_jobs',[])+[(title,job.outcome)])[-30:];job.deleteLater()
        job.finished.connect(finish);job.start();return job

    def build_discovery_controls(self,layout):
        self.date_filters={};self.discovery_generation=0;self.completion_job=None
        self.completion_model=QStringListModel(self);self.completer=QCompleter(self.completion_model,self);self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search.setCompleter(self.completer);self.completion_timer=QTimer(self);self.completion_timer.setSingleShot(True);self.completion_timer.setInterval(300);self.completion_timer.timeout.connect(self.request_completion)
        self.search.textEdited.connect(lambda text:self.completion_timer.start())
        layout.addWidget(line(action('날짜 / 타임라인',self.date_dialog),action('작업 목록',lambda:JobCenter(self).exec())))
        layout.addWidget(line(action('유사 이미지',self.find_similar),action('의미 검색',self.semantic_dialog)))
        self.collection_drop=CollectionDropList(self);self.collection_drop.hide();self.collection_drop.referencesDropped.connect(self.drop_collection)
        self.collection_drop.itemClicked.connect(lambda item:self.collection_filter.setCurrentIndex(self.collection_filter.findData(item.text())))
        layout.addWidget(action('컬렉션 드롭 영역',lambda:self.collection_drop.setVisible(not self.collection_drop.isVisible())))
        layout.addWidget(self.collection_drop);self.refresh_collections()

    def request_completion(self):
        if self.closing_requested or self.library.stopped:return
        text=self.search.text();scope=self.scope.currentData()
        if self.completion_job:self.completion_job.requestInterruption()
        if len(text.rsplit(' ',1)[-1])<2:self.completion_model.setStringList([]);return
        from .discovery import completions
        def ready(words):
            if text==self.search.text() and scope==self.scope.currentData():
                self.completion_model.setStringList(words)
                if words and self.search.hasFocus():self.completer.setCompletionPrefix(text);self.completer.complete()
        job=self.run_discovery('검색어 자동완성',lambda j:completions(self.library.database,text,scope,j.isInterruptionRequested),ready);self.completion_job=job
        job.finished.connect(lambda:setattr(self,'completion_job',None) if self.completion_job is job else None)

    def drop_collection(self,name,paths):
        if not self.store.db.execute('SELECT 1 FROM collections WHERE name=?',(name,)).fetchone():return
        paths=list(dict.fromkeys(p for p in paths if p in self.library_items))
        with self.store.db:self.store.db.executemany('INSERT OR IGNORE INTO collection_items VALUES(?,?)',[(name,path) for path in paths])
        self.library.refresh_query();self.statusBar().showMessage(f'{name}에 {len(paths)}개 추가 · 원본 위치 유지',5000)

    def delete_collection(self,name):
        paths=[path for path, in self.store.db.execute('SELECT path FROM collection_items WHERE name=?',(name,))]
        self.store.state('last_deleted_collection',{'name':name,'paths':paths})
        with self.store.db:
            self.store.db.execute('DELETE FROM collection_items WHERE name=?',(name,));self.store.db.execute('DELETE FROM collections WHERE name=?',(name,))
        self.refresh_collections();self.apply_browser_filters();self.statusBar().showMessage('컬렉션 삭제 · 원본 유지 · 관리 메뉴에서 마지막 삭제 복원',8000)

    def undo_deleted_collection(self):
        saved=self.store.state('last_deleted_collection') or {};name=saved.get('name')
        if not name:return
        if self.store.db.execute('SELECT 1 FROM collections WHERE name=?',(name,)).fetchone():self.error('같은 이름이 이미 있습니다. 기존 컬렉션의 이름을 바꾼 뒤 복원하세요.');return
        with self.store.db:
            self.store.db.execute('INSERT INTO collections VALUES(?)',(name,));self.store.db.executemany('INSERT INTO collection_items VALUES(?,?)',[(name,path) for path in saved.get('paths',[])])
        self.store.state('last_deleted_collection',{});self.refresh_collections();self.collection_filter.setCurrentIndex(self.collection_filter.findData(name))

    def date_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle('날짜 범위 / 월별 타임라인');dialog.resize(520,560);layout=QVBoxLayout(dialog)
        kind=QComboBox();kind.addItem('파일 수정일','modified');kind.addItem('원본에 명시된 생성일 (없으면 미상)','generated');kind.setCurrentIndex(max(0,kind.findData(self.date_filters.get('date_kind','modified'))));layout.addWidget(kind)
        enabled=QCheckBox('날짜 범위 적용');enabled.setChecked(bool(self.date_filters.get('date_from')));layout.addWidget(enabled)
        start=QDateEdit();end=QDateEdit()
        for widget,key,default in [(start,'date_from',QDate.currentDate().addMonths(-1)),(end,'date_to',QDate.currentDate())]:
            widget.setCalendarPopup(True);widget.setDisplayFormat('yyyy-MM-dd');value=QDate.fromString(self.date_filters.get(key,''),'yyyy-MM-dd');widget.setDate(value if value.isValid() else default)
        layout.addWidget(line(start,QLabel('~'),end));unknown=QCheckBox('날짜 미상만 보기');unknown.setChecked(bool(self.date_filters.get('date_unknown')));layout.addWidget(unknown)
        months=QListWidget();layout.addWidget(months);status=QLabel('월별 항목을 누르면 해당 월 범위를 선택합니다.');status.setWordWrap(True);layout.addWidget(status)
        jobs=[];generation=[0]
        def refresh():
            generation[0]+=1;version=generation[0]
            for job in jobs:
                if job.isRunning():job.requestInterruption()
            months.clear();status.setText('타임라인 집계 중…')
            from .discovery import timeline
            def ready(value):
                if version!=generation[0] or not dialog.isVisible():return
                counts,missing=value
                for month,count in counts:
                    item=QListWidgetItem(f'{month} · {count}개');item.setData(Qt.ItemDataRole.UserRole,month);months.addItem(item)
                status.setText(f'날짜 미상 {missing}개 · 생성일은 명시된 메타데이터만 사용합니다.')
            selected_kind=kind.currentData();job=self.run_discovery('날짜 타임라인',lambda j:timeline(self.library.database,selected_kind,j.isInterruptionRequested),ready);jobs.append(job)
            job.finished.connect(lambda:jobs.remove(job))
        def choose(item):
            year,month=map(int,item.data(Qt.ItemDataRole.UserRole).split('-'));start.setDate(QDate(year,month,1));end.setDate(QDate(year,month,calendar.monthrange(year,month)[1]));enabled.setChecked(True);unknown.setChecked(False)
        months.itemClicked.connect(choose);kind.currentIndexChanged.connect(refresh)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        def apply():
            if enabled.isChecked() and not unknown.isChecked() and start.date()>end.date():status.setText('시작일은 종료일보다 늦을 수 없습니다.');return
            self.date_filters={'date_kind':kind.currentData()}
            if unknown.isChecked():self.date_filters['date_unknown']=True
            elif enabled.isChecked():self.date_filters.update(date_from=start.date().toString('yyyy-MM-dd'),date_to=end.date().toString('yyyy-MM-dd'))
            else:self.date_filters={}
            self.days_filter.setCurrentIndex(0);self.apply_browser_filters();dialog.accept()
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply)
        QTimer.singleShot(0,refresh);dialog.exec();generation[0]+=1
        for job in jobs:job.requestInterruption()

    def visible_paths(self):return [self.library.proxy.index(n,0).data(Qt.ItemDataRole.UserRole) for n in range(self.library.proxy.rowCount())]

    def show_discovery_paths(self,paths):
        self.library.transient_paths=set(paths)&set(self.library_items);self.library.proxy.beginFilterChange();self.library.proxy.endFilterChange();self.apply_browser_filters()
        self.workspace_mode.setCurrentIndex(0)

    def find_similar(self):
        if self.library.search_pending or self.index_job:self.statusBar().showMessage('이미지 색인·검색이 끝난 뒤 다시 실행하세요.');return
        paths=self.visible_paths()
        if len(paths)<2:self.statusBar().showMessage('비교할 이미지가 2개 이상 필요합니다.');return
        threshold,ok=QInputDialog.getInt(self,'유사 이미지 묶기',f'현재 결과 {len(paths)}개 비교 · pHash 허용 거리 (작을수록 엄격)',8,0,16)
        if not ok:return
        from .discovery import similar_groups
        self.run_discovery('유사 이미지 후보 묶기',lambda j:similar_groups(self.library.database,paths,threshold,j.isInterruptionRequested,j.progress.emit),self.similar_results)

    def similar_results(self,result):
        dialog=QDialog(self);dialog.setWindowTitle('시각적으로 비슷한 후보');dialog.resize(720,530);layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"{len(result['groups'])}개 그룹 · 읽기 실패 {len(result['failed'])}개"+(' · 취소된 부분 결과' if result['cancelled'] else '')+'\n모양·평균색·비율 기준 후보입니다. 동일 파일 판정이 아니며 자동 삭제하지 않습니다.'))
        tree=QTreeWidget();tree.setHeaderLabel('그룹 선택 후 갤러리에서 확인');layout.addWidget(tree)
        for n,paths in enumerate(result['groups'][:500]):
            parent=QTreeWidgetItem([f'그룹 {n+1} · {len(paths)}개']);parent.setData(0,Qt.ItemDataRole.UserRole,paths);tree.addTopLevelItem(parent)
            for path in paths[:200]:child=QTreeWidgetItem([Path(path).name]);child.setToolTip(0,path);child.setData(0,Qt.ItemDataRole.UserRole,[path]);parent.addChild(child)
        def show():
            item=tree.currentItem()
            if item:self.show_discovery_paths(item.data(0,Qt.ItemDataRole.UserRole));dialog.accept()
        layout.addWidget(action('선택 후보를 갤러리에서 보기',show));layout.addWidget(QLabel('최대 500개 그룹/그룹당 200개 이름 표시 · 그룹 선택 시 전체 소속 표시 · 모두 해제로 원래 목록 복귀'))
        dialog.exec()

    def semantic_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle('로컬 프롬프트 의미 검색');dialog.resize(660,420);layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('이미지 픽셀이 아닌 선택한 텍스트 출처의 의미를 검색합니다.\n한국어·영어 등 다국어 · 첫 128토큰 사용 · 텍스트는 PC 밖으로 전송하지 않습니다.'))
        query=QLineEdit();query.setPlaceholderText('예: 비 오는 밤의 도시 거리');layout.addWidget(query)
        source=QComboBox();source.addItem('원본에 포함된 긍정 프롬프트','positive');source.addItem('저장된 작업 프롬프트','work');source.addItem('AI 추정 태그','tags');layout.addWidget(source)
        folder=QLineEdit((self.store.state('semantic_settings') or {}).get('model',''));layout.addWidget(folder)
        status=QLabel('공식 multilingual MiniLM ONNX 모델 · 약 128 MB · 설치 후 오프라인 검색');status.setWordWrap(True);layout.addWidget(status)
        def choose():
            path=QFileDialog.getExistingDirectory(dialog,'의미 검색 모델 폴더')
            if path:folder.setText(path)
        def install():
            from .semantic import install as install_model
            def ready(path):
                self.store.state('semantic_settings',{'model':path})
                if dialog.isVisible():folder.setText(path);status.setText('모델 설치 완료')
            self.run_discovery('의미 검색 모델 다운로드',lambda j:install_model(self.store.root/'models',j.isInterruptionRequested,j.progress.emit),ready)
        layout.addWidget(line(action('기존 모델 선택',choose),action('공식 모델 다운로드 / 이어받기',install),action('작업 목록 / 취소',lambda:JobCenter(self).exec())))
        def run():
            if self.library.search_pending or self.index_job:status.setText('이미지 색인·검색이 끝난 뒤 다시 실행하세요.');return
            if not query.text().strip() or not (Path(folder.text())/'install_manifest.json').is_file():status.setText('검색 문장과 설치된 모델 폴더를 지정하세요.');return
            paths=self.visible_paths();self.save_draft();self.store.state('semantic_settings',{'model':folder.text()});text=query.text().strip();model=folder.text();kind=source.currentData()
            from .semantic import search
            self.run_discovery('프롬프트 의미 검색',lambda j:search(self.library.database,paths,text,model,kind,cancelled=j.isInterruptionRequested,progress=j.progress.emit),lambda result:self.semantic_results(result,text));dialog.accept()
        layout.addWidget(action('현재 갤러리 결과 안에서 검색',run));dialog.exec()

    def semantic_results(self,result,query):
        dialog=QDialog(self);dialog.setWindowTitle('의미 검색 결과');dialog.resize(700,550);layout=QVBoxLayout(dialog)
        label=QLabel(f"검색: {query}\n텍스트 없는 이미지 {result['skipped']}개 제외 · 코사인 유사도 순 상위 100개"+(' · 취소된 부분 결과' if result['cancelled'] else ''));label.setWordWrap(True);layout.addWidget(label)
        items=QListWidget();layout.addWidget(items)
        for score,path in result['matches']:
            item=QListWidgetItem(f'{score:.3f} · {Path(path).name}');item.setData(Qt.ItemDataRole.UserRole,path);item.setToolTip(path);items.addItem(item)
        def open_item(item):
            dialog.accept();self.safe(lambda:self.load(item.data(Qt.ItemDataRole.UserRole)));self.workspace_mode.setCurrentIndex(1)
        items.itemDoubleClicked.connect(open_item)
        def gallery():self.show_discovery_paths([path for score,path in result['matches']]);dialog.accept()
        layout.addWidget(action('결과를 갤러리에서 보기',gallery));layout.addWidget(QLabel('점수는 정답 확률이 아닙니다. 갤러리에서는 현재 정렬을 유지합니다.'));dialog.exec()
