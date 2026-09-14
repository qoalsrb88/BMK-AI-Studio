"""Empty-state hints painted inside item views that have nothing to show."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import QListWidget


def paint_hint(view, text):
    """Draw a centred, word-wrapped hint on the viewport; call after the view's own paintEvent."""
    rect = view.viewport().rect().adjusted(24, 16, -24, -16)
    if rect.height() < 40 or not text: return
    painter = QPainter(view.viewport()); painter.setPen(view.palette().color(QPalette.ColorRole.PlaceholderText))
    font = painter.font(); font.setPointSizeF(font.pointSizeF() + 0.5); painter.setFont(font)
    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text); painter.end()


class HintListWidget(QListWidget):
    """QListWidget that shows `hint` while it has no items."""
    def __init__(self, hint='', parent=None):
        super().__init__(parent); self.hint = hint
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0: paint_hint(self, self.hint)
