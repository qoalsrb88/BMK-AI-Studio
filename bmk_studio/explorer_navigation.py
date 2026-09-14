"""Stable thumbnail cards and familiar, read-only Explorer navigation."""
from pathlib import Path
import os
from PySide6.QtCore import Qt,QSize,QDir,QModelIndex,QStandardPaths,QEvent
from PySide6.QtGui import QIcon,QKeySequence,QShortcut
from PySide6.QtWidgets import (QListView,QStyledItemDelegate,QStyleOptionViewItem,QStyle,QWidget,QVBoxLayout,QLabel,QTreeView,QFileSystemModel,QAbstractItemView,QListWidget,QListWidgetItem)
from .appearance import caption,icon as line_icon,pixmap,tokens
from .hints import paint_hint
from .cards import paint_card

class CardDelegate(QStyledItemDelegate):
    """Explorer card: folders show a light glyph tile, images their thumbnail; names wrap to two lines."""
    def sizeHint(self,option,index):return self.parent().gridSize()
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index);text=opt.text;icon=QIcon(opt.icon);row=index.data(Qt.ItemDataRole.UserRole)
        def content(p,area):
            if row and row[2]:
                side=int(min(area.width(),area.height())*.62);glyph=pixmap('folder',side,fill=tokens()['surface2'])
                p.drawPixmap(area.center().x()-side//2,area.center().y()-side//2,glyph)
            else:icon.paint(p,area,Qt.AlignmentFlag.AlignCenter)
        paint_card(painter,opt,option.rect,content,text)

class ExplorerView(QListView):
    def __init__(self,panel):super().__init__();self.panel=panel;self.wheel_remainder=0;self.setItemDelegate(CardDelegate(self))
    def wheelEvent(self,event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.wheel_remainder+=event.angleDelta().y() or event.pixelDelta().y()
            steps=int(self.wheel_remainder/120)
            if steps:self.wheel_remainder-=steps*120;self.panel.size.setValue(self.panel.size.value()+steps*16)
            event.accept();return
        super().wheelEvent(event)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.panel.activate(self.currentIndex());event.accept();return
        if event.key()==Qt.Key.Key_Backspace:self.panel.travel(-1);event.accept();return
        super().keyPressEvent(event)
    def paintEvent(self,event):
        super().paintEvent(event)
        if self.model() is None or self.model().rowCount():return
        panel=self.panel
        if not panel.folder:text='주소를 입력하거나 왼쪽 트리에서 폴더를 선택하세요.'
        elif panel.scan_job:text='폴더를 읽는 중…'
        elif panel.model.rows:text='이름 검색에 맞는 항목이 없습니다.'
        else:text='이 폴더에는 표시할 이미지나 하위 폴더가 없습니다.'
        paint_hint(self,text)

class TreeDelegate(QStyledItemDelegate):
    """Drives keep their system icons; folders below them use the line folder glyph in the current text colour."""
    def __init__(self,parent):super().__init__(parent);self.cached=None
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        if index.parent().isValid() or option.icon.isNull():
            color=option.palette.color(option.palette.ColorRole.Text).name()
            if not self.cached or self.cached[0]!=color:self.cached=(color,line_icon('folder',color))
            option.icon=self.cached[1]

class NavigationPane(QWidget):
    def __init__(self,panel):
        super().__init__();self.panel=panel;self.setMinimumWidth(150);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,5,0)
        layout.addWidget(caption('빠른 이동 / 즐겨찾기','section'));self.quick=QListWidget();self.quick.setMaximumHeight(185);layout.addWidget(self.quick)
        self.quick.itemClicked.connect(lambda item:panel.navigate(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(caption('내 PC · 폴더','section'));self.tree=QTreeView();layout.addWidget(self.tree,1)
        self.fs=QFileSystemModel(self);self.fs.setReadOnly(True);self.fs.setOption(QFileSystemModel.Option.DontUseCustomDirectoryIcons,True);self.fs.setFilter(QDir.Filter.AllDirs|QDir.Filter.NoDotAndDotDot|QDir.Filter.Drives);self.fs.setRootPath('')
        self.tree.setModel(self.fs);self.tree.setItemDelegate(TreeDelegate(self.tree));self.tree.setHeaderHidden(True);self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.tree.setDragEnabled(False);self.tree.setAcceptDrops(False);self.tree.setUniformRowHeights(True);self.tree.setIndentation(14);self.tree.setColumnWidth(0,320);self.tree.setExpandsOnDoubleClick(True)
        for column in (1,2,3):self.tree.hideColumn(column)
        self.tree.clicked.connect(lambda index:panel.navigate(self.fs.filePath(index)))
        self.fs.directoryLoaded.connect(lambda path:self.sync() if self.panel.folder and (os.path.normcase(self.panel.folder)==os.path.normcase(path) or os.path.normcase(self.panel.folder).startswith(os.path.normcase(path).rstrip('\\/')+os.sep)) else None);self.refresh_quick()
        self.tree.viewport().installEventFilter(self)
        for sequence,callback in [('Alt+Left',lambda:panel.travel(-1)),('Alt+Right',lambda:panel.travel(1)),('Alt+Up',self.up),('Alt+D',self.address),('Ctrl+L',self.address),('Ctrl+F',self.search),('F5',lambda:panel.navigate(panel.folder,refresh=True))]:
            shortcut=QShortcut(QKeySequence(sequence),panel);shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);shortcut.activated.connect(callback)
        panel.view.viewport().installEventFilter(self)
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.MouseButtonRelease:
            if event.button()==Qt.MouseButton.BackButton:self.panel.travel(-1);return True
            if event.button()==Qt.MouseButton.ForwardButton:self.panel.travel(1);return True
        return super().eventFilter(obj,event)
    def address(self):self.panel.address.setFocus();self.panel.address.selectAll()
    def search(self):self.panel.search.setFocus();self.panel.search.selectAll()
    def up(self):
        if self.panel.folder:self.panel.navigate(str(Path(self.panel.folder).parent))
    def refresh_quick(self):
        self.quick.clear();seen=set();paths=[('홈',str(Path.home()))]
        for label,key in [('바탕 화면',QStandardPaths.StandardLocation.DesktopLocation),('다운로드',QStandardPaths.StandardLocation.DownloadLocation),('사진',QStandardPaths.StandardLocation.PicturesLocation)]:paths.append((label,QStandardPaths.writableLocation(key)))
        paths.extend(('★ '+Path(p).name,p) for p in self.panel.state.get('favorites',[]))
        for label,path in paths:
            if not path or path in seen:continue
            seen.add(path);item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,path);item.setToolTip(path);self.quick.addItem(item)
    def sync(self):
        if not self.panel.active or not self.panel.folder:return
        index=self.fs.index(self.panel.folder)
        if not index.isValid():return
        self.tree.expand(index)
        parent=index.parent()
        while parent.isValid():self.tree.expand(parent);parent=parent.parent()
        if self.tree.currentIndex()!=index:self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index,QAbstractItemView.ScrollHint.PositionAtCenter);self.tree.horizontalScrollBar().setValue(0)
