"""Windows shell conveniences shared by context menus. They only open or copy references; source files are never modified."""
import os,subprocess
from pathlib import Path
from PySide6.QtCore import QItemSelectionModel,QUrl
from PySide6.QtGui import QDesktopServices,QGuiApplication

def reveal_in_explorer(path):
    """Show a file selected in its Explorer folder, or open a folder. False when the path no longer exists."""
    target=Path(path)
    if not target.exists():return False
    if os.name!='nt':return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target if target.is_dir() else target.parent)))
    # Windows paths cannot contain quotes, so quoting keeps commas and spaces in one argument.
    subprocess.Popen(f'explorer "{target}"' if target.is_dir() else f'explorer /select,"{target}"');return True

def open_default(path):
    """Open with the app Windows associates with the file type. False when the path no longer exists."""
    target=Path(path)
    return target.exists() and QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

def copy_paths(paths,names=False):
    """Copy full paths (or file names) one per line; returns how many were copied."""
    values=[Path(p).name if names else str(Path(p)) for p in paths]
    if values:QGuiApplication.clipboard().setText('\n'.join(values))
    return len(values)

def select_for_context(view,index):
    """Windows convention: right-clicking outside the selection selects only that item; inside keeps the selection."""
    if not index.isValid():return
    model=view.selectionModel()
    if not model.isSelected(index):model.setCurrentIndex(index,QItemSelectionModel.SelectionFlag.ClearAndSelect)
