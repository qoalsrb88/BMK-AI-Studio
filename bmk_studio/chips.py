"""Removable filter chips laid out in a wrapping flow."""
from PySide6.QtCore import Qt, QPoint, QRect, QSize
from PySide6.QtWidgets import QLayout, QWidget, QPushButton, QLabel, QSizePolicy


class FlowLayout(QLayout):
    """Left-to-right layout that wraps items onto new rows (port of the Qt flow-layout example)."""
    def __init__(self, parent=None, spacing=6):
        super().__init__(parent); self.items = []; self.gap = spacing; self.setContentsMargins(0, 0, 0, 0)
    def addItem(self, item): self.items.append(item); self.invalidate()
    def count(self): return len(self.items)
    def itemAt(self, index): return self.items[index] if 0 <= index < len(self.items) else None
    def takeAt(self, index):
        item = self.items.pop(index) if 0 <= index < len(self.items) else None
        self.invalidate(); return item
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self._arrange(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect): super().setGeometry(rect); self._arrange(rect, False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        size = QSize()
        for item in self.items: size = size.expandedTo(item.minimumSize())
        return size
    def _arrange(self, rect, test_only):
        x, y, row_height = rect.x(), rect.y(), 0
        for item in self.items:
            hint = item.sizeHint()
            if x + hint.width() > rect.right() + 1 and row_height > 0:
                x = rect.x(); y += row_height + self.gap; row_height = 0
            if not test_only: item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self.gap; row_height = max(row_height, hint.height())
        return y + row_height - rect.y()


def flow(*widgets):
    """Widgets in a wrapping row, so narrow panels stack them instead of growing wider."""
    host = QWidget(); layout = FlowLayout(host)
    for widget in widgets: layout.addWidget(widget)
    return host


class ChipRow(QWidget):
    """Shows one removable chip per active condition, or `empty_text` when there is none."""
    def __init__(self, empty_text=''):
        super().__init__(); self.flow = FlowLayout(self); self.empty_text = empty_text; self.chips = []
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.set_chips([])

    def set_chips(self, chips):
        """chips: list of (label, callback) where callback removes that condition; callback may be None."""
        while self.flow.count():
            item = self.flow.takeAt(0); widget = item.widget()
            # Detach immediately: a deferred delete can leave the old widget painting until the event loop turns.
            if widget: widget.hide(); widget.setParent(None); widget.deleteLater()
        self.chips = list(chips)
        if not self.chips:
            if self.empty_text:
                label = QLabel(self.empty_text); label.setProperty('role', 'muted'); self.flow.addWidget(label)
            self.flow.activate(); self.updateGeometry(); return
        for text, callback in self.chips:
            chip = QPushButton(text + ('  ×' if callback else '')); chip.setProperty('chip', True); chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip('클릭하면 이 조건을 해제합니다' if callback else text)
            if callback: chip.clicked.connect(callback)
            else: chip.setEnabled(False)
            self.flow.addWidget(chip)
        self.flow.activate(); self.updateGeometry()
