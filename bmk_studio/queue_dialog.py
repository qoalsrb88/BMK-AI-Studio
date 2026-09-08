from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QPushButton,QAbstractItemView

class QueueDialog(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.setWindowTitle('태깅 대기열');self.resize(700,500);layout=QVBoxLayout(self)
        self.status=QLabel();layout.addWidget(self.status);self.items=QListWidget();self.items.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);layout.addWidget(self.items)
        row=QHBoxLayout()
        for title,fn in [('선택 이미지 추가',studio.enqueue_selected),('위로',lambda:self.move(-1)),('아래로',lambda:self.move(1)),('대기 항목 제거',self.remove),('실행 / 재개',studio.run_queue),('일시 정지',studio.pause_queue)]:
            button=QPushButton(title);button.clicked.connect(fn);row.addWidget(button)
        layout.addLayout(row);layout.addWidget(QLabel('현재 추론 배치는 끝까지 마무리합니다. 대기 항목은 실행 중에도 추가·정렬·제거할 수 있습니다.'))
        self.refresh()
    def refresh(self):
        selected={item.data(Qt.ItemDataRole.UserRole) for item in self.items.selectedItems()};self.items.clear()
        for path in self.studio.tag_queue:
            item=QListWidgetItem(Path(path).name+' · '+path);item.setData(Qt.ItemDataRole.UserRole,path);self.items.addItem(item);item.setSelected(path in selected)
        self.status.setText(f'대기 {len(self.studio.tag_queue)}개 · 현재 배치 {len(self.studio.queue_active)}개 · '+('실행 중' if self.studio.queue_running else '정지'))
    def remove(self):
        paths={item.data(Qt.ItemDataRole.UserRole) for item in self.items.selectedItems()}
        self.studio.tag_queue=[path for path in self.studio.tag_queue if path not in paths];self.studio.save_queue()
    def move(self,direction):
        rows=sorted({self.items.row(item) for item in self.items.selectedItems()},reverse=direction>0)
        selected=set(rows);queue=self.studio.tag_queue
        for row in rows:
            target=row+direction
            if 0<=target<len(queue) and target not in selected:
                queue[row],queue[target]=queue[target],queue[row];selected.remove(row);selected.add(target)
        self.studio.save_queue()
