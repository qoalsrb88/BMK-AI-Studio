import json
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QListWidget

MIME='application/x-bmk-library-references'

class CollectionDropList(QListWidget):
    referencesDropped=Signal(str,object)
    def __init__(self,parent=None):
        super().__init__(parent);self.setAcceptDrops(True);self.setMaximumHeight(150);self.setToolTip('선택한 이미지 카드를 컬렉션 이름 위로 드래그 · 원본 파일은 이동하지 않습니다')
    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(MIME):event.acceptProposedAction()
        else:event.ignore()
    def dragMoveEvent(self,event):
        if event.mimeData().hasFormat(MIME) and self.itemAt(event.position().toPoint()):event.acceptProposedAction()
        else:event.ignore()
    def dropEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if not item or not event.mimeData().hasFormat(MIME):event.ignore();return
        try:paths=json.loads(bytes(event.mimeData().data(MIME)))
        except (ValueError,TypeError):event.ignore();return
        if not isinstance(paths,list) or not all(isinstance(path,str) for path in paths):event.ignore();return
        self.referencesDropped.emit(item.text(),paths);event.setDropAction(Qt.DropAction.CopyAction);event.accept()
