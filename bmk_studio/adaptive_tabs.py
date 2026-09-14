"""Tab widget that drops tab titles and keeps only icons when the panel is too narrow for the full labels."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabWidget

MARGIN = 12  # hysteresis so a panel hovering around the threshold does not flip modes on every pixel


class AdaptiveTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.titles = []; self.compact = False; self.full_width = 0; self.fitting = False
        self.setElideMode(Qt.TextElideMode.ElideNone)

    def addTab(self, *args):
        index = super().addTab(*args); self.titles.insert(index, self.tabText(index)); self.setTabToolTip(index, self.titles[index]); return index

    def resizeEvent(self, event):
        super().resizeEvent(event); self.fit()

    def fit(self):
        """Measure the full-title tab bar and switch to icon-only tabs when it would not fit."""
        if not self.titles or self.fitting: return
        self.fitting = True
        try:
            available = self.width() - 4
            if not self.compact:
                self.full_width = self.tabBar().sizeHint().width()
                if self.full_width > available: self._apply(True)
            elif self.full_width <= available - MARGIN:
                self._apply(False); self.full_width = self.tabBar().sizeHint().width()
                if self.full_width > available: self._apply(True)
        finally: self.fitting = False

    def _apply(self, compact):
        self.compact = compact
        for index, title in enumerate(self.titles): self.setTabText(index, '' if compact else title); self.setTabToolTip(index, title)
