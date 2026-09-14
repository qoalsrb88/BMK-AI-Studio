"""Wrapping rows of widgets and removable filter chips."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QSizePolicy


class Flow(QWidget):
    """Left-to-right row that wraps onto new lines.

    Children are positioned by hand and the widget fixes its own height for the current width, so it never
    reports heightForWidth: inside a resizable QScrollArea that would make the page as tall as every editor's
    preferred height instead of the viewport.
    """
    def __init__(self, spacing=6):
        super().__init__(); self.gap = spacing; self.widgets = []
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def add(self, widget):
        widget.setParent(self); self.widgets.append(widget); widget.show(); self.arrange(); return widget

    def clear(self):
        # Detach immediately: a deferred delete would leave the old widget painting until the event loop turns.
        for widget in self.widgets: widget.hide(); widget.setParent(None); widget.deleteLater()
        self.widgets = []; self.arrange()

    def sizeHint(self):
        hints = [w.sizeHint() for w in self.widgets if not w.isHidden()]
        if not hints: return QSize(0, 0)
        return QSize(sum(h.width() for h in hints) + self.gap * (len(hints) - 1), max(h.height() for h in hints))

    def minimumSizeHint(self):
        hints = [w.sizeHint() for w in self.widgets if not w.isHidden()]
        if not hints: return QSize(0, 0)
        return QSize(max(h.width() for h in hints), max(h.height() for h in hints))

    def resizeEvent(self, event):
        super().resizeEvent(event); self.arrange()

    def arrange(self):
        width = max(self.width(), 1); x = y = row = 0
        for widget in self.widgets:
            if widget.isHidden(): continue
            hint = widget.sizeHint()
            if x and x + hint.width() > width: x = 0; y += row + self.gap; row = 0
            widget.setGeometry(x, y, hint.width(), hint.height()); x += hint.width() + self.gap; row = max(row, hint.height())
        height = y + row
        if height != self.height(): self.setFixedHeight(height); self.updateGeometry()


def flow(*widgets):
    """Widgets in a wrapping row, so narrow panels stack them instead of growing wider."""
    host = Flow()
    for widget in widgets: host.add(widget)
    return host


class ChipRow(Flow):
    """Shows one removable chip per active condition, or `empty_text` when there is none."""
    def __init__(self, empty_text=''):
        super().__init__(); self.empty_text = empty_text; self.chips = []; self.set_chips([])

    def set_chips(self, chips):
        """chips: list of (label, callback) where callback removes that condition; callback may be None."""
        self.clear(); self.chips = list(chips)
        if not self.chips:
            if self.empty_text:
                label = QLabel(self.empty_text); label.setProperty('role', 'muted'); self.add(label)
            return
        for text, callback in self.chips:
            chip = QPushButton(text + ('  ×' if callback else '')); chip.setProperty('chip', True); chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip('클릭하면 이 조건을 해제합니다' if callback else text)
            if callback: chip.clicked.connect(callback)
            else: chip.setEnabled(False)
            self.add(chip)
