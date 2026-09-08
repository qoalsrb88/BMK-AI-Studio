"""Virtual item view with bounded, demand-decoded thumbnail cache."""
from collections import OrderedDict
from PySide6.QtCore import Qt,QAbstractListModel,QModelIndex,QSize,QSortFilterProxyModel,Signal,QItemSelectionModel,QTimer
from PySide6.QtGui import QPixmap,QIcon,QDrag
from PySide6.QtWidgets import QListView,QPushButton
from .library_disk import ThumbnailPages,SearchJob

ROLE=Qt.ItemDataRole

class LibraryItem:
    def __init__(self,view,title,path):
        self.view=view;self.title=title;self.path=path;self.search=title.casefold();self.blob=b'';self.position=-1
    def text(self):return self.title
    def data(self,role):return self.path if role==ROLE.UserRole else self.title
    def icon(self):return self.view.records.thumbnail(self)
    def isHidden(self):return not self.view.proxy.mapFromSource(self.view.records.index(self.position)).isValid()
    def setSelected(self,on):
        index=self.view.proxy.mapFromSource(self.view.records.index(self.position))
        if index.isValid():self.view.selectionModel().select(index,QItemSelectionModel.SelectionFlag.Select if on else QItemSelectionModel.SelectionFlag.Deselect)

class LibraryModel(QAbstractListModel):
    def __init__(self,parent):
        super().__init__(parent);self.rows=[];self.icons=OrderedDict();self.decode_count=0
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def data(self,index,role=ROLE.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows):return None
        item=self.rows[index.row()]
        if role==ROLE.DisplayRole:
            rating=self.parent().favorite_ratings.get(item.path)
            return ('★'+(str(rating) if rating else '')+' ' if rating is not None else '')+item.title
        if role in (ROLE.UserRole,ROLE.ToolTipRole):return item.path
        if role==ROLE.DecorationRole:return self.thumbnail(item)
        if role==ROLE.SizeHintRole:
            view=self.parent();size=view.iconSize().height()
            return QSize(size+32,size+46) if view.viewMode()==QListView.ViewMode.IconMode else QSize(150,size+14)
        if role==ROLE.UserRole+1:return item.search
    def thumbnail(self,item):
        if item.path in self.icons:
            self.icons.move_to_end(item.path);return self.icons[item.path]
        view=self.parent();blob=view.large.get(item.path) if view.large and view.iconSize().width()>160 else None
        if not blob:blob=view.pages.get(item.path) if view.pages else item.blob
        if not blob:return QIcon()
        pix=QPixmap();pix.loadFromData(blob);icon=QIcon(pix)
        self.icons[item.path]=icon;self.decode_count+=1
        if len(self.icons)>(64 if view.iconSize().width()>160 else 256):self.icons.popitem(last=False)
        return icon
    def append(self,item):
        index=len(self.rows);self.beginInsertRows(QModelIndex(),index,index)
        item.position=index;self.rows.append(item);self.endInsertRows()
    def remove_paths(self,paths):
        self.beginResetModel();self.rows=[item for item in self.rows if item.path not in paths]
        for i,item in enumerate(self.rows):item.position=i
        for path in paths:self.icons.pop(path,None)
        self.endResetModel()

class SearchProxy(QSortFilterProxyModel):
    def __init__(self,parent):super().__init__(parent);self.words=[];self.accepted=None
    def lessThan(self,left,right):return self.sourceModel().rows[left.row()].title.casefold()<self.sourceModel().rows[right.row()].title.casefold()
    def filterAcceptsRow(self,row,parent):
        if self.parent().transient_paths is not None and self.sourceModel().rows[row].path not in self.parent().transient_paths:return False
        if not self.words:return True
        if self.accepted is not None:return self.sourceModel().rows[row].path in self.accepted
        text=self.sourceModel().rows[row].search
        return all(word in text for word in self.words)

class LibraryView(QListView):
    itemClicked=Signal(object)
    removeRequested=Signal(str)
    searching=Signal(bool)
    def __init__(self,database=None,owner=None):
        super().__init__();self.records=LibraryModel(self);self.proxy=SearchProxy(self)
        self.database=database;self.owner=owner;self.pages=ThumbnailPages(database) if database else None
        self.query='';self.generation=0;self.search_job=None;self.search_jobs=[];self.stopped=False
        self.filters={}
        self.transient_paths=None
        from .large_thumbnails import LargeThumbnails
        self.large=LargeThumbnails(self) if database else None
        self.setDragEnabled(True)
        self.favorite_ratings={}
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(100);self.search_timer.timeout.connect(self.start_search)
        self.proxy.setSourceModel(self.records);self.proxy.setFilterRole(ROLE.UserRole+1);self.setModel(self.proxy)
        self.setUniformItemSizes(True);self.setLayoutMode(QListView.LayoutMode.Batched);self.setBatchSize(200)
        self.clicked.connect(lambda index:self.itemClicked.emit(self.records.rows[self.proxy.mapToSource(index).row()]))
        self.setMouseTracking(True)
        self.remove_button=QPushButton('×',self.viewport());self.remove_button.setFixedSize(26,26)
        self.remove_button.setAccessibleName('이 이미지를 목록에서 제거')
        self.remove_button.setToolTip('목록에서만 제거 · 원본 파일은 유지됩니다')
        self.remove_button.setStyleSheet('QPushButton { padding:0; font-size:22px; background:#303030; color:white; border:1px solid #888; border-radius:4px; } QPushButton:hover { background:#a4262c; }')
        self.remove_button.hide();self.hover_path=None
        self.remove_button.clicked.connect(self.remove_hovered)
        self.verticalScrollBar().valueChanged.connect(self.hide_remove)
        self.horizontalScrollBar().valueChanged.connect(self.hide_remove)
        self.proxy.modelReset.connect(self.hide_remove)
        self.proxy.layoutChanged.connect(self.hide_remove)
    def hide_remove(self,*args):
        self.remove_button.hide();self.hover_path=None
    def startDrag(self,actions):
        import json
        from PySide6.QtCore import QMimeData
        from .collection_drop import MIME
        paths=[item.path for item in self.selectedItems()]
        if not paths:return
        mime=QMimeData();mime.setData(MIME,json.dumps(paths).encode());drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.CopyAction)
    def mouseMoveEvent(self,event):
        super().mouseMoveEvent(event)
        index=self.indexAt(event.position().toPoint())
        if not index.isValid():self.hide_remove();return
        self.hover_path=index.data(ROLE.UserRole)
        rect=self.visualRect(index)
        self.remove_button.move(rect.right()-29,rect.top()+3);self.remove_button.show();self.remove_button.raise_()
    def leaveEvent(self,event):
        self.hide_remove();super().leaveEvent(event)
    def resizeEvent(self,event):
        self.hide_remove();super().resizeEvent(event)
    def keyPressEvent(self,event):
        super().keyPressEvent(event)
        if event.modifiers()==Qt.KeyboardModifier.NoModifier and event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down,Qt.Key.Key_Return):
            index=self.currentIndex()
            if index.isValid():
                item=self.records.rows[self.proxy.mapToSource(index).row()]
                if not self.owner or str(self.owner.path)!=item.path:self.itemClicked.emit(item)
    def remove_hovered(self):
        path=self.hover_path;self.hide_remove()
        if path:self.removeRequested.emit(path)
    def add_path(self,path,title):
        item=LibraryItem(self,title,path);self.records.append(item);return item
    def add_references(self,references):
        self.records.beginResetModel()
        from pathlib import Path
        items=[]
        for path,stamp in references:
            item=LibraryItem(self,Path(path).name,path);item.position=len(self.records.rows);self.records.rows.append(item);items.append(item)
        self.records.endResetModel();return items
    def set_thumbnail_size(self,size):
        size=max(40,min(512,int(size)));self.hide_remove()
        if (self.iconSize().width()>160)!=(size>160):self.records.icons.clear()
        self.setIconSize(QSize(size,size))
        if size>160 and self.large and self.large.paused and not self.stopped:self.large.resume()
        elif size<=160 and self.large:self.large.pause()
        if self.records.rows:self.records.dataChanged.emit(self.records.index(0),self.records.index(len(self.records.rows)-1),[ROLE.SizeHintRole])
        self.doItemsLayout()
    def count(self):return len(self.records.rows)
    def item(self,index):return self.records.rows[index]
    def selectedItems(self):return [self.records.rows[self.proxy.mapToSource(i).row()] for i in self.selectionModel().selectedIndexes()]
    def update_item(self,item,search=None,blob=None):
        roles=[]
        if self.database:
            if blob is not None:self.pages.clear();self.records.icons.pop(item.path,None);roles.append(ROLE.DecorationRole)
            if blob is not None and self.large:self.large.invalidate(item.path)
        else:
            if search is not None:item.search=search.casefold();roles.append(ROLE.UserRole+1)
            if blob is not None:item.blob=blob;self.records.icons.pop(item.path,None);roles.append(ROLE.DecorationRole)
        index=self.records.index(item.position);self.records.dataChanged.emit(index,index,roles)
    def set_query(self,query):
        self.hide_remove()
        self.query=query
        if self.database:
            self.generation+=1;self.search_timer.stop()
            if self.search_job:self.search_job.requestInterruption()
            self.proxy.beginFilterChange();self.proxy.words=query.casefold().split() or ([''] if self.filters else []);self.proxy.accepted=set() if self.proxy.words else None;self.proxy.endFilterChange()
            if self.proxy.words and not self.stopped:self.search_timer.start();self.searching.emit(True)
            else:self.searching.emit(False)
            return
        self.proxy.beginFilterChange();self.proxy.words=query.casefold().split();self.proxy.endFilterChange()
    def refresh_query(self):
        if self.query.strip() or self.filters:self.set_query(self.query)
    @property
    def search_pending(self):
        # A stopped worker may still have queued result/finished signals on the UI thread.
        return self.search_timer.isActive() or bool(self.search_jobs)
    def start_search(self):
        if self.stopped or not (self.query.strip() or self.filters):return
        references=[(item.path,item.title) for item in self.records.rows]
        job=SearchJob(self.database,references,self.query,self.generation,self,filters=self.filters);self.search_job=job;self.search_jobs.append(job)
        if self.owner:self.owner.jobs.append(job)
        def result(payload):
            generation,matches=payload
            if generation!=self.generation:return
            self.proxy.beginFilterChange();self.proxy.accepted=matches;self.proxy.endFilterChange();self.searching.emit(False)
        def failed(error):
            if job.generation==self.generation and self.owner:self.owner.statusBar().showMessage('목록 검색 실패: '+error)
        def finish():
            self.search_jobs.remove(job)
            if self.owner:self.owner.jobs.remove(job)
            if self.search_job is job:self.search_job=None
        job.result.connect(result);job.failed.connect(failed);job.finished.connect(finish);job.start()
    def stop_search(self):
        self.stopped=True;self.generation+=1;self.search_timer.stop();self.searching.emit(False)
        if self.large:self.large.pause()
        for job in self.search_jobs:job.requestInterruption()
    def resume_search(self):
        self.stopped=False;self.set_query(self.query)
        if self.large:self.large.resume()
    def remove_paths(self,paths):self.records.remove_paths(set(paths))
