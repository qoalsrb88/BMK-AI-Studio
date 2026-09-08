from __future__ import annotations
import json
import os
import sys
import copy
from datetime import datetime
from pathlib import Path
from PIL import Image
from PIL.ImageQt import ImageQt
from PySide6.QtCore import Qt, QThread, Signal, QMimeData, QUrl, QRectF, QTimer, QSettings, QSize
from PySide6.QtGui import QPixmap, QColor, QPen, QKeySequence, QAction, QActionGroup, QPainter, QDesktopServices, QFontDatabase, QFont, QTextCursor, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QPushButton, QLineEdit, QPlainTextEdit, QTabWidget, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QComboBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem, QAbstractItemView,
    QDialog, QDialogButtonBox, QFormLayout, QProgressBar, QTreeWidget, QTreeWidgetItem, QScrollArea, QTabBar, QMenu, QSlider, QStackedWidget)
from .workspace import WorkspaceMixin
from .discovery_ui import DiscoveryMixin
from .appearance import apply_theme, decorate, icon
from .crop_ui import CropInteraction,bounded_box,anchored_box,snap_value
from . import data_location
from .data_dialog import DataDirectoryDialog
from .core import (Store, data_dir, inspect_image, load_image, json_text, fingerprint,
    unique_path, save_derived, crop_image, stitch_image, tone_restore, EXTENSIONS, file_stamp, resize_image, normalize_category, validate_note, searchable_tags)
from .vendor.prompt_converter import BMKPromptSyntaxConverter
from .tagger import Tagger, model_signature, inference_signature
from .batch import BatchTagJob
from .library import IndexJob, FolderWatch, folder_snapshot
from .library_view import LibraryView
from .library_disk import SearchExtras
from .sessions import Sessions
from .relink import relink_source
from .prompt_tools import export_stem
from .wildcard_dialog import WildcardDialog
from .note_fields import NoteFieldsDialog
from .model_dialog import ModelDownloadDialog
from .queue_dialog import QueueDialog
from .gpu_tone import tone_restore_cuda
from .color import normalize_source,high_precision
from .stitch_dialog import StitchDialog
from .dialogs import ResizeDialog, CompareDialog, MaskDialog, ToneDialog, RevisionDialog

STYLE = '''
QWidget { background:#171c24; color:#dce3ed; font-family:"Segoe UI","Malgun Gothic"; font-size:13px; }
QMainWindow { background:#11161d; }
QLineEdit,QPlainTextEdit,QListWidget,QListView,QTreeWidget,QComboBox,QSpinBox,QDoubleSpinBox { background:#10151d; border:1px solid #303b4c; border-radius:6px; padding:7px; selection-background-color:#285a71; }
QPushButton { background:#263242; border:1px solid #3a4b60; border-radius:6px; padding:8px 11px; }
QPushButton:hover { background:#35475c; } QPushButton:disabled { color:#667486; }
QPushButton[primary="true"] { background:#176b65; border-color:#288d85; color:white; }
QTabBar::tab { padding:10px 12px; color:#8f9fb2; } QTabBar::tab:selected { color:#74ddc9; border-bottom:2px solid #74ddc9; }
QTabWidget::pane { border:0; } QSplitter::handle { background:#303b4c; }
QListWidget::item,QListView::item { padding:10px 5px; } QListWidget::item:selected,QListView::item:selected { background:#233f4c; }
QLabel#muted { color:#8f9fb2; } QStatusBar { background:#10151d; color:#8f9fb2; }
'''

def configure_app(app):
    # Also provides real glyphs on Qt's offscreen platform used for visual QA.
    fonts=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    for name in ('malgun.ttf','malgunbd.ttf','segoeui.ttf'):
        if (fonts/name).is_file():QFontDatabase.addApplicationFont(str(fonts/name))
    app.setFont(QFont('Malgun Gothic',10))
    app.setStyle('Fusion');apply_theme(app)

def button(text, fn, primary=False):
    b = QPushButton(text)
    b.setProperty('primary',primary)
    b.clicked.connect(fn)
    for word,name in [('복사','copy'),('폴더','folder'),('이미지','image'),('노트','note'),('태깅','tag'),('실행 취소','undo'),('내보내기','save'),('보관','save')]:
        if word in text:decorate(b,name);break
    return b

def row(*widgets):
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0,0,0,0)
    for item in widgets:
        layout.addWidget(item)
    return w

def replace_text(editor,text):
    cursor=editor.textCursor();cursor.beginEditBlock();cursor.select(QTextCursor.SelectionType.Document);cursor.insertText(text);cursor.endEditBlock()

class Job(QThread):
    result = Signal(object)
    failed = Signal(str)
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
    def run(self):
        try:
            self.result.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc))

class Viewer(CropInteraction,QGraphicsView):
    cropChanged = Signal(object)
    interpolationChanged = Signal(str)
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor('#0c1118'))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.crop_mode = False
        self.crop_item = None
        self.image_rect = QRectF()
        self.ratio = 0
        self.origin = None
        self.pixmap_item = None
        self.interpolation = 'smooth'
        self.overscroll = 25
        self.init_crop()
        welcome=self.scene().addText('이미지와 프롬프트를 한곳에서\n\n이미지·폴더를 열거나 이 창으로 드롭하세요.\n\n원본 읽기 → 작업 프롬프트 → 편집 → 내보내기')
        welcome.setDefaultTextColor(QColor('#92adbb'))
        welcome.setFont(QFont('Malgun Gothic',13))
    def display(self, image, fit=True):
        self.crop_drag=None;self.crop_pan=None;self.set_crop_box(None)
        self.image_rect=QRectF()
        self.scene().clear()
        self.pixmap_item = None
        self.crop_item = None
        self.origin = None
        if image is None:
            return
        pix = QPixmap.fromImage(ImageQt(image.convert('RGBA')))
        self.pixmap_item = self.scene().addPixmap(pix)
        self.set_interpolation(self.interpolation)
        self.image_rect = QRectF(0,0,image.width,image.height)
        self.scene().setSceneRect(self.image_rect)
        if fit: self.fit()
        else:self.update_scroll_margin()
    def fit(self):
        if self.image_rect.isEmpty():return
        self.scene().setSceneRect(self.image_rect)
        self.fitInView(self.image_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.update_scroll_margin();self.centerOn(self.image_rect.center())
    def actual_size(self):
        self.resetTransform();self.update_scroll_margin();self.centerOn(self.image_rect.center())
    def update_scroll_margin(self):
        if self.image_rect.isEmpty():return
        scale=max(self.transform().m11(),.00001)
        # Margin is a fraction of the viewport, capped at half the displayed image.
        x=min(self.viewport().width()/scale*self.overscroll/100,self.image_rect.width()/2)
        y=min(self.viewport().height()/scale*self.overscroll/100,self.image_rect.height()/2)
        self.scene().setSceneRect(self.image_rect.adjusted(-x,-y,x,y))
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'image_rect'):self.update_scroll_margin()
    def set_interpolation(self,mode):
        self.interpolation=mode if mode in ('nearest','smooth') else 'smooth'
        smooth=self.interpolation=='smooth'
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,smooth)
        if self.pixmap_item:self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation)
        self.viewport().update()
    def interpolation_menu(self):
        menu=QMenu(self);group=QActionGroup(menu);group.setExclusive(True)
        for label,mode in [('필터 적용 안 함 · 도트 이미지','nearest'),('부드럽게 · 일반 이미지','smooth')]:
            action=menu.addAction(label);action.setCheckable(True);action.setChecked(self.interpolation==mode);group.addAction(action)
            action.triggered.connect(lambda checked=False,m=mode:self.choose_interpolation(m))
        menu.addSeparator();menu.addAction('화면 맞춤',self.fit);menu.addAction('100%',self.actual_size)
        return menu
    def choose_interpolation(self,mode):
        self.set_interpolation(mode);self.interpolationChanged.emit(self.interpolation)
    def contextMenuEvent(self,event):
        menu=self.interpolation_menu();menu.exec(event.globalPos());menu.deleteLater()
    def wheelEvent(self,event):
        factor = 1.2 if event.angleDelta().y()>0 else 1/1.2
        if .01<=self.transform().m11()*factor<=64:
            self.scale(factor,factor);self.update_scroll_margin()

class CheckpointWait(QDialog):
    def reject(self):pass
    def closeEvent(self,event):event.ignore()

from .main_tabs import MainTabsMixin

class Studio(MainTabsMixin,DiscoveryMixin,WorkspaceMixin,QMainWindow):
    def __init__(self, root=None, location_config=None):
        super().__init__()
        self.setWindowTitle('BMK AI Studio 0.9.7 · 이미지와 프롬프트 작업실')
        self.location_config=Path(location_config) if location_config else (Path(root).parent/'test-data-location.json' if root is not None else data_location.config_path())
        self.data_switch_ready=False
        self.resize(1500,960)
        self.setMinimumSize(1120,760)
        self.setAcceptDrops(True)
        self.store = Store(root)
        self.sessions=Sessions(self.store.root)
        self.recovery=Sessions(self.store.root/'recovery')
        self.recovery_job=None;self.recovery_versions={};self.recovery_saved={}
        self.restoring_documents=True
        queue=self.store.state('tag_queue') or {}
        self.tag_queue=list(dict.fromkeys(path for path in queue.get('active',[])+queue.get('pending',[]) if isinstance(path,str))) if isinstance(queue,dict) else []
        self.queue_active=[];self.queue_running=False;self.queue_dialog=None
        self.settings = QSettings('BMK','AI-Studio')
        self.path = None
        self.info = None
        self.original = None
        self.current = None
        self.crop_context = None
        self.rotation = 0
        self.box = None
        self.scores = None
        self.jobs = []
        self.tagger = Tagger()
        self.tag_busy = False
        self.note_id = None
        self.note_extra = {}
        self.note_mode = False
        self.document_index = 0
        self.loading = False
        self.history = []
        self.operations = []
        self.exported_state = ''
        self.checkpoint_state = ''
        self.source_hash = None
        self.library_items={}
        self.searchable={}
        self.search_extra=SearchExtras(self.store)
        self.removed_paths=self.store.hidden_paths()
        self.removal_history=[]
        self.index_stamps={}
        self.index_retries={}
        self.pending_index=set()
        self.indexing=set()
        self.index_job=None
        self.batch_job=None
        self.watch_job=None
        self.folder=None
        self.load_stamp=None
        self.closing_requested=False
        self.build()
        self.appearance=self.store.state('appearance') or {}
        self.apply_appearance()
        self.refresh_notes()
        self.restore_library()
        self.restore_window_state()
        self.restore_documents()
        self.restoring_documents=False;self.save_documents()
        self.recovery_timer=QTimer(self);self.recovery_timer.setInterval(10000);self.recovery_timer.timeout.connect(self.auto_checkpoint);self.recovery_timer.start()
        self.initialize_workspace();self.restore_main_workspace()
        if self.store.needs_tag_search():
            root=self.store.root
            def migrate_search():
                store=Store(root)
                try:return store.backfill_tag_search()
                finally:store.db.close()
            def search_ready(count):
                self.search_extra.clear();self.library.refresh_query()
            self.task(migrate_search,search_ready)
        self.statusBar().showMessage('이미지·폴더를 드롭하거나 Ctrl+O로 시작하세요. 원본 파일은 수정하지 않습니다.')

    def prompt_header(self,label,editor):
        copy=button('',lambda:self.copy_text(editor.toPlainText()));decorate(copy,'copy')
        copy.setFixedSize(30,30);copy.setToolTip(label+' 전체 복사');copy.setAccessibleName(label+' 전체 복사')
        copy.setEnabled(bool(editor.toPlainText()))
        editor.textChanged.connect(lambda:copy.setEnabled(bool(editor.toPlainText())))
        return row(QLabel(label),copy)

    def apply_appearance(self):
        apply_theme(QApplication.instance(),self.appearance.get('theme','light'))
        self.viewer.setBackgroundBrush(QColor('#181818' if self.appearance.get('theme')=='dark' else '#e5e5e5'))
        self.viewer.set_interpolation(self.appearance.get('interpolation','smooth'))
        try:self.viewer.overscroll=max(0,min(50,int(self.appearance.get('overscroll',25))))
        except (ValueError,TypeError):self.viewer.overscroll=25
        self.viewer.update_scroll_margin()
        if hasattr(self,'disk_browser'):
            self.disk_browser.viewer.setBackgroundBrush(self.viewer.backgroundBrush());self.disk_browser.viewer.set_interpolation(self.viewer.interpolation);self.disk_browser.viewer.overscroll=self.viewer.overscroll;self.disk_browser.viewer.update_scroll_margin()
        self.thumbnail_slider.setValue(max(40,min(512,int(self.appearance.get('thumbnail_size',128)))))
        self.crop_snap.setCurrentIndex(max(0,self.crop_snap.findData(self.appearance.get('crop_snap',1))))
        for i,name in enumerate(('image','note','tag','edit','info')):self.tabs.setTabIcon(i,icon(name))

    def resize_thumbnails(self,size):
        self.library.set_thumbnail_size(64 if getattr(self,'active_workspace',None)=='work' else size);self.thumbnail_label.setText(f'갤러리 {size}px')
        if hasattr(self,'appearance'):
            self.appearance['thumbnail_size']=size;self.store.state('appearance',self.appearance)

    def save_interpolation(self,mode):
        self.appearance['interpolation']=mode;self.store.state('appearance',self.appearance)
        self.statusBar().showMessage('미리보기 보간 설정 저장 · 원본과 내보내기 픽셀은 변경되지 않습니다.',5000)

    def open_settings(self):
        dialog=QDialog(self);dialog.setWindowTitle('전역 설정');layout=QFormLayout(dialog)
        theme=QComboBox();theme.addItem('라이트 (기본)','light');theme.addItem('다크','dark');theme.setCurrentIndex(max(0,theme.findData(self.appearance.get('theme','light'))))
        interpolation=QComboBox();interpolation.addItem('부드럽게 · 일반 이미지','smooth');interpolation.addItem('필터 적용 안 함 · 도트 이미지','nearest');interpolation.setCurrentIndex(max(0,interpolation.findData(self.viewer.interpolation)))
        margin=QSpinBox();margin.setRange(0,50);margin.setSuffix(' %');margin.setValue(self.viewer.overscroll)
        recovery=QCheckBox('10초마다 변경된 편집을 백그라운드 복구본으로 저장');recovery.setChecked(self.appearance.get('auto_checkpoint',True))
        layout.addRow('화면 테마',theme);layout.addRow('미리보기 보간',interpolation);layout.addRow('가장자리 이동 여유',margin)
        layout.addRow('비정상 종료 복구',recovery)
        current_data=QLineEdit(str(self.store.root));current_data.setReadOnly(True);layout.addRow('사용자 데이터 폴더',current_data)
        change_data=button('사용자 데이터 폴더 변경…',lambda:dialog.reject() if self.change_data_directory() else None);layout.addRow(change_data)
        if data_location.session_directory or os.environ.get('BMK_STUDIO_DATA','').strip():
            change_data.setEnabled(False);layout.addRow(QLabel('실행 옵션 또는 BMK_STUDIO_DATA로 경로를 지정했습니다.\n설정에서 변경하려면 해당 경로 지정을 해제하고 실행하세요.'))
        naming=QLineEdit(self.appearance.get('export_pattern','{source}_edited'));layout.addRow('내보내기 이름 규칙',naming)
        name_preview=QLabel();name_preview.setWordWrap(True);layout.addRow('이름 미리보기',name_preview)
        def preview_name():
            try:name_preview.setText(export_stem(naming.text(),self.path or 'image.png',self.current.size if self.current else (1024,1024),self.note_title.text())+'.png')
            except ValueError as exc:name_preview.setText(str(exc))
        naming.textChanged.connect(preview_name);preview_name()
        layout.addRow(QLabel('{source} {date} {time} {width} {height} {note} · 금지 문자는 자동 정리'))
        hint=QLabel('이동 여유는 화면 크기 기준이며 이미지 크기의 절반을 넘지 않습니다.\n미리보기 우클릭으로도 보간을 변경할 수 있습니다.\n설정은 다음 실행에도 유지됩니다.');hint.setWordWrap(True);layout.addRow(hint)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        def accept_settings():
            try:export_stem(naming.text(),'image.png',(1024,1024))
            except ValueError as exc:self.error(str(exc));return
            dialog.accept()
        controls.accepted.connect(accept_settings);controls.rejected.connect(dialog.reject);layout.addRow(controls)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.appearance.update(theme=theme.currentData(),interpolation=interpolation.currentData(),overscroll=margin.value())
            self.appearance['auto_checkpoint']=recovery.isChecked()
            self.appearance['export_pattern']=naming.text()
            self.store.state('appearance',self.appearance);self.apply_appearance()

    def change_data_directory(self):
        if data_location.session_directory or os.environ.get('BMK_STUDIO_DATA','').strip():return False
        if self.jobs:
            self.error('폴더 감시·태깅·다운로드 등 진행 중인 작업을 마친 뒤 데이터 폴더를 변경하세요.');return False
        dialog=DataDirectoryDialog(self.store.root,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return False
        if self.jobs:
            self.error('폴더 선택 중 시작된 백그라운드 작업이 있습니다. 완료 또는 취소 후 다시 변경하세요.');return False
        self.autosave.stop();self.recovery_timer.stop();self.library.stop_search();self.disk_browser.set_active(False)
        success=False
        try:
            self.save_draft();self.save_documents();self.save_window_state();self.save_queue()
            if self.image_dirty() and not self.save_edit_session():return False
            self.store.db.commit()
            result=self.session_operation(lambda:data_location.activate_directory(self.store.root,dialog.target.text(),dialog.mode.currentData(),self.location_config),'사용자 데이터를 확인하고 복사합니다. 완료되면 앱을 종료합니다…')
            if not result:return False
            success=True;self.data_switch_ready=True;self.closing_requested=True
            self.statusBar().showMessage('사용자 데이터 폴더 변경 완료 · 다음 실행부터 '+result['directory'])
            QTimer.singleShot(0,self.close);return True
        finally:
            if not success:
                self.recovery_timer.start();self.library.resume_search();self.disk_browser.set_active(self.workspace_mode.currentData()=='disk')
                self.autosave.start()

    def build(self):
        host = QWidget()
        outer = QVBoxLayout(host)
        outer.setContentsMargins(18,15,18,10)
        title = QLabel('BMK  /  AI STUDIO')
        title.setObjectName('brand')
        self.workspace_mode=QComboBox();self.workspace_mode.addItem('탐색 · 갤러리','browse');self.workspace_mode.addItem('작업 · 미리보기','work');self.workspace_mode.addItem('폴더 탐색','disk')
        self.workspace_mode.setAccessibleName('화면 모드');self.workspace_mode.currentIndexChanged.connect(self.switch_workspace)
        self.settings_button=button('설정',self.open_settings);decorate(self.settings_button,'settings')
        self.settings_button.setToolTip('전역 설정 · 테마 / 미리보기')
        outer.addWidget(row(title,self.workspace_mode, button('이미지 추가',self.open_file),button('폴더 추가',self.open_folder),
                            button('붙여넣기',self.paste),button('작업 폴더',lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root)))),self.settings_button))
        splitter = QSplitter();self.main_splitter=splitter
        outer.addWidget(splitter,1)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0,8,8,0)
        ll.addWidget(QLabel('LIBRARY  ·  이미지 / 노트'))
        self.search = QLineEdit(); self.search.setPlaceholderText('파일명·메타·작업·추정 태그 검색')
        self.search.textChanged.connect(self.search_changed); ll.addWidget(self.search)
        self.build_browser_controls(ll)
        self.library = LibraryView(self.store.root/'library.sqlite3',self); self.library.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.library.setIconSize(QSize(64,64));self.library.setUniformItemSizes(True)
        self.library.itemClicked.connect(lambda item:self.safe(lambda:self.load(item.data(Qt.ItemDataRole.UserRole))))
        self.library.removeRequested.connect(lambda path:self.remove_library_paths([path]))
        self.library.doubleClicked.connect(lambda index:self.workspace_mode.setCurrentIndex(1))
        self.thumbnail_label=QLabel('썸네일 64px');self.thumbnail_slider=QSlider(Qt.Orientation.Horizontal)
        self.thumbnail_slider.setRange(40,512);self.thumbnail_slider.setValue(64);self.thumbnail_slider.setAccessibleName('갤러리 썸네일 크기')
        self.thumbnail_slider.valueChanged.connect(self.resize_thumbnails);ll.addWidget(row(self.thumbnail_label,self.thumbnail_slider))
        ll.addWidget(button('선택 항목을 목록에서 제거',self.remove_library_selection))
        self.restore_removed_button=button('목록 제거 되돌리기',self.undo_library_removal);self.restore_removed_button.setEnabled(False);decorate(self.restore_removed_button,'undo');ll.addWidget(self.restore_removed_button)
        self.watch_toggle=QCheckBox('열어 둔 폴더의 새 이미지 자동 수집')
        self.watch_toggle.toggled.connect(self.toggle_watch);ll.addWidget(self.watch_toggle)
        self.library_status=QLabel('폴더를 열면 감시를 켤 수 있습니다.');self.library_status.setWordWrap(True);ll.addWidget(self.library_status)
        self.library.searching.connect(lambda active:self.library_status.setText('디스크 검색 중…' if active else f'{self.library.proxy.rowCount()} / {self.library.count()}개 이미지'))
        self.note_browser=QWidget();nl=QVBoxLayout(self.note_browser);nl.setContentsMargins(0,0,8,0)
        nl.addWidget(QLabel('PROMPT NOTES'))
        self.note_search=QLineEdit();self.note_search.setPlaceholderText('노트만 검색');self.note_search.textChanged.connect(self.refresh_notes);nl.addWidget(self.note_search)
        self.notes = QTreeWidget();self.notes.setHeaderHidden(True); self.notes.itemClicked.connect(self.open_note); nl.addWidget(self.notes,2)
        self.show_archived=QCheckBox('보관함 보기');self.show_archived.toggled.connect(self.refresh_notes);nl.addWidget(self.show_archived)
        nl.addWidget(row(button('노트 가져오기',self.import_notes),button('새 노트',self.new_note)))
        nl.addWidget(button('노트 폴더 가져오기',self.import_note_folder))
        self.notes.setMinimumHeight(150)
        sidebar=QScrollArea();sidebar.setWidgetResizable(True);sidebar.setWidget(left);sidebar.setMinimumWidth(245);splitter.addWidget(sidebar)
        center_host=QWidget();center_layout=QVBoxLayout(center_host);center_layout.setContentsMargins(6,8,6,0)
        self.selection_label=QLabel('선택 0개');self.browser_count=QLabel('0개')
        self.selection_actions=button('선택 작업',self.selection_menu)
        self.sort_order=QComboBox();self.sort_order.addItems(['추가 순서','파일명 ↑','파일명 ↓'])
        self.sort_order.currentIndexChanged.connect(lambda i:self.library.proxy.sort(-1 if i==0 else 0,Qt.SortOrder.DescendingOrder if i==2 else Qt.SortOrder.AscendingOrder))
        center_layout.addWidget(row(self.browser_count,self.selection_label,self.selection_actions,self.sort_order))
        self.compare_button=button('A/B 비교',self.compare_selection)
        self.inspector_toggle=QCheckBox('정보 패널');self.inspector_toggle.setChecked(True)
        self.inspector_toggle.toggled.connect(lambda on:self.tabs.setVisible(on))
        center_layout.addWidget(row(button('현재 이미지 A로 고정',self.pin_compare),self.compare_button,self.inspector_toggle))
        center = QWidget();self.preview_panel=center;cl=QVBoxLayout(center);cl.setContentsMargins(0,0,0,0)
        self.file_label=QLabel('이미지를 여기에 놓으세요'); self.file_label.setWordWrap(True); cl.addWidget(self.file_label)
        self.viewer=Viewer(); self.viewer.cropChanged.connect(self.set_box); cl.addWidget(self.viewer,1)
        cl.addWidget(row(button('화면 맞춤',self.viewer.fit),button('100%',self.viewer.actual_size),button('실행 취소',self.undo)))
        self.viewer.interpolationChanged.connect(self.save_interpolation)
        cl.addWidget(row(button('보기 / 복사 / 보관',self.viewer_actions),button('작업본 내보내기',self.export_image,True)))
        center_layout.addWidget(center,1);center_layout.addWidget(self.library,1)
        self.save_status=QLabel('텍스트 저장됨');self.save_status.setWordWrap(True);center_layout.addWidget(self.save_status)
        self.jobs_status=QLabel('작업 대기');center_layout.addWidget(self.jobs_status)
        splitter.addWidget(center_host)
        self.tabs=QTabWidget(); splitter.addWidget(self.tabs)
        splitter.setSizes([240,730,510])
        original_page=QWidget(); ol=QVBoxLayout(original_page)
        self.source=QLabel('원본 메타데이터'); self.source.setWordWrap(True); ol.addWidget(self.source)
        self.positive=QPlainTextEdit(); self.positive.setReadOnly(True); self.positive.setPlaceholderText('파일에 저장된 프롬프트')
        self.negative=QPlainTextEdit(); self.negative.setReadOnly(True); self.negative.setPlaceholderText('파일에 저장된 네거티브')
        ol.addWidget(self.prompt_header('프롬프트',self.positive));ol.addWidget(self.positive,3)
        ol.addWidget(self.prompt_header('네거티브',self.negative));ol.addWidget(self.negative,2)
        ol.addWidget(row(button('프롬프트 복사',lambda:self.copy_text(self.positive.toPlainText())),button('작업으로 가져오기',self.use_original,True)))
        self.tabs.addTab(original_page,'원본')
        work=QWidget();self.image_work_layout=QVBoxLayout(work);self.prompt_editor=QWidget();self.image_work_layout.addWidget(self.prompt_editor);wl=QVBoxLayout(self.prompt_editor)
        self.note_tabs=QTabBar();self.note_tabs.setExpanding(False);self.note_tabs.setTabsClosable(True)
        self.note_tabs.addTab('이미지 작업');self.note_tabs.setTabData(0,{'id':None})
        self.note_tabs.setTabButton(0,QTabBar.ButtonPosition.RightSide,None)
        self.note_tabs.currentChanged.connect(self.activate_document);self.note_tabs.tabCloseRequested.connect(self.close_document)
        wl.addWidget(self.note_tabs)
        self.note_title=QLineEdit(); self.note_title.setPlaceholderText('프로젝트 / 캐릭터 / 노트 이름'); wl.addWidget(self.note_title)
        self.note_category=QComboBox();self.note_category.setEditable(True);self.note_category.setPlaceholderText('카테고리 (예: 캐릭터/의상)');wl.addWidget(self.note_category)
        self.draft=QPlainTextEdit(); self.draft.setPlaceholderText('다음 생성에 사용할 프롬프트');self.work_prompt_header=self.prompt_header('작업 프롬프트',self.draft);wl.addWidget(self.work_prompt_header); wl.addWidget(self.draft,4)
        self.draft_negative=QPlainTextEdit(); self.draft_negative.setPlaceholderText('작업 네거티브');self.work_negative_header=self.prompt_header('작업 네거티브',self.draft_negative);wl.addWidget(self.work_negative_header); wl.addWidget(self.draft_negative,2)
        self.memo=QPlainTextEdit(); self.memo.setPlaceholderText('설정·서비스·작업 메모'); wl.addWidget(self.memo,2)
        self.conversion=QComboBox(); self.conversion.addItems(BMKPromptSyntaxConverter.MODES)
        wl.addWidget(row(self.conversion,button('문법 변환',self.convert)))
        wl.addWidget(button('와일드카드 편집 / 확장',self.expand_work_wildcards))
        wl.addWidget(button('프롬프트 조각 보관함',self.prompt_snippets))
        self.note_save_button=button('노트 저장',self.save_note,True);wl.addWidget(row(button('중복 태그 정리',self.dedupe),button('복사',lambda:self.copy_text(self.draft.toPlainText())),self.note_save_button))
        self.note_revision_row=row(button('버전 이력 / 복원',self.note_history),button('보관 / 복구',self.archive_current_note),button('JSON 내보내기',self.export_note));wl.addWidget(self.note_revision_row)
        self.note_fields_row=row(button('BMK 추가 필드',self.edit_note_fields),button('전체 JSON 편집',self.edit_note_json));wl.addWidget(self.note_fields_row)
        self.note_only_controls=[self.note_tabs,self.note_title,self.note_category,self.note_save_button,self.note_revision_row,self.note_fields_row]
        self.image_note_save=button('노트에 저장…',self.save_image_to_note);wl.addWidget(self.image_note_save)
        ol.addWidget(button('노트에 저장…',self.save_image_to_note))
        self.tabs.addTab(work,'작업 프롬프트')
        tags=QWidget(); tl=QVBoxLayout(tags);tl.addWidget(button('노트에 저장…',self.save_image_to_note))
        default_model=''
        local=Path(__file__).resolve().parent.parent/'local-settings.json'
        if local.is_file():
            try:default_model=json.loads(local.read_text(encoding='utf-8')).get('model_path','')
            except (ValueError,OSError):pass
        self.model_path=QLineEdit(str(self.settings.value('model_path',default_model))); self.model_path.setPlaceholderText('WD v3 모델 폴더')
        tl.addWidget(row(self.model_path,button('찾기',self.choose_model),button('다운로드',self.download_model)))
        tl.addWidget(QLabel('추정 태그는 원본 프롬프트와 별도로 보관됩니다.'))
        self.precision=QComboBox();self.precision.addItem('FP32 · 기본 / CPU·CUDA','fp32');self.precision.addItem('FP16 · CUDA 혼합 정밀도','fp16');self.precision.addItem('BF16 · 지원 CUDA GPU','bf16')
        self.precision.currentIndexChanged.connect(self.refresh_saved_tags);tl.addWidget(self.precision)
        self.threshold=QDoubleSpinBox(); self.threshold.setRange(0,1);self.threshold.setSingleStep(.05);self.threshold.setValue(.35)
        self.char_threshold=QDoubleSpinBox();self.char_threshold.setRange(0,1);self.char_threshold.setValue(.75)
        self.threshold.valueChanged.connect(self.render_tags);self.char_threshold.valueChanged.connect(self.render_tags)
        tl.addWidget(row(QLabel('일반'),self.threshold,QLabel('캐릭터'),self.char_threshold))
        self.exclude=QLineEdit();self.exclude.setPlaceholderText('제외 태그 (콤마 구분)');self.exclude.textChanged.connect(self.render_tags);tl.addWidget(self.exclude)
        self.tag_button=button('현재 원본 태깅',self.run_tags,True)
        self.batch_button=button('선택 이미지 일괄 태깅',self.run_selected_tags,True)
        tl.addWidget(row(self.tag_button,self.batch_button))
        tl.addWidget(row(button('선택을 대기열에 추가',self.enqueue_selected),button('대기열 관리',self.open_queue)))
        self.batch_size=QSpinBox();self.batch_size.setRange(1,16);self.batch_size.setValue(4)
        self.cancel_button=button('작업 취소',self.cancel_tags);self.cancel_button.setEnabled(False)
        tl.addWidget(row(QLabel('추론 배치 크기'),self.batch_size,self.cancel_button))
        self.tag_progress=QProgressBar();self.tag_progress.setRange(0,1);self.tag_progress.setValue(0);tl.addWidget(self.tag_progress)
        tl.addWidget(button('태깅 모델 메모리 해제',self.unload_tagger))
        self.tag_list=QListWidget();self.tag_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);tl.addWidget(self.tag_list,1)
        tl.addWidget(row(button('표시 태그 복사',lambda:self.copy_text(self.tag_text())),button('선택 태그 추가',self.append_tags)))
        self.tag_status=QLabel('WD v3 · GPU 자동 선택 · 임계값 변경 시 재추론 없음');self.tag_status.setWordWrap(True);tl.addWidget(self.tag_status)
        self.job_log=QPlainTextEdit();self.job_log.setReadOnly(True);self.job_log.setMaximumBlockCount(200);self.job_log.setMaximumHeight(95);self.job_log.setPlaceholderText('일괄 처리 결과 / 오류');tl.addWidget(self.job_log)
        tl.addWidget(button('현재 추정 태그 JSON 내보내기',self.export_tags))
        self.model_path.textChanged.connect(self.refresh_saved_tags)
        self.tabs.addTab(tags,'태깅')
        edit=QWidget(); edit_layout=QVBoxLayout(edit)
        self.edit_tool=QComboBox();self.edit_tool.addItems(['크롭','크기 / 회전','스티치','톤 복원','고급 색상'])
        edit_layout.addWidget(self.edit_tool);self.edit_pages=QStackedWidget();edit_layout.addWidget(self.edit_pages,1)
        crop_page=QWidget();el=QVBoxLayout(crop_page);self.edit_pages.addWidget(crop_page)
        self.crop_toggle=QCheckBox('크롭 영역 편집 · 드래그 / 이동 / 크기 조절');self.crop_toggle.toggled.connect(self.toggle_crop);el.addWidget(self.crop_toggle)
        self.ratio=QComboBox();self.ratio.addItems(['자유','1:1','2:3','3:2','3:4','4:3','9:16','16:9']);self.ratio.currentTextChanged.connect(self.set_ratio)
        el.addWidget(row(self.ratio,button('90° 회전',self.rotate)))
        self.crop_snap=QComboBox()
        for value in (1,8,16,32,64):self.crop_snap.addItem('끄기 · 1 px' if value==1 else f'{value} px',value)
        self.crop_snap.currentIndexChanged.connect(self.change_crop_snap)
        el.addWidget(row(QLabel('스냅'),self.crop_snap,button('새 영역',self.new_crop_selection)))
        self.crop_info=QLabel('영역 내부: 이동 · 모서리: 크기 조절');el.addWidget(self.crop_info)
        hint=QLabel('바깥/Shift+드래그: 새 영역 · Alt: 스냅 해제\n휠: 확대 · Space+드래그/가운데 버튼: 화면 이동\n방향키: 스냅 단위 이동 · Esc: 현재 드래그 취소');hint.setWordWrap(True);el.addWidget(hint)
        self.coords=[]
        for name in ('X','Y','너비','높이'):
            spin=QSpinBox();spin.setRange(0,100000);spin.setKeyboardTracking(False);spin.valueChanged.connect(self.coords_changed);self.coords.append(spin)
            el.addWidget(row(QLabel(name),spin))
        el.addWidget(button('크롭 적용',self.apply_crop,True))
        el.addStretch()
        resize_page=QWidget();el=QVBoxLayout(resize_page);self.edit_pages.addWidget(resize_page)
        el.addWidget(QLabel('출력 크기를 정하거나 작업본을 회전합니다.'))
        el.addWidget(button('90° 회전',self.rotate))
        el.addWidget(button('출력 규격 / 리사이즈',self.resize_current))
        el.addStretch()
        stitch_page=QWidget();el=QVBoxLayout(stitch_page);self.edit_pages.addWidget(stitch_page)
        el.addWidget(QLabel('크롭 → 외부 수정 → 스티치'))
        self.feather=QSpinBox();self.feather.setRange(0,512);self.feather.setValue(24)
        el.addWidget(row(QLabel('스티치 경계 부드러움 (px)'),self.feather))
        el.addWidget(button('스티치 마스크 그리기',self.edit_stitch_mask))
        el.addWidget(button('외부 수정본 불러와 합성',self.stitch))
        el.addWidget(button('저장된 크롭 작업 다시 열기',self.open_crop_record))
        el.addStretch()
        tone_page=QWidget();el=QVBoxLayout(tone_page);self.edit_pages.addWidget(tone_page)
        el.addWidget(QLabel('TONE RESTORE · 구도가 대응하는 기준 이미지'))
        self.tone_backend=QComboBox();self.tone_backend.addItem('CPU · 기본','cpu');self.tone_backend.addItem('CUDA GPU','cuda');el.addWidget(self.tone_backend)
        self.reference=QLineEdit();self.reference.setPlaceholderText('색·명암 기준 이미지');el.addWidget(row(self.reference,button('찾기',self.choose_reference)))
        self.strength=QDoubleSpinBox();self.strength.setRange(0,2);self.strength.setValue(.8);self.strength.setSingleStep(.1)
        self.levels=QSpinBox();self.levels.setRange(1,10);self.levels.setValue(5)
        el.addWidget(row(QLabel('강도'),self.strength,QLabel('단계'),self.levels))
        self.luminance=QCheckBox('명암만 복원 (대상 색차 유지)');el.addWidget(self.luminance)
        el.addWidget(row(button('톤 미리보기 / 비교',self.preview_tone),button('톤 복원 적용',self.restore_tone,True)));el.addStretch()
        color_page=QWidget();el=QVBoxLayout(color_page);self.edit_pages.addWidget(color_page)
        el.addWidget(QLabel('원본의 색상 정보를 해석해 별도 작업본으로 변환합니다.'))
        el.addWidget(button('ICC / HDR 원본 색상 정규화',self.normalize_color));el.addStretch()
        self.edit_tool.currentIndexChanged.connect(self.edit_pages.setCurrentIndex)
        def change_tool(index):
            if index!=0:self.crop_toggle.setChecked(False)
            self.workspace_mode.setCurrentIndex(1)
        self.edit_tool.currentIndexChanged.connect(change_tool)
        self.crop_toggle.toggled.connect(lambda on:self.workspace_mode.setCurrentIndex(1) if on else None)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(edit);self.tabs.addTab(scroll,'편집')
        metadata_panel=QWidget();ml=QVBoxLayout(metadata_panel)
        self.generation_settings=QPlainTextEdit();self.generation_settings.setReadOnly(True);self.generation_settings.setMaximumHeight(190)
        ml.addWidget(QLabel('파일에 기록된 생성 설정'));ml.addWidget(self.generation_settings)
        self.branch_choice=QComboBox();self.branch_choice.currentIndexChanged.connect(self.show_branch)
        ml.addWidget(self.branch_choice)
        self.branch_preview=QPlainTextEdit();self.branch_preview.setReadOnly(True);self.branch_preview.setMaximumHeight(170);ml.addWidget(self.branch_preview)
        ml.addWidget(button('선택 분기의 정적 텍스트를 작업 프롬프트로 복사',self.use_branch))
        self.raw=QPlainTextEdit();self.raw.setReadOnly(True);ml.addWidget(self.raw);self.tabs.addTab(metadata_panel,'메타정보')
        from .disk_browser import DiskBrowser
        self.disk_browser=DiskBrowser(self,Viewer);self.disk_browser.hide();outer.addWidget(self.disk_browser,1)
        self.build_main_tabs(outer)
        self.disk_browser.layout().insertWidget(2,button('이 이미지의 프롬프트를 노트에 저장…',lambda:self.save_image_to_note(True)))
        self.setCentralWidget(host)
        self.autosave=QTimer(self);self.autosave.setSingleShot(True);self.autosave.setInterval(600);self.autosave.timeout.connect(self.save_draft)
        for editor in (self.draft,self.draft_negative,self.memo): editor.textChanged.connect(lambda:self.autosave.start() if not self.loading else None)
        self.note_title.textChanged.connect(lambda:self.autosave.start() if not self.loading else None)
        self.note_category.currentTextChanged.connect(lambda:self.autosave.start() if not self.loading else None)
        for shortcut,fn in [('Ctrl+O',self.open_file),('Ctrl+Shift+V',self.paste),('Ctrl+S',lambda:self.save_note() if self.note_mode else self.save_draft())]:
            action=QAction(self);action.setShortcut(QKeySequence(shortcut));action.triggered.connect(fn);self.addAction(action)

    def safe(self,fn):
        try: return fn()
        except Exception as exc: self.error(str(exc))
    def error(self,message):
        QMessageBox.warning(self,'BMK AI Studio',message)
    def task(self,fn,callback):
        job=Job(fn);self.jobs.append(job)
        job.result.connect(lambda result:self.safe(lambda:callback(result)))
        job.failed.connect(self.error)
        job.finished.connect(lambda:self.jobs.remove(job))
        job.start()
        return job
    def require_image(self):
        if self.current is None:
            self.statusBar().showMessage('먼저 이미지를 열어주세요.');return False
        return True
    def load(self,path):
        if hasattr(self,'main_tabs') and self.main_tabs.currentIndex()==2:self.main_tabs.setCurrentIndex(1)
        # Validate before replacing the current session.
        def read_source():
            stamp=file_stamp(path);info=inspect_image(path);im=load_image(path);source_hash=fingerprint(path)
            if file_stamp(path)!=stamp:raise ValueError('읽는 중 이미지가 변경되었습니다. 다시 열어주세요.')
            return stamp,info,im,source_hash
        if high_precision(path):
            result=self.session_operation(read_source,'고정밀 원본과 SDR 미리보기를 읽고 있습니다…')
            if result is None:return False
            stamp,info,im,source_hash=result
        else:stamp,info,im,source_hash=read_source()
        if not self.confirm_image_change():return False
        self.save_draft()
        self.loading=True
        self.path=Path(path).resolve();self.info=info;self.original=im;self.current=im.copy()
        self.load_stamp=file_stamp(self.path)
        self.source_hash=source_hash
        self.store.remember_source(self.path,source_hash)
        self.rotation=0;self.box=None;self.crop_context=None;self.history=[];self.operations=[];self.scores=None;self.note_id=None;self.note_extra={};self.note_mode=False
        self.exported_state=''
        self.checkpoint_state=''
        self.note_category.setCurrentText('')
        self.positive.setPlainText(info['positive']);self.negative.setPlainText(info['negative']);self.source.setText(info['source'])
        self.raw.setPlainText(json_text({'characters':info['characters'],'workflow_candidates':info['candidates'],'metadata':info['raw']}))
        self.generation_settings.setPlainText(json_text({'출처':info['settings_origin'],'설정':info['settings'],'XMP':info['xmp'],'안내':info['warnings']}))
        self.branch_choice.clear();self.branch_choice.addItem('ComfyUI 샘플러 선택 — 실제 출력 분기 자동 확정 안 함',None)
        for branch in info['branches']:
            self.branch_choice.addItem(f"노드 {branch['node']} · {branch['type']}",branch)
        saved=self.store.asset(self.path)
        self.draft.setPlainText(saved[0] if saved else info['positive']);self.draft_negative.setPlainText(saved[1] if saved else info['negative']);self.memo.setPlainText(saved[2] if saved else '')
        self.note_title.setText(self.path.stem);self.loading=False
        self.select_document(0)
        restore_error=''
        if self.sessions.contains(self.path):
            restored=self.session_operation(lambda:self.sessions.load(self.path),'보관한 편집 작업을 읽고 있습니다…',quiet=True)
            if restored:
                self.current,state=restored;self.operations=state['operations'];self.crop_context=state.get('crop_context')
                self.rotation=state.get('rotation',0);self.box=state.get('box');self.exported_state=state.get('exported_state','')
                self.checkpoint_state=self.edit_state()
            else:restore_error='보관 작업 검증 실패: '+self.session_error
        if self.recovery.contains(self.path):
            recovered=self.session_operation(lambda:self.recovery.load(self.path),'자동 복구본을 확인하고 있습니다…',quiet=True)
            if recovered:
                self.current,state=recovered;self.operations=state['operations'];self.crop_context=state.get('crop_context')
                self.rotation=state.get('rotation',0);self.box=state.get('box');self.exported_state=state.get('exported_state','')
                self.recovery_saved[str(self.path)]=self.edit_state()
                self.source.setText('자동 복구본을 열었습니다. 확인 후 작업 보관 또는 내보내기하세요.')
            else:restore_error='자동 복구본 검증 실패: '+self.session_error
        self.viewer.display(self.current);self.set_box(self.box or (0,0,*self.current.size));self.render_tags()
        self.file_label.setText(f'{self.path.name}\n{im.width} × {im.height}  ·  {self.path.parent}')
        self.statusBar().showMessage('메타데이터 읽기 완료 · 작업 프롬프트 자동 저장')
        if restore_error:self.source.setText(restore_error+' · 원본 이미지만 열었습니다.')
        self.refresh_saved_tags()
        self.save_window_state()
        return True
    def show_branch(self):
        branch=self.branch_choice.currentData()
        self.branch_preview.setPlainText(json_text(branch) if branch else '')
    def use_branch(self):
        branch=self.branch_choice.currentData()
        if not branch:return
        # Unknown dynamic inputs must not silently replace a good work prompt.
        if branch['warnings'] or not (branch['positive'] or branch['negative']):
            self.error('이 분기에 동적/미지원 연결이 있습니다. 원문에서 텍스트를 확인해 복사하세요.');return
        self.draft.setPlainText('\n'.join(p['text'] for p in branch['positive']))
        self.draft_negative.setPlainText('\n'.join(p['text'] for p in branch['negative']))
        self.statusBar().showMessage('선택한 정적 텍스트를 작업 프롬프트로 복사했습니다. 원본 메타데이터는 유지됩니다.')
    def add_paths(self,paths,open_first=True,restore_hidden=True):
        self.index_cancelled=False
        accepted=[]
        for p in paths:
            p=Path(p)
            if p.suffix.lower() in EXTENSIONS and p.is_file():
                key=str(p.resolve())
                if key in self.removed_paths:
                    if not restore_hidden:continue
                    self.store.reveal_paths([key]);self.removed_paths.discard(key)
                accepted.append(key)
                if key not in self.library_items:
                    item=self.library.add_path(key,p.name);self.library_items[key]=item
                    self.searchable[key]=p.name.casefold()
        for key in accepted:
            try:
                if self.index_stamps.get(key)!=file_stamp(key):self.pending_index.add(key)
            except OSError:pass
        self.start_index()
        self.search_changed(self.search.text())
        if accepted and open_first:self.safe(lambda:self.load(accepted[0]))

    def restore_library(self):
        references=self.store.indexed_references()
        for item in self.library.add_references(references):self.library_items[item.path]=item
        self.index_stamps.update(references)
        self.library_status.setText(f'{self.library.count()}개 이미지 · 폴더 감시는 기본 꺼짐')
        if references:
            def changed():
                result=[]
                for path,stamp in references:
                    try:
                        if file_stamp(path)!=stamp:result.append(path)
                    except OSError:pass
                return result
            def refresh(paths):
                if not self.closing_requested:self.pending_index.update(path for path in paths if path not in self.removed_paths);self.start_index()
            self.task(changed,refresh)

    def start_index(self):
        if self.closing_requested or getattr(self,'index_cancelled',False) or self.index_job or not self.pending_index:return
        paths=list(self.pending_index)[:64];self.pending_index.difference_update(paths)
        self.indexing=set(paths)
        job=IndexJob(paths,self.store.root);self.index_job=job;self.jobs.append(job)
        job.indexed.connect(self.index_ready)
        job.failed_item.connect(self.index_failed)
        def finished():
            self.jobs.remove(job);self.index_job=None;self.indexing.clear()
            watching=' · 감시 중' if self.watch_toggle.isChecked() else ''
            self.library_status.setText(f'{self.library.count()}개 이미지 · 색인 대기 {len(self.pending_index)}개{watching}')
            self.start_index()
        job.finished.connect(finished);job.start()

    def index_failed(self,path,error):
        if path in self.removed_paths:return
        self.statusBar().showMessage(f'읽기 실패: {Path(path).name} · {error}')
        if self.closing_requested or getattr(self,'index_cancelled',False):return
        try:key=(path,file_stamp(path))
        except OSError:return
        attempts=self.index_retries.get(key,0)
        if attempts<2:
            self.index_retries[key]=attempts+1
            def retry():
                if not self.closing_requested and not getattr(self,'index_cancelled',False):self.pending_index.add(path);self.start_index()
            QTimer.singleShot(2000,retry)

    def index_ready(self,record):
        path,stamp,searchable,blob=record
        if path in self.removed_paths:return
        item=self.library_items.get(path)
        if item is None:
            item=self.library.add_path(path,Path(path).name);self.library_items[path]=item
        self.index_stamps[path]=stamp
        self.library.update_item(item,blob=blob);self.update_library_search(path)
        if self.path and path==str(self.path) and stamp!=self.load_stamp:
            self.source.setText('원본 파일이 변경되었습니다. 목록에서 다시 열어 새 내용을 확인하세요.')
            self.scores=None;self.render_tags()

    def open_folder_path(self,path):
        self.watch_toggle.setChecked(False);self.folder=str(Path(path).resolve())
        self.library_status.setText(self.folder);self.library_status.setToolTip(self.folder)
        # Directory listing itself runs off the UI thread.
        self.task(lambda:list(folder_snapshot(path)),lambda paths:self.add_paths(paths))

    def toggle_watch(self,on):
        if self.watch_job:
            self.watch_job.requestInterruption()
        if not on:return
        if not self.folder:
            self.watch_toggle.setChecked(False);self.statusBar().showMessage('먼저 감시할 이미지 폴더를 열어주세요.');return
        job=FolderWatch(self.folder);self.watch_job=job;self.jobs.append(job)
        job.discovered.connect(lambda paths:self.add_paths(paths,False,False) if self.watch_job is job and self.watch_toggle.isChecked() else None)
        job.failed.connect(lambda error:self.watch_error(job,error))
        def finished():
            self.jobs.remove(job)
            if self.watch_job is job:self.watch_job=None
        job.finished.connect(finished);job.start()
        self.library_status.setText('감시 중 · '+self.folder)

    def watch_error(self,job,error):
        if self.watch_job is job:
            self.watch_toggle.setChecked(False);self.library_status.setText('감시 중단: '+error)
    def open_file(self):
        paths,_=QFileDialog.getOpenFileNames(self,'이미지 열기','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.exr)');self.add_paths(paths)
    def open_folder(self):
        path=QFileDialog.getExistingDirectory(self,'이미지 폴더')
        if path:self.open_folder_path(path)
    def search_changed(self,text):
        if hasattr(self,'filter_summary'):self.apply_browser_filters()
    def update_library_search(self,path):
        if self.library.database:
            self.library.refresh_query();return
        item=self.library_items.get(str(path))
        if item is None:return
        extra=self.search_extra.get(str(path),{})
        tags=extra.get('tags','') if extra.get('stamp')==self.index_stamps.get(str(path)) else ''
        self.library.update_item(item,search='\n'.join((self.searchable.get(str(path),item.text()),extra.get('work',''),tags)))
    def remove_library_selection(self):
        self.remove_library_paths([item.path for item in self.library.selectedItems()])
    def remove_library_paths(self,paths):
        paths={str(p) for p in paths if str(p) in self.library_items}
        if not paths:return
        self.removal_history.append(paths);self.removal_history=self.removal_history[-20:];self.restore_removed_button.setEnabled(True)
        self.store.hide_paths(paths);self.removed_paths.update(paths);self.pending_index.difference_update(paths)
        self.library.remove_paths(paths)
        for path in paths:
            self.library_items.pop(path,None);self.searchable.pop(path,None);self.index_stamps.pop(path,None)
        self.statusBar().showMessage(f'{len(paths)}개 항목을 목록에서 제거했습니다. 원본·작업 텍스트는 유지되며 이미지/폴더 열기로 다시 추가할 수 있습니다.')
    def undo_library_removal(self):
        if not self.removal_history:return
        paths=self.removal_history.pop();self.restore_removed_button.setEnabled(bool(self.removal_history))
        self.store.reveal_paths(paths);self.removed_paths.difference_update(paths)
        # Restore references without navigation or changing the current search.
        self.add_paths(sorted(paths),False)
        missing=sum(not Path(path).is_file() for path in paths)
        self.statusBar().showMessage(f'목록 제거를 되돌렸습니다. 현재 검색은 유지됩니다.'+(f' 파일이 없는 {missing}개는 다시 표시할 수 없습니다.' if missing else ''))
    def refresh_notes(self,*args):
        scroll=self.notes.verticalScrollBar().value();selected=self.notes.currentItem();selected_id=selected.data(0,Qt.ItemDataRole.UserRole) if selected else self.note_id
        expanded={}
        def remember(parent,prefix=''):
            for n in range(parent.childCount()):
                item=parent.child(n);key=prefix+'/'+item.text(0)
                if not item.data(0,Qt.ItemDataRole.UserRole):expanded[key]=item.isExpanded();remember(item,key)
        remember(self.notes.invisibleRootItem())
        self.notes.clear()
        folders={}
        for record in self.store.note_entries(self.note_search.text(),self.show_archived.isChecked()):
            nid,title,body,category,archived=record
            parent=self.notes.invisibleRootItem();path=''
            for part in (category.split('/') if category else ['미분류']):
                path=path+'/'+part
                if path not in folders:
                    folder=QTreeWidgetItem([part]);parent.addChild(folder);folders[path]=folder;folder.setExpanded(expanded.get(path,True))
                parent=folders[path]
            item=QTreeWidgetItem([title]);item.setData(0,Qt.ItemDataRole.UserRole,nid);parent.addChild(item)
            if nid==selected_id:self.notes.setCurrentItem(item)
        self.notes.verticalScrollBar().setValue(scroll)
        current=self.note_category.currentText();self.note_category.blockSignals(True);self.note_category.clear()
        self.note_category.addItems(['']+sorted({r[3] for r in self.store.note_entries() if r[3]}));self.note_category.setCurrentText(current);self.note_category.blockSignals(False)
    def save_draft(self):
        self.autosave.stop()
        if self.path and not self.loading and not self.note_mode:
            self.store.save_asset(self.path,self.info,self.draft.toPlainText(),self.draft_negative.toPlainText(),self.memo.toPlainText())
            self.search_extra.setdefault(str(self.path),{})['work']='\n'.join((self.draft.toPlainText(),self.draft_negative.toPlainText(),self.memo.toPlainText()))
            self.update_library_search(str(self.path))
        if self.note_mode and not self.loading:
            if not self.note_id and not any((self.note_title.text().strip(),self.draft.toPlainText().strip(),self.draft_negative.toPlainText().strip(),self.memo.toPlainText().strip())) and not (set(self.note_extra)-{'schema','source','prompt','negative','notes'}):return
            title=self.note_title.text().strip() or '제목 없는 노트';body=self.note_body();category=normalize_category(self.note_category.currentText())
            record=self.store.note(self.note_id) if self.note_id else None
            if record is None or (record[1],json.loads(record[2]),record[3])!=(title,body,category):
                self.note_id=self.store.save_note(title,body,self.note_id,category);self.refresh_notes()
            if self.document_index > 0:
                self.note_tabs.setTabData(self.document_index,{'id':self.note_id})
                self.note_tabs.setTabText(self.document_index,title)
        if not self.loading:self.save_documents()
    def note_body(self):
        return {**self.note_extra,'schema':self.note_extra.get('schema',1),'prompt':self.draft.toPlainText(),'negative':self.draft_negative.toPlainText(),'notes':self.memo.toPlainText(),'source':self.note_extra.get('source',str(self.path) if self.path else None)}
    def save_note(self):
        self.save_draft()
        title=self.note_title.text().strip() or '제목 없는 노트'
        self.note_id=self.store.save_note(title,self.note_body(),self.note_id,self.note_category.currentText());self.note_mode=True;self.refresh_notes();self.save_draft();self.statusBar().showMessage('노트와 버전 이력을 저장했습니다.')
        self.attach_note_tab(self.note_id,title)
        if hasattr(self,'main_tabs') and not self.main_switching:self.main_tabs.setCurrentIndex(2)
    def select_document(self,index):
        self.note_tabs.blockSignals(True);self.note_tabs.setCurrentIndex(index);self.note_tabs.blockSignals(False);self.document_index=index
        self.save_documents()
    def save_documents(self):
        if self.restoring_documents:return
        ids=[self.note_tabs.tabData(i).get('id') for i in range(1,self.note_tabs.count())]
        self.store.state('documents',{'ids':[nid for nid in ids if nid],'active':self.note_id if self.note_mode else None})
    def restore_documents(self):
        state=self.store.state('documents')
        if not isinstance(state,dict) or not isinstance(state.get('ids'),list):return
        for nid in state['ids']:
            if not isinstance(nid,str):continue
            record=self.store.note(nid)
            if record:self.attach_note_tab(nid,record[1])
        self.select_document(0)
        if isinstance(state.get('active'),str) and self.store.note(state['active']):self.open_note_id(state['active'])
    def attach_note_tab(self,nid,title):
        for index in range(1,self.note_tabs.count()):
            if self.note_tabs.tabData(index).get('id')==nid and nid:
                self.select_document(index);self.note_tabs.setTabText(index,title);return
        self.note_tabs.blockSignals(True);index=self.note_tabs.addTab(title);self.note_tabs.setTabData(index,{'id':nid});self.note_tabs.blockSignals(False)
        self.select_document(index)
    def activate_document(self,index,save=True):
        if index<0:return
        if save:self.save_draft()
        if index:
            data=self.note_tabs.tabData(index) or {}
            if data.get('id'):
                self.open_note_id(data['id'],save=False);return
            self.loading=True;self.note_id=None;self.note_extra={'source':None};self.note_mode=True
            self.note_title.clear();self.note_category.setCurrentText('');self.draft.clear();self.draft_negative.clear();self.memo.clear()
            self.loading=False;self.select_document(index);return
        self.loading=True;self.note_mode=False;self.note_id=None;self.note_extra={}
        saved=self.store.asset(self.path) if self.path else None
        self.note_title.setText(self.path.stem if self.path else '');self.note_category.setCurrentText('')
        self.draft.setPlainText(saved[0] if saved else (self.info['positive'] if self.info else ''))
        self.draft_negative.setPlainText(saved[1] if saved else (self.info['negative'] if self.info else ''));self.memo.setPlainText(saved[2] if saved else '')
        self.loading=False;self.select_document(0)
    def close_document(self,index):
        if index==0:return
        self.save_draft()
        active=self.document_index
        self.note_tabs.blockSignals(True);self.note_tabs.removeTab(index);self.note_tabs.blockSignals(False)
        if active==index:
            self.note_mode=False;self.document_index=0;self.activate_document(0,save=False)
        else:self.select_document(active-1 if index<active else active)
        if hasattr(self,'main_tabs') and self.main_tabs.currentIndex()==2 and not self.note_mode:
            if self.note_tabs.count()>1:self.activate_document(min(index,self.note_tabs.count()-1))
            else:self.new_note()
    def open_note(self,item,*args):
        nid=item.data(0,Qt.ItemDataRole.UserRole)
        if nid:self.open_note_id(nid)
    def open_note_id(self,nid,save=True):
        if save:self.save_draft()
        self.loading=True
        record=self.store.note(nid)
        if not record:self.loading=False;return
        self.note_id=record[0];doc=json.loads(record[2]);self.note_mode=True
        self.note_extra=doc.copy()
        self.note_title.setText(record[1]);self.note_category.setCurrentText(record[3]);self.draft.setPlainText(doc.get('prompt',''));self.draft_negative.setPlainText(doc.get('negative',''));self.memo.setPlainText(doc.get('notes',''))
        self.loading=False;self.tabs.setCurrentIndex(1)
        self.attach_note_tab(nid,record[1])
        if hasattr(self,'main_tabs') and not self.main_switching:self.main_tabs.setCurrentIndex(2)
    def new_note(self):
        self.save_draft();self.loading=True;self.note_id=None;self.note_extra={'source':None};self.note_mode=True
        self.note_title.clear();self.draft.clear();self.draft_negative.clear();self.memo.clear()
        self.note_category.setCurrentText('');self.attach_note_tab(None,'새 노트')
        self.loading=False;self.tabs.setCurrentIndex(1);self.note_title.setFocus()
        if hasattr(self,'main_tabs') and not self.main_switching:self.main_tabs.setCurrentIndex(2)
    def note_history(self):
        self.save_draft()
        if not self.note_id:self.statusBar().showMessage('먼저 노트를 저장하거나 목록에서 선택하세요.');return
        dialog=RevisionDialog(self.store.revisions(self.note_id),self)
        if dialog.exec()==QDialog.DialogCode.Accepted and dialog.revision_id is not None:self.restore_note_version(dialog.revision_id)
    def restore_note_version(self,revision_id):
        self.save_draft();nid=self.note_id
        self.store.restore_revision(nid,revision_id)
        # Avoid saving the obsolete editor over the restored record on navigation.
        self.open_note_id(nid,save=False);self.refresh_notes();self.statusBar().showMessage('선택 버전을 새 이력으로 복원했습니다.')
    def archive_current_note(self):
        self.save_draft()
        if not self.note_id:self.statusBar().showMessage('먼저 노트를 선택하세요.');return
        record=self.store.note(self.note_id);self.store.archive_note(self.note_id,not record[4]);self.refresh_notes()
        self.statusBar().showMessage('노트를 복구했습니다.' if record[4] else '노트를 보관함으로 옮겼습니다. 내용과 이력은 유지됩니다.')
    def import_notes(self):
        paths,_=QFileDialog.getOpenFileNames(self,'BMK 노트 JSON 가져오기','','JSON (*.json)')
        if paths:self.import_note_paths(paths)
    def import_note_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'노트 JSON 폴더 (하위 폴더 포함)')
        if folder:self.import_note_paths(None,folder)
    def import_note_paths(self,paths,folder=None):
        root=self.store.root
        def work():
            store=Store(root)
            try:return store.import_note_files(paths if paths is not None else sorted(Path(folder).rglob('*.json')),folder)
            finally:store.db.close()
        def done(report):
            self.refresh_notes();self.statusBar().showMessage(f"노트 가져오기: {len(report['imported'])}개 성공 / {len(report['failed'])}개 실패")
            if report['failed']:self.error(json_text(report['failed']))
        self.task(work,done)
    def edit_note_fields(self):
        if not self.note_mode:
            self.statusBar().showMessage('추가 필드는 노트를 열거나 새 노트를 만든 뒤 편집하세요.');return
        dialog=NoteFieldsDialog(self.note_body(),self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.note_extra=dialog.result;self.save_draft();self.statusBar().showMessage('BMK 추가 필드를 저장했습니다. 미지원 키는 유지됩니다.')
    def edit_note_json(self):
        dialog=QDialog(self);dialog.setWindowTitle('전체 노트 JSON · 미지원 필드도 보존');dialog.resize(720,650)
        layout=QVBoxLayout(dialog);editor=QPlainTextEdit(json_text(self.note_body()));layout.addWidget(editor)
        layout.addWidget(QLabel('prompt / negative / notes는 문자열입니다. LoRA·params·ui 등 다른 필드는 JSON으로 보관합니다.'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('적용');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        def apply():
            try:doc=validate_note(json.loads(editor.toPlainText()))
            except Exception as exc:QMessageBox.warning(dialog,'JSON 확인',str(exc));return
            self.note_extra=doc.copy();self.draft.setPlainText(doc.get('prompt',''));self.draft_negative.setPlainText(doc.get('negative',''));self.memo.setPlainText(doc.get('notes',''))
            self.save_draft();dialog.accept()
        buttons.accepted.connect(apply);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()
    def export_note(self):
        path,_=QFileDialog.getSaveFileName(self,'노트 내보내기',str(self.store.root/'note.json'),'JSON (*.json)')
        if path:self.safe(lambda:Path(path).write_text(json_text({**self.note_body(),'_studio_category':normalize_category(self.note_category.currentText())}),encoding='utf-8'))
    def copy_text(self,text):
        QApplication.clipboard().setText(text);self.statusBar().showMessage('텍스트를 복사했습니다.')
    def copy_image(self):
        if self.require_image():QApplication.clipboard().setImage(ImageQt(self.current).copy());self.statusBar().showMessage('작업 이미지 픽셀을 복사했습니다. 원본 메타데이터는 파일 복사를 사용하세요.')
    def copy_file(self):
        if self.path:
            mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.path))]);QApplication.clipboard().setMimeData(mime);self.statusBar().showMessage('원본 파일을 복사했습니다.')
    def paste(self):
        mime=QApplication.clipboard().mimeData()
        if mime.hasUrls():self.add_paths([u.toLocalFile() for u in mime.urls()])
        elif mime.hasImage():
            path=unique_path(self.store.root/'clipboard',datetime.now().strftime('%Y%m%d-%H%M%S'))
            if QApplication.clipboard().image().save(str(path),'PNG'):self.add_paths([path])
        elif mime.hasText():self.draft.insertPlainText(mime.text());self.tabs.setCurrentIndex(1)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def dropEvent(self,event):
        paths=[]
        for url in event.mimeData().urls():
            p=Path(url.toLocalFile())
            if p.is_dir():self.open_folder_path(p)
            else:paths.append(p)
        self.add_paths(paths);event.acceptProposedAction()
    def use_original(self):
        self.draft.setPlainText(self.positive.toPlainText());self.draft_negative.setPlainText(self.negative.toPlainText());self.tabs.setCurrentIndex(1)
    def convert(self):
        def work():
            converter=BMKPromptSyntaxConverter();mode=self.conversion.currentText()
            for editor in (self.draft,self.draft_negative):replace_text(editor,converter.convert(editor.toPlainText(),mode,1.5,False)[0])
        self.safe(work)
    def expand_work_wildcards(self):
        token=(self.path,self.note_id,self.document_index)
        dialog=WildcardDialog(self.store.root/'wildcards',self.draft.toPlainText(),self.draft_negative.toPlainText(),self)
        if dialog.exec()==QDialog.DialogCode.Accepted and dialog.result is not None and token==(self.path,self.note_id,self.document_index):
            editor=self.draft if dialog.target.currentIndex()==0 else self.draft_negative
            replace_text(editor,dialog.result);self.save_draft()
            self.statusBar().showMessage(f'와일드카드 {len(dialog.used)}개 적용 · 시드 {dialog.seed.value()} · Ctrl+Z로 되돌리기')
    def dedupe(self):
        # Restrict to literal comma-separated tags; don't rewrite nested weight groups.
        text=self.draft.toPlainText()
        if any(c in text for c in '(){}[]') or '::' in text:
            self.statusBar().showMessage('중복 정리는 가중치 문법이 없는 평문 태그에만 적용합니다.');return
        seen=set();lines=[]
        for line in text.splitlines():
            keep=[]
            for tag in line.split(','):
                key=tag.strip()
                if key and key not in seen:keep.append(key);seen.add(key)
            lines.append(', '.join(keep))
        replace_text(self.draft,'\n'.join(lines))
    def download_model(self):
        if self.tag_busy:self.statusBar().showMessage('현재 태깅이 끝난 뒤 모델을 변경하세요.');return
        dialog=ModelDownloadDialog(self.store.root/'models',self)
        if dialog.exec()==QDialog.DialogCode.Accepted and dialog.installed:
            self.model_path.setText(dialog.installed);self.settings.setValue('model_path',dialog.installed)
    def choose_model(self):
        path=QFileDialog.getExistingDirectory(self,'WD v3 모델 폴더 선택',self.model_path.text())
        if path:self.model_path.setText(path);self.settings.setValue('model_path',path)
    def run_tags(self):
        if not self.require_image() or self.tag_busy:return
        self.start_tags([str(self.path)])
    def run_selected_tags(self):
        paths=[i.data(Qt.ItemDataRole.UserRole) for i in self.library.selectedItems() if not i.isHidden()]
        if not paths:self.statusBar().showMessage('왼쪽 목록에서 Ctrl / Shift로 처리할 이미지를 선택하세요.');return
        self.start_tags(paths)
    def save_queue(self):
        self.store.state('tag_queue',{'active':self.queue_active,'pending':self.tag_queue})
        if self.queue_dialog:self.queue_dialog.refresh()
    def enqueue_selected(self):
        paths=[item.path for item in self.library.selectedItems() if not item.isHidden()]
        known=set(self.tag_queue+self.queue_active)
        for path in paths:
            if path not in known:self.tag_queue.append(path);known.add(path)
        self.save_queue();self.statusBar().showMessage(f'대기열 {len(self.tag_queue)}개 · 대기열 관리에서 실행하세요.')
    def open_queue(self):
        if self.queue_dialog is None:self.queue_dialog=QueueDialog(self)
        self.queue_dialog.refresh();self.queue_dialog.show();self.queue_dialog.raise_()
    def run_queue(self):
        if self.tag_busy or not self.tag_queue:return
        if not self.model_path.text().strip():self.error('먼저 모델 폴더를 선택하세요.');return
        self.queue_running=True;self.process_queue()
    def pause_queue(self):
        self.queue_running=False;self.save_queue()
    def process_queue(self):
        if self.closing_requested or not self.queue_running or self.tag_busy:return
        if not self.tag_queue:self.queue_running=False;self.save_queue();return
        if not self.model_path.text().strip():self.queue_running=False;self.save_queue();self.statusBar().showMessage('모델 경로가 없어 대기열을 정지했습니다.');return
        self.queue_active=self.tag_queue[:self.batch_size.value()];del self.tag_queue[:len(self.queue_active)];self.save_queue()
        self.start_tags(list(self.queue_active),queued=True)
    def start_tags(self,paths,queued=False):
        if self.tag_busy:return
        if self.queue_running and not queued:self.statusBar().showMessage('대기열을 일시 정지한 뒤 직접 태깅하세요.');return
        model=self.model_path.text().strip()
        if not model:self.error('WD v3 모델 폴더를 선택하세요.');return
        self.tag_busy=True;self.tag_button.setEnabled(False);self.batch_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.tagger.precision=self.precision.currentData();self.precision.setEnabled(False)
        self.model_path.setEnabled(False);self.batch_size.setEnabled(False)
        self.tag_progress.setRange(0,len(paths));self.tag_progress.setValue(0);self.job_log.clear()
        self.tag_status.setText(f'{len(paths)}개 이미지 · 모델 로딩 / 캐시 확인 중…')
        job=BatchTagJob(paths,model,self.tagger,self.store.root,self.batch_size.value());self.batch_job=job;self.jobs.append(job)
        processed=set()
        if queued:
            job.item_ready.connect(lambda payload:processed.add(payload['path']))
            job.item_failed.connect(lambda path,error:processed.add(path))
        job.item_ready.connect(self.tags_ready)
        job.item_failed.connect(lambda path,error:self.job_log.appendPlainText(f'실패 · {Path(path).name}: {error}'))
        job.progress.connect(lambda done,total:self.tag_progress.setValue(done))
        job.summary.connect(self.tags_summary)
        def finished():
            self.jobs.remove(job);self.batch_job=None;self.tag_finished()
            if queued:
                remaining=[path for path in self.queue_active if path not in processed]
                self.tag_queue=remaining+[path for path in self.tag_queue if path not in remaining];self.queue_active=[]
                if job.stats.get('cancelled') or job.stats.get('fatal'):self.queue_running=False
                self.save_queue()
                if self.queue_running:QTimer.singleShot(0,self.process_queue)
        job.finished.connect(finished);job.start()
    def tags_ready(self,payload):
        self.job_log.appendPlainText(('캐시' if payload['cached'] else '완료')+' · '+Path(payload['path']).name)
        self.search_extra.setdefault(payload['path'],{}).update({'tags':searchable_tags(payload['result']),'stamp':payload['stamp']})
        self.update_library_search(payload['path'])
        if self.path and str(self.path)==payload['path']:
            try:
                if (payload['stamp']==self.load_stamp==file_stamp(self.path)
                        and payload['model_signature']==inference_signature(self.model_path.text(),self.precision.currentData())):
                    self.scores=payload['result'];self.render_tags()
            except OSError:pass
    def tags_summary(self,summary):
        self.last_batch_summary=summary
        label='취소됨' if summary['cancelled'] else ('작업 오류' if summary.get('fatal') else '완료')
        self.tag_status.setText(f"{label} · 저장 {summary['completed']} / {summary['total']} · 캐시 {summary['cached']} · 실패 {summary['failed']}")
    def cancel_tags(self):
        self.queue_running=False
        if self.batch_job:
            self.batch_job.cancel();self.cancel_button.setEnabled(False)
            self.tag_status.setText('취소 요청됨 · 현재 추론 배치가 끝나면 정지합니다. 완료 결과는 유지됩니다.')
    def refresh_saved_tags(self,*args):
        self.scores=None
        if self.path:
            try:
                stamp=file_stamp(self.path)
                if stamp==self.load_stamp:self.scores=self.store.saved_tags(self.path,inference_signature(self.model_path.text(),self.precision.currentData()),stamp)
            except OSError:pass
        self.render_tags()
    def export_tags(self):
        if not self.scores:self.statusBar().showMessage('현재 이미지의 태깅 결과가 없습니다.');return
        target=unique_path(self.store.root/'exports',self.path.stem+'_tags','.json')
        path,_=QFileDialog.getSaveFileName(self,'추정 태그 내보내기',str(target),'JSON (*.json)')
        if path:self.safe(lambda:Path(path).write_text(json_text({'kind':'inferred_tags','source':str(self.path),'model':self.scores['model'],'threshold':self.threshold.value(),'character_threshold':self.char_threshold.value(),'selected_text':self.tag_text(),'prediction':self.scores}),encoding='utf-8'))
    def tag_finished(self):
        self.tag_busy=False;self.tag_button.setEnabled(True);self.batch_button.setEnabled(True);self.cancel_button.setEnabled(False)
        self.precision.setEnabled(True)
        self.model_path.setEnabled(True);self.batch_size.setEnabled(True)
    def unload_tagger(self):
        if self.tag_busy:self.statusBar().showMessage('태깅이 끝난 뒤 해제할 수 있습니다.');return
        if self.tagger.loaded:
            import torch
            self.tagger.model.to('cpu');del self.tagger.model;self.tagger.loaded=None
            if torch.cuda.is_available():torch.cuda.empty_cache()
        self.tag_status.setText('태깅 모델 메모리를 해제했습니다. 점수 캐시는 유지됩니다.')
    def render_tags(self,*args):
        self.tag_list.clear()
        if not self.scores:return
        exclude={s.strip().replace('_',' ').casefold() for s in self.exclude.text().split(',')}
        for item in sorted(self.scores['scores'],key=lambda s:s['score'],reverse=True):
            tag=item['tag'].replace('_',' ');threshold=self.char_threshold.value() if item['category']==4 else self.threshold.value()
            if item['category']==9 or item['score']<threshold or tag.casefold() in exclude:continue
            entry=QListWidgetItem(f"{item['score']:.3f}  {tag}");entry.setData(Qt.ItemDataRole.UserRole,tag);self.tag_list.addItem(entry)
    def tag_text(self,selected=False):
        items=self.tag_list.selectedItems() if selected else [self.tag_list.item(i) for i in range(self.tag_list.count())]
        return ', '.join(i.data(Qt.ItemDataRole.UserRole) for i in items)
    def append_tags(self):
        text=self.tag_text(True)
        if text:self.draft.appendPlainText(text);self.tabs.setCurrentIndex(1)
    def show_original(self):
        if self.original:self.viewer.display(self.original);self.crop_toggle.setChecked(False)
    def show_current(self):
        if self.current:
            self.viewer.display(self.current)
            if self.box:self.viewer.set_crop_box(self.box)
    def compare_images(self):
        if self.require_image():CompareDialog(self.original,self.current,self).exec()
    def resize_current(self):
        if not self.require_image():return
        token=self.current;dialog=ResizeDialog(self.current,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted or self.current is not token:return
        width,height,mode,bg=dialog.settings()
        def done(image):
            if self.current is token and not self.closing_requested:
                self.push();self.current=image;self.operations.append({'resize':[width,height],'mode':mode,'background':bg});self.viewer.display(image);self.set_box((0,0,*image.size))
        self.task(lambda:resize_image(token,width,height,mode,bg),done)
    def push(self):
        self.history.append((self.current.copy(),self.rotation,self.box,self.crop_context, list(self.operations)))
        self.history=self.history[-5:]
    def undo(self):
        if self.history:
            self.current,self.rotation,self.box,self.crop_context,self.operations=self.history.pop();self.viewer.display(self.current)
            if self.box:self.set_box(self.box)
            if not self.image_dirty():self.discard_recovery(self.path)
    def toggle_crop(self,on):
        if on and self.current:
            self.viewer.display(self.current,fit=False)
            box=self.box or (0,0,*self.current.size)
            self.viewer.set_crop_box(box if tuple(box)!=(0,0,*self.current.size) else None)
        self.viewer.crop_mode=on;self.viewer.crop_drag=None;self.viewer.crop_pan=None
        self.viewer.setDragMode(QGraphicsView.DragMode.NoDrag if on else QGraphicsView.DragMode.ScrollHandDrag)
        self.viewer.viewport().unsetCursor();self.viewer.viewport().update()
    def new_crop_selection(self):
        if not self.require_image():return
        self.crop_toggle.setChecked(True);self.set_box((0,0,*self.current.size));self.viewer.set_crop_box(None)
        self.viewer.setFocus();self.crop_info.setText('드래그로 새 영역 지정 · Shift+드래그도 가능')
    def change_crop_snap(self):
        step=self.crop_snap.currentData() or 1;self.viewer.crop_snap=step
        for spin in self.coords:spin.setSingleStep(step)
        if hasattr(self,'appearance'):
            self.appearance['crop_snap']=step;self.store.state('appearance',self.appearance)
    def set_ratio(self,text):
        self.viewer.ratio=0 if text=='자유' else float(text.split(':')[0])/float(text.split(':')[1])
        if self.current and self.box and self.viewer.ratio:
            x,y,w,h=self.box
            self.set_box(anchored_box((x,y),(x+w,y+h),self.current.size,self.viewer.ratio))
    def set_box(self,box):
        self.box=bounded_box(box,self.current.size) if self.current else tuple(box)
        for spin,value in zip(self.coords,self.box):spin.blockSignals(True);spin.setValue(value);spin.blockSignals(False)
        self.viewer.set_crop_box(self.box)
        x,y,w,h=self.box;self.crop_info.setText(f'{w} × {h} px · X {x} / Y {y}')
    def coords_changed(self):
        if not self.current:return
        box=list(s.value() for s in self.coords);sender=self.sender()
        index=self.coords.index(sender) if sender in self.coords else 2
        box[index]=snap_value(box[index],self.viewer.crop_snap)
        x,y,w,h=bounded_box(box,self.current.size)
        if self.viewer.ratio and index in (2,3):
            if index==2:h=w/self.viewer.ratio
            else:w=h*self.viewer.ratio
            x,y,w,h=anchored_box((x,y),(x+w,y+h),self.current.size,self.viewer.ratio)
        self.set_box((x,y,w,h))
    def rotate(self):
        if self.require_image():
            self.push();self.current=self.current.rotate(-90,expand=True);self.rotation=(self.rotation+90)%360;self.operations.append({'rotate':90});self.viewer.display(self.current);self.set_box((0,0,*self.current.size))
    def apply_crop(self):
        if not self.require_image():return
        def work():
            result=crop_image(self.current,self.box)
            self.push()
            # Persist the precise pre-crop working image, including earlier edits.
            basepath=unique_path(self.store.root/'crop_sources',datetime.now().strftime('%Y%m%d-%H%M%S'))
            self.current.save(basepath)
            self.crop_context={'base':str(basepath),'base_hash':fingerprint(basepath),'box':list(self.box),'rotation':0,'source':str(self.path)}
            self.current=result;self.operations.append({'crop':self.crop_context});self.rotation=0;self.viewer.display(result);self.set_box((0,0,*result.size));self.crop_toggle.setChecked(False)
            self.statusBar().showMessage('크롭 적용 완료. 내보내기 후 외부 수정본을 불러와 합성할 수 있습니다.')
        self.safe(work)
    def open_crop_record(self):
        path,_=QFileDialog.getOpenFileName(self,'크롭 작업 기록 열기','','BMK JSON (*.bmk.json)')
        if not path:return
        def work():
            record=json.loads(Path(path).read_text(encoding='utf-8'));ctx=record.get('crop_context')
            if not ctx:raise ValueError('크롭 좌표가 없는 기록입니다.')
            base=Path(ctx['base'])
            if fingerprint(base)!=ctx['base_hash']:raise ValueError('크롭 원본 파일이 변경되었습니다.')
            if self.load(base) is False:return
            self.crop_context=ctx;self.statusBar().showMessage('크롭 작업을 복원했습니다. 외부 수정본을 불러오세요.')
        self.safe(work)
    def edit_stitch_mask(self):
        if not self.crop_context:self.error('먼저 크롭을 적용하거나 크롭 작업 기록을 여세요.');return
        ctx=self.crop_context
        def work():
            if fingerprint(ctx['base'])!=ctx['base_hash']:raise ValueError('크롭 원본이 변경되었습니다.')
            region=crop_image(load_image(ctx['base']),ctx['box'],ctx['rotation'])
            mask=None
            if ctx.get('mask'):
                if fingerprint(ctx['mask'])!=ctx['mask_hash']:raise ValueError('저장된 마스크 파일이 변경되었습니다.')
                with Image.open(ctx['mask']) as saved:mask=saved.convert('L')
            dialog=MaskDialog(region,mask,self)
            if dialog.exec()==QDialog.DialogCode.Accepted and self.crop_context is ctx:
                path=unique_path(self.store.root/'masks',datetime.now().strftime('%Y%m%d-%H%M%S'))
                dialog.canvas.result().save(path);self.push()
                self.crop_context={**ctx,'mask':str(path),'mask_hash':fingerprint(path)}
                self.operations.append({'mask':str(path)})
                self.statusBar().showMessage('스티치 마스크를 저장했습니다. 외부 수정본 합성 시 적용됩니다.')
        self.safe(work)
    def stitch(self):
        if not self.crop_context:self.error('먼저 크롭을 적용하거나 저장된 크롭 작업을 여세요.');return
        path,_=QFileDialog.getOpenFileName(self,'외부 수정 결과 선택','','Images (*.png *.jpg *.jpeg *.webp)')
        if not path:return
        ctx=dict(self.crop_context);token=self.current
        def prepare():
            if fingerprint(ctx['base'])!=ctx['base_hash']:raise ValueError('크롭 원본 파일이 변경되었습니다.')
            mask=None
            if ctx.get('mask'):
                if fingerprint(ctx['mask'])!=ctx['mask_hash']:raise ValueError('저장된 마스크 파일이 변경되었습니다.')
                with Image.open(ctx['mask']) as im:mask=im.convert('L')
            return load_image(ctx['base']),load_image(path),mask
        prepared=self.session_operation(prepare,'스티치 이미지와 마스크를 확인하고 있습니다…')
        if prepared is None:return
        base,patch,mask=prepared;dialog=StitchDialog(base,patch,mask,ctx,self.feather.value(),self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        dx,dy,angle,scale,feather=dialog.settings()
        def compute():
            if fingerprint(ctx['base'])!=ctx['base_hash']:raise ValueError('미리보기 중 크롭 원본이 변경되었습니다.')
            if ctx.get('mask') and fingerprint(ctx['mask'])!=ctx['mask_hash']:raise ValueError('미리보기 중 마스크가 변경되었습니다.')
            return stitch_image(base,patch,ctx['box'],ctx['rotation'],feather,mask,(dx,dy),angle,scale)
        def done(result):
            if self.current is token and self.crop_context==ctx and not self.closing_requested:
                self.push();self.current=result;self.operations.append({'stitch':path,'context':ctx,'offset':[dx,dy],'angle':angle,'scale':scale,'feather':feather})
                self.crop_context=None;self.viewer.display(result);self.set_box((0,0,*result.size))
        self.task(compute,done)
    def choose_reference(self):
        path,_=QFileDialog.getOpenFileName(self,'톤 기준 이미지','','Images (*.png *.jpg *.jpeg *.webp)')
        if path:self.reference.setText(path)
    def normalize_color(self):
        if not self.require_image():return
        token=self.current;path=self.path;source_hash=self.source_hash
        dialog=QDialog(self);dialog.setWindowTitle('원본 색상 정규화');layout=QFormLayout(dialog)
        text=QLabel('원본을 다시 읽어 8비트 sRGB 작업본을 만듭니다. 현재 편집은 실행 취소로 돌아갈 수 있습니다.\nHDR 출력/모니터 제어가 아닌 SDR 변환입니다. 입력 색 공간을 확인하고 선택하세요.');text.setWordWrap(True);layout.addRow(text)
        mode=QComboBox();mode.addItem('내장 ICC → sRGB','icc');mode.addItem('고정밀 / 직접 입력 해석','hdr');layout.addRow('변환',mode)
        encoding=QComboBox();encoding.addItem('선형 RGB · sRGB 원색','linear');encoding.addItem('sRGB 감마 RGB','srgb');layout.addRow('입력 해석',encoding)
        exposure=QDoubleSpinBox();exposure.setRange(-16,16);exposure.setSuffix(' EV');layout.addRow('노출',exposure)
        tone=QComboBox();tone.addItem('명암 기반 Reinhard','reinhard');tone.addItem('0~1 범위로 자르기','clip');layout.addRow('HDR → SDR',tone)
        premult=QCheckBox('입력이 알파 사전 곱 RGB');layout.addRow(premult)
        def mode_changed():
            enabled=mode.currentData()=='hdr'
            for widget in (encoding,exposure,tone,premult):widget.setEnabled(enabled)
        mode.currentIndexChanged.connect(mode_changed)
        if high_precision(path):
            mode.setCurrentIndex(1)
            if path.suffix.lower()=='.png':encoding.setCurrentIndex(1);tone.setCurrentIndex(1)
        mode_changed()
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addRow(controls)
        controls.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept);controls.rejected.connect(dialog.reject)
        if dialog.exec()!=QDialog.DialogCode.Accepted or self.current is not token:return
        options={'mode':mode.currentData(),'encoding':encoding.currentData(),'exposure':exposure.value(),'tone_map':tone.currentData(),'premultiplied':premult.isChecked()}
        def work():
            if fingerprint(path)!=source_hash:raise ValueError('원본이 변경되어 색상 변환을 중단했습니다.')
            result=normalize_source(path,**options)
            if fingerprint(path)!=source_hash:raise ValueError('변환 중 원본이 변경되었습니다.')
            return result
        def done(result):
            if self.current is not token or self.path!=path or self.closing_requested:return
            image,record=result;self.push();self.current=image;self.rotation=0;self.crop_context=None
            self.operations=[{'color_normalization':record}];self.viewer.display(image);self.set_box((0,0,*image.size))
            self.statusBar().showMessage('sRGB 작업본으로 정규화했습니다. 원본 파일은 유지됩니다.')
        self.task(work,done)
    def preview_tone(self):
        if not self.require_image():return
        ref=self.reference.text().strip()
        if not ref:self.error('기준 이미지를 선택하세요.');return
        token=self.current
        def work():
            dialog=ToneDialog(token,load_image(ref),self.strength.value(),self.levels.value(),self.luminance.isChecked(),self)
            if dialog.exec()==QDialog.DialogCode.Accepted and self.current is token:
                self.strength.setValue(dialog.strength.value()/100);self.restore_tone()
        self.safe(work)
    def restore_tone(self):
        if not self.require_image():return
        ref=self.reference.text().strip()
        if not ref:self.error('기준 이미지를 선택하세요.');return
        content=self.current.copy();token=self.current;strength=self.strength.value();levels=self.levels.value();lum=self.luminance.isChecked()
        backend=self.tone_backend.currentData()
        self.statusBar().showMessage('톤 복원 계산 중… 다른 이미지로 이동하면 결과를 적용하지 않습니다.')
        def done(result):
            if self.current is token and not self.closing_requested:
                self.push();self.current=result;self.operations.append({'tone':ref,'strength':strength,'levels':levels,'luminance':lum,'backend':backend});self.viewer.display(result);self.statusBar().showMessage('톤 복원을 적용했습니다. 원본 보기 / 실행 취소로 비교할 수 있습니다.')
        restore=tone_restore_cuda if backend=='cuda' else tone_restore
        self.task(lambda:restore(content,load_image(ref),strength,levels,lum),done)
    def export_image(self):
        if not self.require_image():return False
        stem=self.safe(lambda:export_stem(self.appearance.get('export_pattern','{source}_edited'),self.path or 'image.png',self.current.size,self.note_title.text()))
        if stem is None:return False
        proposed=unique_path(self.store.root/'exports',stem)
        path,_=QFileDialog.getSaveFileName(self,'PNG 작업본 내보내기',str(proposed),'PNG (*.png)')
        if path:
            def work():
                record={'schema':1,'source':str(self.path),'original_metadata':self.info,'work':self.note_body(),'crop_context':self.crop_context,'operations':self.operations}
                saved=save_derived(self.current,Path(path).with_suffix('.png'),record)
                self.exported_state=self.edit_state()
                self.discard_recovery(self.path)
                self.statusBar().showMessage(f'저장 완료: {saved} · 기록: .bmk.json')
                return True
            return bool(self.safe(work))
        return False
    def edit_state(self):return json_text({'operations':self.operations,'crop_context':self.crop_context})
    def image_dirty(self):return bool(self.operations) and self.edit_state() not in (self.exported_state,self.checkpoint_state)
    def checkpoint_payload(self):
        return copy.deepcopy({'schema':1,'source':str(self.path),'source_hash':self.source_hash,'operations':self.operations,
               'crop_context':self.crop_context,'rotation':self.rotation,'box':self.box,'exported_state':self.exported_state})
    def discard_recovery(self,path):
        if path is None:return
        key=str(path);self.recovery_versions[key]=self.recovery_versions.get(key,0)+1
        self.recovery_saved.pop(key,None);self.recovery.remove(path)
    def auto_checkpoint(self):
        if self.closing_requested or self.recovery_job or self.loading or QApplication.activeModalWidget() or not self.appearance.get('auto_checkpoint',True):return
        if not self.image_dirty():return
        key=str(self.path);signature=self.edit_state()
        if self.recovery_saved.get(key)==signature:return
        self.save_draft();self.save_window_state();state=self.checkpoint_payload()
        # Editing operations replace PIL images; the captured image is immutable here.
        content=self.current;version=self.recovery_versions.get(key,0)
        job=Job(lambda:self.recovery.save(content,state));self.recovery_job=job;self.jobs.append(job)
        def saved(result):
            if self.recovery_versions.get(key,0)!=version:self.recovery.remove(key);return
            self.recovery_saved[key]=signature
            if str(self.path)==key:self.statusBar().showMessage('자동 복구본 저장 완료 · 원본은 유지됩니다.',3000)
        def finish():self.jobs.remove(job);self.recovery_job=None
        job.result.connect(saved);job.failed.connect(lambda error:self.statusBar().showMessage('자동 복구 저장 실패: '+error));job.finished.connect(finish);job.start()
    def session_operation(self,fn,title,quiet=False):
        dialog=CheckpointWait(self);dialog.setWindowTitle('편집 작업');layout=QVBoxLayout(dialog);layout.addWidget(QLabel(title))
        progress=QProgressBar();progress.setRange(0,0);layout.addWidget(progress)
        results=[];errors=[];job=Job(fn);self.jobs.append(job)
        job.result.connect(results.append);job.failed.connect(errors.append)
        def finish():self.jobs.remove(job);dialog.accept()
        job.finished.connect(finish);job.start();dialog.exec()
        self.session_error=errors[0] if errors else ''
        if errors and not quiet:self.error(errors[0])
        return results[0] if results and not errors else None
    def save_edit_session(self):
        if not self.require_image():return False
        self.save_draft();content=self.current.copy()
        state=self.checkpoint_payload()
        saved=self.session_operation(lambda:self.sessions.save(content,state),'이미지와 크롭 작업을 보관하고 있습니다…')
        if saved:
            self.discard_recovery(self.path)
            self.checkpoint_state=json_text({'operations':state['operations'],'crop_context':state['crop_context']});self.save_window_state();self.statusBar().showMessage('편집 작업을 보관했습니다. 원본을 다시 열면 작업본이 복원됩니다.');return True
        return False
    def open_edit_sessions(self):
        dialog=QDialog(self);dialog.setWindowTitle('보관한 편집 작업');dialog.resize(720,400);layout=QVBoxLayout(dialog)
        items=QListWidget();layout.addWidget(items)
        entries=dict(self.sessions.entries());entries.update(dict(self.recovery.entries()))
        for path in self.store.hidden_paths():
            if not Path(path).is_file():entries.setdefault(path,'원본 경로를 찾을 수 없음')
        missing=self.store.db.execute('SELECT path FROM source_identity').fetchall()
        for (path,) in missing:
            if not Path(path).is_file():entries.setdefault(path,'원본 경로를 찾을 수 없음')
        for path,updated in entries.items():
            item=QListWidgetItem(f'{Path(path).name}\n{updated} · {path}');item.setData(Qt.ItemDataRole.UserRole,path);items.addItem(item)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Open|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Open).setText('열기');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        reconnect=button('선택 원본 재연결…',lambda:self.reconnect_selected(items,dialog));layout.addWidget(reconnect)
        if dialog.exec()==QDialog.DialogCode.Accepted and items.currentItem():self.safe(lambda:self.load(items.currentItem().data(Qt.ItemDataRole.UserRole)))
    def reconnect_selected(self,items,dialog):
        item=items.currentItem()
        if item is None:return
        if self.jobs:self.statusBar().showMessage('진행 중인 작업이 끝난 뒤 재연결하세요.');return
        old=item.data(Qt.ItemDataRole.UserRole)
        new,_=QFileDialog.getOpenFileName(self,'이동한 동일 원본 선택 — SHA256 검증','','Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.exr)')
        if not new:return
        self.save_draft()
        result=self.session_operation(lambda:relink_source(self.store.root,old,new),'원본과 보관 작업의 해시를 검증하고 연결을 복사합니다…')
        if result:
            self.removed_paths=self.store.hidden_paths();self.search_extra=SearchExtras(self.store)
            self.library.remove_paths([old]);self.library_items.pop(old,None);self.searchable.pop(old,None);self.index_stamps.pop(old,None)
            self.add_paths([result],False);item.setData(Qt.ItemDataRole.UserRole,result);item.setText('재연결 완료 · '+result)
            self.statusBar().showMessage('재연결 완료 · 이전 기록은 유지했습니다. 열기를 눌러 복원하세요.')
    def save_window_state(self):
        self.save_browser_state()
        self.store.state('window',{'path':str(self.path) if self.path else None,'reference':self.reference.text(),
            'strength':self.strength.value(),'levels':self.levels.value(),'luminance':self.luminance.isChecked(),
            'feather':self.feather.value(),'ratio':self.ratio.currentText(),'model':self.model_path.text(),
            'threshold':self.threshold.value(),'char_threshold':self.char_threshold.value(),'exclude':self.exclude.text(),
            'batch_size':self.batch_size.value(),'precision':self.precision.currentData(),'tone_backend':self.tone_backend.currentData()})
    def restore_window_state(self):
        state=self.store.state('window')
        if not isinstance(state,dict):return
        self.precision.setCurrentIndex(max(0,self.precision.findData(state.get('precision','fp32'))))
        self.tone_backend.setCurrentIndex(max(0,self.tone_backend.findData(state.get('tone_backend','cpu'))))
        for key,widget in [('strength',self.strength),('levels',self.levels),('feather',self.feather),('threshold',self.threshold),('char_threshold',self.char_threshold),('batch_size',self.batch_size)]:
            value=state.get(key)
            if isinstance(value,(int,float)):
                widget.setValue(int(value) if isinstance(widget,QSpinBox) else value)
        for key,widget in [('reference',self.reference),('model',self.model_path),('exclude',self.exclude)]:
            if isinstance(state.get(key),str):widget.setText(state[key])
        self.luminance.setChecked(state.get('luminance') is True)
        if isinstance(state.get('ratio'),str):self.ratio.setCurrentText(state['ratio'])
        path=state.get('path')
        if isinstance(path,str) and Path(path).is_file():
            try:self.load(path)
            except Exception as exc:self.source.setText('마지막 이미지 복원 실패: '+str(exc))
        elif isinstance(path,str):self.source.setText('마지막 원본 이미지가 없습니다. 보관 작업과 데이터는 유지됩니다: '+path)
    def confirm_image_change(self):
        if not self.image_dirty():return True
        box=QMessageBox(self);box.setWindowTitle('저장하지 않은 이미지 편집');box.setText('현재 이미지의 편집 결과를 내보내시겠어요?')
        save=box.addButton('내보내기',QMessageBox.ButtonRole.AcceptRole)
        keep=box.addButton('작업 보관',QMessageBox.ButtonRole.ActionRole)
        discard=box.addButton('편집 버리기',QMessageBox.ButtonRole.DestructiveRole)
        cancel=box.addButton('취소',QMessageBox.ButtonRole.RejectRole);box.setDefaultButton(save);box.setEscapeButton(cancel);box.exec()
        if box.clickedButton() is save:return self.export_image()
        if box.clickedButton() is keep:return self.save_edit_session()
        if box.clickedButton() is discard:self.discard_recovery(self.path);return True
        return False
    def closeEvent(self,event):
        if self.data_switch_ready:
            self.store.db.close();event.accept();return
        if not self.closing_requested and not self.confirm_image_change():event.ignore();return
        self.save_main_workspace();self.disk_browser.set_active(False);self.disk_browser.save()
        self.library.stop_search()
        if self.jobs:
            self.queue_running=False
            self.closing_requested=True;self.pending_index.clear();self.setEnabled(False)
            for job in list(self.jobs):job.requestInterruption()
            self.statusBar().showMessage('진행 중인 배치를 마무리하고 안전하게 종료합니다.')
            QTimer.singleShot(150,self.close);event.ignore();return
        self.workspace_timer.stop();self.save_draft();self.save_documents();self.save_window_state();self.store.db.close();event.accept()

def main():
    app=QApplication(sys.argv);configure_app(app)
    import argparse
    parser=argparse.ArgumentParser(description='BMK AI Studio')
    parser.add_argument('--user-directory',metavar='FOLDER',help='사용자 데이터 폴더 (환경변수/설정보다 우선)')
    parser.add_argument('images',nargs='*');options=parser.parse_args()
    data_location.session_directory=options.user_directory
    while True:
        try:
            root=data_location.check_directory(data_location.resolve_directory());lock=data_location.lock_directory(root);break
        except Exception as exc:
            if data_location.session_directory or os.environ.get('BMK_STUDIO_DATA','').strip():
                QMessageBox.critical(None,'사용자 데이터 폴더를 열 수 없습니다',str(exc));sys.exit(1)
            message=QMessageBox();message.setWindowTitle('사용자 데이터 폴더를 열 수 없습니다');message.setText(str(exc))
            choose=message.addButton('다른 사용자 폴더 선택',QMessageBox.ButtonRole.ActionRole);message.addButton('종료',QMessageBox.ButtonRole.RejectRole);message.exec()
            if message.clickedButton() is not choose:sys.exit(1)
            selected=QFileDialog.getExistingDirectory(None,'기존 사용자 데이터 또는 새 빈 폴더 선택')
            if not selected:sys.exit(1)
            try:
                target=data_location.validate_existing(selected);selection_lock=data_location.lock_directory(target)
                try:data_location.save_choice(target)
                finally:selection_lock.unlock()
            except Exception as error:QMessageBox.critical(None,'폴더 선택 실패',str(error))
    try:
        window=Studio(root,location_config=data_location.config_path());window.show()
        if options.images:window.add_paths(options.images)
        code=app.exec()
    finally:lock.unlock()
    sys.exit(code)

if __name__=='__main__':main()
