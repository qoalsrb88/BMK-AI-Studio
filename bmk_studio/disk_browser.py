"""Read-only disk browsing, isolated from library membership and edit sessions."""
import os,io,hashlib,time
from pathlib import Path
from collections import OrderedDict
from PySide6.QtCore import Qt,QAbstractListModel,QModelIndex,QSize,QSortFilterProxyModel,QTimer
from PySide6.QtGui import QPixmap,QIcon,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QLineEdit,QComboBox,QLabel,QListView,QAbstractItemView,QSplitter,QPlainTextEdit,QFileDialog,QSlider,QTabWidget,QStyle)
from .core import EXTENSIONS,load_image,inspect_image,json_text,file_stamp
from .workspace import line,action
from .appearance import CANVAS,caption
from .explorer_navigation import ExplorerView,NavigationPane


def scan_folder(folder,cancelled=lambda:False):
    rows=[];skipped=0
    with os.scandir(folder) as entries:
        for entry in entries:
            if cancelled():return None
            try:
                directory=entry.is_dir()
                if not directory and Path(entry.name).suffix.lower() not in EXTENSIONS:continue
                stat=entry.stat();rows.append((entry.path,entry.name,directory,stat.st_size,stat.st_mtime_ns))
            except OSError:skipped+=1
    return rows,skipped


def thumbnail(path,stamp,cache):
    key=hashlib.sha256((path+str(stamp)).encode()).hexdigest();target=cache/(key+'.png')
    if target.exists():return target.read_bytes()
    image=load_image(path);image.thumbnail((320,320));buf=io.BytesIO();image.save(buf,format='PNG')
    if file_stamp(path)!=stamp:return None
    blob=buf.getvalue();cache.mkdir(parents=True,exist_ok=True);target.write_bytes(blob);return blob


class DiskModel(QAbstractListModel):
    def __init__(self,panel):super().__init__(panel);self.panel=panel;self.rows=[];self.positions={}
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        row=self.rows[index.row()]
        if role==Qt.ItemDataRole.SizeHintRole:return self.panel.view.gridSize()
        if role==Qt.ItemDataRole.DisplayRole:return row[1]
        if role==Qt.ItemDataRole.ToolTipRole:return row[0]
        if role==Qt.ItemDataRole.UserRole:return row
        if role==Qt.ItemDataRole.DecorationRole:return self.panel.folder_icon if row[2] else self.panel.icon(row)
    def replace(self,rows):self.beginResetModel();self.rows=rows;self.positions={row[0]:i for i,row in enumerate(rows)};self.endResetModel()


class DiskProxy(QSortFilterProxyModel):
    def __init__(self,panel):super().__init__(panel);self.panel=panel
    def filterAcceptsRow(self,n,parent):return all(w in self.sourceModel().rows[n][1].casefold() for w in self.panel.search.text().casefold().split())
    def lessThan(self,a,b):
        x=self.sourceModel().rows[a.row()];y=self.sourceModel().rows[b.row()]
        if x[2]!=y[2]:return x[2] # Folders always first, including descending file order.
        kind=self.panel.sort.currentIndex();key=1 if kind<2 else 4 if kind<4 else 3
        vx=x[key].casefold() if key==1 else x[key];vy=y[key].casefold() if key==1 else y[key]
        if vx==vy:return x[1].casefold()<y[1].casefold()
        return vx>vy if kind%2 else vx<vy


class DiskBrowser(QWidget):
    def __init__(self,owner,viewer_class):
        super().__init__();self.owner=owner;self.folder='';self.history=[];self.history_at=-1;self.generation=0;self.preview_generation=0;self.active=False
        self.scan_job=None;self.thumb_job=None;self.preview_job=None;self.pending=OrderedDict();self.icons=OrderedDict();self.preview_path=None
        self.folder_icon=self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.cache=owner.store.root/'folder-thumbnails';self.state=owner.store.state('disk_browser') or {}
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.address=QLineEdit();self.address.setPlaceholderText('폴더 주소 입력 후 Enter · 예: H:\\Images');self.address.setAccessibleName('폴더 탐색 주소')
        self.back=action('←',lambda:self.travel(-1));self.back.setToolTip('뒤로');self.forward=action('→',lambda:self.travel(1));self.forward.setToolTip('앞으로')
        layout.addWidget(line(self.back,self.forward,action('↑ 상위',lambda:self.navigate(str(Path(self.folder).parent)) if self.folder else None),self.address,action('이동',lambda:self.navigate(self.address.text())),action('폴더 선택',self.choose),action('새로고침',lambda:self.navigate(self.folder,refresh=True))))
        self.favorites=QComboBox();self.favorites.setMinimumContentsLength(12);self.favorites.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon);self.favorites.setMaximumWidth(240);self.refresh_favorites();self.favorites.activated.connect(lambda i:self.navigate(self.favorites.itemData(i)) if i else None)
        self.search=QLineEdit();self.search.setPlaceholderText('현재 폴더의 이름 검색 · 하위 폴더 제외');self.sort=QComboBox();self.sort.addItems(['이름 ↑','이름 ↓','수정일 ↑','수정일 ↓','크기 ↑','크기 ↓'])
        self.add=action('선택 이미지를 라이브러리에 추가',self.add_selected);self.add.setEnabled(False)
        layout.addWidget(line(self.favorites,action('☆ 경로 저장 / 해제',self.toggle_favorite),self.search,self.sort,self.add))
        self.split=QSplitter();layout.addWidget(self.split,1)
        self.view=ExplorerView(self);self.view.setViewMode(QListView.ViewMode.IconMode);self.view.setMovement(QListView.Movement.Static);self.view.setResizeMode(QListView.ResizeMode.Adjust);self.view.setUniformItemSizes(True);self.view.setLayoutMode(QListView.LayoutMode.Batched);self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.model=DiskModel(self);self.proxy=DiskProxy(self);self.proxy.setSourceModel(self.model);self.view.setModel(self.proxy);self.navigation=NavigationPane(self);self.split.addWidget(self.navigation);self.split.addWidget(self.view)
        side=QWidget();right=QVBoxLayout(side);self.label=caption('이미지를 선택하면 원본을 미리 봅니다.');self.label.setWordWrap(True);right.addWidget(self.label)
        self.viewer=viewer_class();self.viewer.display(None);right.addWidget(self.viewer,3);right.addWidget(line(action('화면 맞춤',self.viewer.fit),action('100%',self.viewer.actual_size)))
        self.info_tabs=QTabWidget();right.addWidget(self.info_tabs,2)
        self.positive=QPlainTextEdit();self.negative=QPlainTextEdit();self.metadata=QPlainTextEdit()
        for title,editor in [('프롬프트',self.positive),('네거티브',self.negative),('전체 정보',self.metadata)]:
            editor.setReadOnly(True);editor.setPlaceholderText('원본에 기록된 '+title+'가 없습니다.');page=QWidget();form=QVBoxLayout(page);form.addWidget(owner.prompt_header(title,editor));form.addWidget(editor);self.info_tabs.addTab(page,title)
        self.split.addWidget(side);sizes=self.state.get('split',[220,660,400])
        if not isinstance(sizes,list) or len(sizes)!=3:sizes=[220,660,400]
        self.split.setSizes(sizes)
        self.size=QSlider(Qt.Orientation.Horizontal);self.size.setRange(64,320);self.size.setValue(self.state.get('size',160));self.size.setAccessibleName('폴더 썸네일 크기')
        self.status=caption('주소를 입력하거나 폴더를 선택하세요. 원본과 라이브러리는 자동 변경되지 않습니다.');self.status.setWordWrap(True);layout.addWidget(line(QLabel('썸네일'),self.size));layout.addWidget(self.status)
        self.address.returnPressed.connect(lambda:self.navigate(self.address.text()));self.search.textChanged.connect(self.filter_changed);self.sort.currentIndexChanged.connect(self.filter_changed);self.size.valueChanged.connect(self.resize_icons);self.resize_icons()
        self.view.doubleClicked.connect(self.activate);self.view.selectionModel().currentChanged.connect(self.selection_changed);self.view.selectionModel().selectionChanged.connect(self.selection_count)
        self.timer=QTimer(self);self.timer.setInterval(70);self.timer.timeout.connect(self.start_thumbnails)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.setInterval(120);self.preview_timer.timeout.connect(self.start_preview)
        self.update_navigation()
    def set_active(self,on):
        self.active=on
        if on:
            self.timer.start();self.viewer.set_interpolation(self.owner.viewer.interpolation);self.viewer.overscroll=self.owner.viewer.overscroll;self.viewer.setBackgroundBrush(QColor(CANVAS))
            if not self.folder and self.state.get('folder'):self.navigate(self.state['folder'])
            elif self.folder and not self.model.rows:self.navigate(self.folder,refresh=True)
            elif self.preview_path and self.viewer.pixmap_item is None:self.preview_timer.start()
        else:
            self.timer.stop();self.preview_timer.stop();self.pending.clear();self.generation+=1;self.preview_generation+=1
            for job in (self.scan_job,self.thumb_job,self.preview_job):
                if job:job.requestInterruption()
    def save(self):
        self.state.update(folder=self.folder or self.state.get('folder',''),size=self.size.value(),split=self.split.sizes());self.owner.store.state('disk_browser',self.state)
    def choose(self):
        folder=QFileDialog.getExistingDirectory(self,'폴더 탐색',self.folder)
        if folder:self.navigate(folder)
    def navigate(self,value,refresh=False,history_at=None):
        if not value or not self.active:return
        folder=os.path.abspath(os.path.expandvars(os.path.expanduser(value.strip().strip('"'))))
        self.generation+=1;token=self.generation;self.preview_generation+=1;self.pending.clear();self.preview_timer.stop()
        if self.scan_job:self.scan_job.requestInterruption()
        self.status.setText('폴더 읽는 중… '+folder)
        def read(job):
            try:return scan_folder(folder,job.isInterruptionRequested),None
            except OSError as exc:return None,str(exc)
        def ready(result):
            if token!=self.generation or not self.active:return
            value,error=result
            if error:self.status.setText('폴더를 열 수 없습니다: '+error);self.address.setText(self.folder);return
            if value is None:self.status.setText('폴더 읽기가 취소되었습니다. 새로고침으로 다시 읽을 수 있습니다.');return
            rows,skipped=value;self.folder=folder;self.address.setText(folder);self.icons.clear();self.model.replace(rows);self.search.clear();self.filter_changed();self.viewer.display(None);self.metadata.clear();self.positive.clear();self.negative.clear();self.preview_path=None;self.label.setText('이미지를 선택하면 원본을 미리 봅니다.')
            if history_at is not None:self.history_at=history_at
            elif not refresh and (self.history_at<0 or self.history[self.history_at]!=folder):self.history=self.history[:self.history_at+1]+[folder];self.history_at=len(self.history)-1
            self.update_navigation();self.navigation.sync();self.save();self.status.setText(f'{len(rows)}개 항목 · 접근 불가 {skipped}개 · 현재 폴더만 표시');self.selection_count()
        job=self.owner.run_discovery('폴더 탐색',read,ready);self.scan_job=job
        job.finished.connect(lambda:setattr(self,'scan_job',None) if self.scan_job is job else None)
    def travel(self,step):
        n=self.history_at+step
        if 0<=n<len(self.history):self.navigate(self.history[n],history_at=n)
    def update_navigation(self):self.back.setEnabled(self.history_at>0);self.forward.setEnabled(self.history_at+1<len(self.history))
    def refresh_favorites(self):
        if hasattr(self,'navigation'):self.navigation.refresh_quick()
        self.favorites.clear();self.favorites.addItem('즐겨찾는 경로',None)
        for path in self.state.get('favorites',[]):self.favorites.addItem(path,path)
    def toggle_favorite(self):
        if not self.folder:return
        paths=list(self.state.get('favorites',[]))
        if self.folder in paths:paths.remove(self.folder)
        else:paths.append(self.folder)
        self.state['favorites']=paths;self.refresh_favorites();self.save()
    def filter_changed(self,*args):self.proxy.invalidate();self.proxy.sort(0);self.selection_count()
    def resize_icons(self,*args):
        anchor=self.view.currentIndex()
        if not anchor.isValid():anchor=self.view.indexAt(self.view.viewport().rect().topLeft())
        n=self.size.value();self.view.setIconSize(QSize(n,n));self.view.setGridSize(QSize(n+36,n+48));self.view.doItemsLayout()
        if anchor.isValid():self.view.scrollTo(anchor)
    def selected_paths(self):return [self.proxy.data(i,Qt.ItemDataRole.UserRole)[0] for i in self.view.selectedIndexes() if not self.proxy.data(i,Qt.ItemDataRole.UserRole)[2]]
    def selection_count(self,*args):self.add.setEnabled(bool(self.selected_paths()))
    def add_selected(self):
        paths=self.selected_paths()
        if paths:self.owner.add_paths(paths,open_first=False);self.status.setText(f'{len(paths)}개 이미지를 라이브러리에 추가했습니다. 원본 위치는 유지됩니다.')
    def activate(self,index):
        row=self.proxy.data(index,Qt.ItemDataRole.UserRole)
        if row and row[2]:self.navigate(row[0])
    def selection_changed(self,index,*args):
        self.preview_generation+=1;self.preview_timer.stop();self.preview_path=None;self.viewer.display(None);self.metadata.clear();self.positive.clear();self.negative.clear()
        if not index.isValid():return
        row=self.proxy.data(index,Qt.ItemDataRole.UserRole);self.label.setText(row[0])
        if not row[2]:self.preview_path=row[0];self.preview_timer.start()
    def start_preview(self):
        if not self.active or not self.preview_path or self.owner.closing_requested:return
        if self.preview_job:self.preview_timer.start();return
        path=self.preview_path;token=self.preview_generation
        def read(job):
            try:
                stamp=file_stamp(path);info=inspect_image(path);image=load_image(path)
                if file_stamp(path)!=stamp:raise ValueError('읽는 중 파일이 변경되었습니다.')
                return image,info,None
            except Exception as exc:return None,None,str(exc)
        def ready(result):
            if not self.active or token!=self.preview_generation:return
            image,info,error=result
            if error:self.label.setText(path+'\n읽기 실패: '+error);return
            self.viewer.display(image);self.metadata.setPlainText(json_text(info));self.positive.setPlainText(info.get('positive',''));self.negative.setPlainText(info.get('negative',''));self.label.setText(f'{Path(path).name} · {image.width} × {image.height}\n{path}')
        job=self.owner.run_discovery('폴더 이미지 미리보기',read,ready);self.preview_job=job
        job.finished.connect(lambda:setattr(self,'preview_job',None) if self.preview_job is job else None)
    def icon(self,row):
        path=row[0]
        if path in self.icons:self.icons.move_to_end(path);return self.icons[path]
        if self.active and len(self.pending)<128:self.pending[path]=None
        return QIcon()
    def start_thumbnails(self):
        if not self.active or self.owner.closing_requested or self.thumb_job or not self.pending:return
        paths=[self.pending.popitem(last=False)[0] for _ in range(min(8,len(self.pending)))];token=self.generation;cache=self.cache
        def read(job):
            results=[]
            for path in paths:
                if job.isInterruptionRequested():break
                try:blob=thumbnail(path,file_stamp(path),cache)
                except Exception:blob=None
                results.append((path,blob))
            # Derived cache only, bounded to 256 MiB. Source files are never removed.
            if cache.exists():
                files=sorted(cache.glob('*.png'),key=lambda p:p.stat().st_mtime);total=sum(p.stat().st_size for p in files)
                for p in files:
                    if total<=256*1024**2:break
                    total-=p.stat().st_size;p.unlink()
            return results
        def ready(results):
            if token!=self.generation or not self.active:return
            for path,blob in results:
                pix=QPixmap()
                if blob:pix.loadFromData(blob)
                self.icons[path]=QIcon(pix);self.pending.pop(path,None)
                position=self.model.positions.get(path)
                if position is not None:
                    index=self.model.index(position,0);self.model.dataChanged.emit(index,index,[Qt.ItemDataRole.DecorationRole])
            while len(self.icons)>128:self.icons.popitem(last=False)
            self.view.viewport().update()
        job=self.owner.run_discovery('폴더 썸네일',read,ready);self.thumb_job=job
        job.finished.connect(lambda:setattr(self,'thumb_job',None) if self.thumb_job is job else None)
