"""Sun Valley inspired Qt styling; no Tk runtime or external assets required."""
from PySide6.QtCore import Qt, QByteArray, QSize
from PySide6.QtGui import QColor, QPalette, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QPushButton

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
}

def icon(name):
    color=QApplication.palette().color(QPalette.ColorRole.WindowText).name()
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</g></svg>'
    pix=QPixmap(48,48);pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix);QSvgRenderer(QByteArray(svg.encode())).render(painter);painter.end();pix.setDevicePixelRatio(2)
    return QIcon(pix)

def decorate(button, name):
    button.setProperty('iconName',name);button.setIcon(icon(name));button.setIconSize(QSize(18,18))

def apply_theme(app, mode='light'):
    dark=mode=='dark'
    bg,base,fg,border,hover,accent,selected=('#202020','#2b2b2b','#f3f3f3','#484848','#383838','#60cdff','#20465b') if dark else ('#f3f3f3','#ffffff','#202020','#d1d1d1','#e9e9e9','#0067c0','#e2eff9')
    palette=QPalette()
    for role,value in {'Window':bg,'WindowText':fg,'Base':base,'AlternateBase':hover,'Text':fg,'Button':base,'ButtonText':fg,'Highlight':accent,'HighlightedText':'#101010' if dark else '#ffffff','ToolTipBase':base,'ToolTipText':fg,'PlaceholderText':'#999999' if dark else '#666666'}.items():
        palette.setColor(getattr(QPalette.ColorRole,role),QColor(value))
    for role in (QPalette.ColorRole.Text,QPalette.ColorRole.ButtonText,QPalette.ColorRole.WindowText):palette.setColor(QPalette.ColorGroup.Disabled,role,QColor('#858585'))
    app.setPalette(palette)
    app.setStyleSheet(f'''
    QWidget {{ font-family:"Segoe UI","Malgun Gothic"; font-size:13px; }}
    QMainWindow,QDialog {{ background:{bg}; }}
    QLineEdit,QPlainTextEdit,QListView,QTreeWidget,QComboBox,QSpinBox,QDoubleSpinBox {{ background:{base}; color:{fg}; border:1px solid {border}; border-radius:5px; padding:6px; selection-background-color:{accent}; }}
    QLineEdit:focus,QPlainTextEdit:focus {{ border-bottom:2px solid {accent}; }}
    QPushButton {{ background:{base}; color:{fg}; border:1px solid {border}; border-radius:5px; padding:7px 9px; }}
    QPushButton:hover {{ background:{hover}; }} QPushButton:pressed {{ background:{selected}; }}
    QPushButton:focus {{ border:1px solid {accent}; }} QPushButton:disabled {{ color:#858585; }}
    QPushButton[primary="true"] {{ border-bottom:2px solid {accent}; }}
    QTabBar::tab {{ padding:9px 8px; margin:1px; }}
    QTabBar::tab:selected {{ background:{base}; border-bottom:3px solid {accent}; }}
    QTabWidget::pane {{ border:0; }} QSplitter::handle {{ background:{border}; }}
    QListView::item {{ padding:6px 4px; }} QListView::item:selected,QTreeView::item:selected {{ background:{selected}; color:{fg}; }}
    QMenu {{ background:{base}; color:{fg}; border:1px solid {border}; padding:4px; }}
    QMenu::item {{ padding:7px 24px; }} QMenu::item:selected {{ background:{selected}; }}
    QToolTip {{ background:{base}; color:{fg}; border:1px solid {border}; padding:5px; }}
    QLabel#brand {{ font-size:21px; font-weight:700; color:{accent}; }}
    ''')
    for widget in app.allWidgets():
        if isinstance(widget,QPushButton) and widget.property('iconName'):decorate(widget,widget.property('iconName'))
