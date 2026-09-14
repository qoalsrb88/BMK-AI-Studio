"""Design tokens and Qt styling for the light and dark themes; no external assets required."""
import tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QByteArray, QSize
from PySide6.QtGui import QColor, QPalette, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QPushButton, QLabel

PATHS = {
    'copy': '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    'folder': '<path d="M3 6h7l2 3h9v11H3z"/>',
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="1.5"/><path d="m3 18 6-6 4 4 3-3 5 5"/>',
    'note': '<path d="M5 3h14v18H5zM8 8h8M8 12h8M8 16h5"/>',
    'tag': '<path d="M3 3h9l9 9-9 9-9-9z"/><circle cx="8" cy="8" r="1"/>',
    'edit': '<path d="m4 16 12-12 4 4L8 20H4zM13 7l4 4"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
    'settings': '<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h6l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>',
    'undo': '<path d="M8 4 3 9l5 5M3 9h11a6 6 0 0 1 0 12"/>',
    'save': '<path d="M4 3h13l3 3v15H4zM8 3v6h8V3M8 21v-8h8v8"/>',
    'paste': '<path d="M9 5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/>',
    'external': '<path d="M14 4h6v6M20 4 10 14M18 13v6H5V6h6"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-up': '<path d="m6 15 6-6 6 6"/>',
    'close': '<path d="M6 6l12 12M18 6 6 18"/>',
    'check': '<path d="m5 12 5 5L20 7"/>',
}

# Neutral canvas behind images in both themes so colour judgement does not shift with the UI.
CANVAS = '#66696e'
CANVAS_TEXT = '#d9dce1'

# Spacing scale in pixels; layouts should pick from these steps.
SPACE = (4, 8, 12, 16)

THEMES = {
    'light': dict(bg='#f2f3f5', surface='#ffffff', surface2='#e9ebef', fg='#1b1f26', muted='#6b7480', border='#d5d9e0',
                  accent='#0067c0', accent_hover='#005fb3', accent_pressed='#0053a0', on_accent='#ffffff', selected='#dfeafb', disabled='#9aa2ad'),
    'dark': dict(bg='#1c1e22', surface='#26292e', surface2='#30343a', fg='#e6e8eb', muted='#98a0aa', border='#3b4048',
                 accent='#4cc2ff', accent_hover='#6fd0ff', accent_pressed='#38adeb', on_accent='#0b1a26', selected='#243a4e', disabled='#6b727c'),
}
_mode = 'light'


def tokens(mode=None):
    return THEMES.get(mode or _mode, THEMES['light'])


def _svg(body, color, stroke=1.7, size=24):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24">'
            f'<g fill="none" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>')


def icon(name, color=None):
    color = color or QApplication.palette().color(QPalette.ColorRole.WindowText).name()
    pix = QPixmap(48, 48); pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix); QSvgRenderer(QByteArray(_svg(PATHS[name], color).encode())).render(painter); painter.end(); pix.setDevicePixelRatio(2)
    return QIcon(pix)


def decorate(button, name):
    button.setProperty('iconName', name)
    button.setIcon(icon(name, tokens()['on_accent'] if button.property('primary') else None)); button.setIconSize(QSize(18, 18))


def ghost(button):
    """Icon-only or low-emphasis button: no fill or border until hovered."""
    button.setProperty('ghost', True); return button


def caption(text, role='muted'):
    """Label with a typographic role: 'section' (group header), 'title', 'field' (editor label) or 'muted' (hint)."""
    widget = QLabel(text); widget.setProperty('role', role); return widget


def asset(name, color, size=24):
    """Stylesheet url() needs a file, so each icon/colour pair is written once to the temp folder."""
    folder = Path(tempfile.gettempdir()) / 'bmk-studio-ui'; folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}-{size}.svg"
    if not path.exists(): path.write_text(_svg(PATHS[name], color, 2.4, size), encoding='utf-8')
    return path.as_posix()


def stylesheet(t):
    bg, surface, surface2, fg, muted, border = t['bg'], t['surface'], t['surface2'], t['fg'], t['muted'], t['border']
    accent, accent_hover, accent_pressed, on_accent, selected, disabled = t['accent'], t['accent_hover'], t['accent_pressed'], t['on_accent'], t['selected'], t['disabled']
    chevron_down, chevron_up, close, check = asset('chevron-down', muted), asset('chevron-up', muted), asset('close', muted), asset('check', on_accent, 12)
    return f'''
    QWidget {{ font-family:"Segoe UI","Malgun Gothic"; font-size:13px; color:{fg}; }}
    QMainWindow, QDialog, QMessageBox {{ background:{bg}; }}
    QFrame#header {{ border:0; border-bottom:1px solid {border}; }}
    QStatusBar {{ background:{bg}; color:{muted}; border-top:1px solid {border}; }}
    QStatusBar::item {{ border:0; }}
    QLabel {{ background:transparent; }}
    QLabel#brand {{ font-size:16px; font-weight:700; letter-spacing:1px; color:{accent}; padding:0 6px 0 2px; }}
    QLabel[role="section"] {{ font-size:11px; font-weight:700; letter-spacing:1px; color:{muted}; padding:8px 0 2px 0; }}
    QLabel[role="title"] {{ font-size:15px; font-weight:600; }}
    QLabel[role="field"] {{ font-weight:600; }}
    QLabel[role="muted"] {{ color:{muted}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background:{surface}; color:{fg}; border:1px solid {border}; border-radius:6px; padding:5px 8px; selection-background-color:{accent}; selection-color:{on_accent}; }}
    QListView, QTreeView, QListWidget, QTreeWidget {{ background:{surface}; color:{fg}; border:1px solid {border}; border-radius:6px; padding:2px; selection-background-color:{selected}; outline:0; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border:1px solid {accent}; }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color:{disabled}; background:{bg}; }}
    QLineEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{ background:{bg}; }}
    QComboBox::drop-down {{ border:0; width:24px; subcontrol-origin:padding; subcontrol-position:center right; }}
    QComboBox::down-arrow {{ image:url({chevron_down}); width:14px; height:14px; }}
    QComboBox QAbstractItemView {{ background:{surface}; color:{fg}; border:1px solid {border}; border-radius:6px; padding:4px; selection-background-color:{selected}; selection-color:{fg}; outline:0; }}
    QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ border:0; width:18px; background:transparent; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image:url({chevron_up}); width:10px; height:10px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image:url({chevron_down}); width:10px; height:10px; }}
    QPushButton {{ background:{surface}; color:{fg}; border:1px solid {border}; border-radius:6px; padding:6px 12px; min-height:18px; }}
    QPushButton:hover {{ background:{surface2}; }}
    QPushButton:pressed {{ background:{selected}; }}
    QPushButton:focus {{ border:1px solid {accent}; }}
    QPushButton:disabled {{ color:{disabled}; background:{bg}; }}
    QPushButton[primary="true"] {{ background:{accent}; color:{on_accent}; border:1px solid {accent}; font-weight:600; }}
    QPushButton[primary="true"]:hover {{ background:{accent_hover}; border-color:{accent_hover}; }}
    QPushButton[primary="true"]:pressed {{ background:{accent_pressed}; border-color:{accent_pressed}; }}
    QPushButton[primary="true"]:disabled {{ background:{surface2}; color:{disabled}; border-color:{border}; }}
    QPushButton[ghost="true"] {{ background:transparent; border:1px solid transparent; padding:4px; }}
    QPushButton[ghost="true"]:hover {{ background:{surface2}; }}
    QPushButton[ghost="true"]:pressed {{ background:{selected}; }}
    QPushButton[ghost="true"]:disabled {{ background:transparent; }}
    QCheckBox, QRadioButton {{ spacing:8px; padding:3px 0; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width:16px; height:16px; border:1px solid {muted}; border-radius:4px; background:{surface}; }}
    QRadioButton::indicator {{ border-radius:8px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color:{accent}; }}
    QCheckBox::indicator:checked, QCheckBox::indicator:indeterminate {{ background:{accent}; border-color:{accent}; image:url({check}); }}
    QRadioButton::indicator:checked {{ border:5px solid {accent}; }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color:{border}; background:{bg}; }}
    QCheckBox::indicator:checked:disabled {{ background:{border}; border-color:{border}; }}
    QTabWidget::pane {{ border:0; }}
    QTabBar {{ background:transparent; qproperty-drawBase:0; }}
    QTabBar::tab {{ background:transparent; color:{muted}; padding:8px 10px; margin-right:2px; border-bottom:2px solid transparent; }}
    QTabBar::tab:hover {{ color:{fg}; }}
    QTabBar::tab:selected {{ color:{fg}; border-bottom:2px solid {accent}; font-weight:600; }}
    QTabBar#mainNav::tab {{ font-size:14px; padding:9px 14px; }}
    QTabBar::close-button {{ image:url({close}); width:12px; height:12px; margin:2px; border-radius:3px; }}
    QTabBar::close-button:hover {{ background:{surface2}; }}
    QListView::item, QTreeView::item, QListWidget::item, QTreeWidget::item {{ padding:5px 4px; border-radius:4px; }}
    QListView::item:hover, QTreeView::item:hover {{ background:{surface2}; }}
    QListView::item:selected, QTreeView::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {{ background:{selected}; color:{fg}; }}
    QHeaderView::section {{ background:{surface2}; color:{muted}; border:0; border-bottom:1px solid {border}; padding:6px 8px; font-weight:600; }}
    QScrollBar:vertical {{ background:transparent; width:12px; margin:0; }}
    QScrollBar::handle:vertical {{ background:{border}; border-radius:4px; min-height:28px; margin:2px 3px; }}
    QScrollBar::handle:vertical:hover {{ background:{muted}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; background:transparent; }}
    QScrollBar:horizontal {{ background:transparent; height:12px; margin:0; }}
    QScrollBar::handle:horizontal {{ background:{border}; border-radius:4px; min-width:28px; margin:3px 2px; }}
    QScrollBar::handle:horizontal:hover {{ background:{muted}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; background:transparent; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
    QSlider::groove:horizontal {{ height:4px; background:{border}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{accent}; border-radius:2px; }}
    QSlider::handle:horizontal {{ width:14px; margin:-5px 0; background:{surface}; border:2px solid {accent}; border-radius:7px; }}
    QProgressBar {{ background:{surface2}; border:1px solid {border}; border-radius:5px; min-height:16px; max-height:16px; text-align:center; color:{fg}; }}
    QProgressBar::chunk {{ background:{accent}; border-radius:4px; }}
    QMenu {{ background:{surface}; color:{fg}; border:1px solid {border}; border-radius:6px; padding:6px; }}
    QMenu::item {{ padding:6px 24px 6px 12px; border-radius:4px; }}
    QMenu::item:selected {{ background:{selected}; }}
    QMenu::item:disabled {{ color:{disabled}; }}
    QMenu::separator {{ height:1px; background:{border}; margin:4px 8px; }}
    QToolTip {{ background:{surface}; color:{fg}; border:1px solid {border}; border-radius:4px; padding:6px 8px; }}
    QSplitter::handle {{ background:transparent; }}
    QSplitter::handle:horizontal {{ width:6px; }}
    QSplitter::handle:vertical {{ height:6px; }}
    QSplitter::handle:hover {{ background:{selected}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:0; }}
    QGraphicsView {{ border:1px solid {border}; }}
    QDialogButtonBox QPushButton {{ min-width:72px; }}
    '''


def apply_theme(app, mode='light'):
    global _mode
    _mode = mode if mode in THEMES else 'light'; t = tokens()
    palette = QPalette()
    roles = {'Window': t['bg'], 'WindowText': t['fg'], 'Base': t['surface'], 'AlternateBase': t['surface2'], 'Text': t['fg'], 'Button': t['surface'], 'ButtonText': t['fg'],
             'Highlight': t['accent'], 'HighlightedText': t['on_accent'], 'ToolTipBase': t['surface'], 'ToolTipText': t['fg'], 'PlaceholderText': t['muted'], 'Link': t['accent']}
    for role, value in roles.items(): palette.setColor(getattr(QPalette.ColorRole, role), QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText): palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(t['disabled']))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(t))
    for widget in app.allWidgets():
        if isinstance(widget, QPushButton) and widget.property('iconName'): decorate(widget, widget.property('iconName'))
