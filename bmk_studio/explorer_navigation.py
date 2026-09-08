"""Stable thumbnail cards and familiar, read-only Explorer navigation."""
from pathlib import Path
import os
from PySide6.QtCore import Qt,QSize,QDir,QModelIndex,QStandardPaths,QEvent
from PySide6.QtGui import QIcon,QKeySequence,QShortcut
from PySide6.QtWidgets import (QListView,QStyledItemDelegate,QStyleOptionViewItem,QStyle,QWidget,QVBoxLayout,QLabel,QTreeView,QFileSystemModel,QAbstractItemView,QListWidget,QListWidgetItem)

class CardDelegate(QStyledItemDelegate):
    def sizeHint(self,option,index):return self.parent().gridSize()
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index);text=opt.text;icon=QIcon(opt.icon);opt.text='';opt.icon=QIcon()
        view=self.parent();view.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,view)
        rect=option.rect;side=view.iconSize().width();area=rect.adjusted(12,6,-12,-34)
        icon.paint(painter,area,Qt.AlignmentFlag.AlignCenter)
        painter.save();painter.setFont(option.font)
        role=option.palette.ColorRole.Text
        painter.setPen(option.palette.color(role));label=rect.adjusted(6,rect.height()-28,-6,-4)
        painter.drawText(label,Qt.AlignmentFlag.AlignCenter,option.fontMetrics.elidedText(text,Qt.TextElideMode.ElideMiddle,label.width()));painter.restore()

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

class TreeDelegate(QStyledItemDelegate):
    def initStyleOption(self,option,index):
        super().initStyleOption(option,index)
        if option.icon.isNull():option.icon=self.parent().style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

class NavigationPane(QWidget):
    def __init__(self,panel):
        super().__init__();self.panel=panel;self.setMinimumWidth(150);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,5,0)
        layout.addWidget(QLabel('빠른 이동 / 즐겨찾기'));self.quick=QListWidget();self.quick.setMaximumHeight(185);layout.addWidget(self.quick)
        self.quick.itemClicked.connect(lambda item:panel.navigate(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(QLabel('내 PC · 폴더'));self.tree=QTreeView();layout.addWidget(self.tree,1)
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
