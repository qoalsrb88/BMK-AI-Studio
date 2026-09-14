"""Collapsible panel section: a header toggle above a vertical body."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from .appearance import decorate


class Section(QWidget):
    toggled = Signal(str, bool)

    def __init__(self, key, title, expanded=True):
        super().__init__(); self.key = key; self.default = expanded
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(6)
        self.header = QPushButton(title); self.header.setCheckable(True); self.header.setChecked(expanded)
        self.header.setProperty('role', 'section'); self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setAccessibleName(title + ' 섹션 접기 / 펼치기')
        self.body = QWidget(); self.body_layout = QVBoxLayout(self.body); self.body_layout.setContentsMargins(0, 0, 0, 0); self.body_layout.setSpacing(6)
        layout.addWidget(self.header); layout.addWidget(self.body)
        self.header.toggled.connect(self._apply); self._apply(expanded)

    def _apply(self, expanded):
        self.body.setVisible(expanded); decorate(self.header, 'chevron-down' if expanded else 'chevron-right'); self.toggled.emit(self.key, expanded)

    def set_expanded(self, expanded):
        self.header.setChecked(bool(expanded))

    def add(self, *widgets):
        for widget in widgets: self.body_layout.addWidget(widget)
        return self
