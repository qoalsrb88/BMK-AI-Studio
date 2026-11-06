"""Note folder sync in the main window: settings, automatic runs, confirmations and the conflict list."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .appearance import caption
from .core import Store
from .note_sync import (RESOLVABLE, SETTINGS_KEY, NoteFolderSync, backup_folder, conflict_label, folder_key, forget_file_base,
                        plan_question, report_summary)

DEBOUNCE_MS = 2000  # after an edit; typing a folder name must not leave folders such as "M", "MO" behind
POLL_MS = 10000
BACKUPS = 'note-sync-backups'
KEEP_BACKUPS = 10


class SyncJob(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, title):
        super().__init__()
        self.fn, self.title, self.detail, self.cancel_allowed = fn, title, '처리 중', False

    def run(self):
        try:
            self.result.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc))


def prune_backups(folder, keep=KEEP_BACKUPS):
    backups = sorted(Path(folder).glob('bmk_notes-*.zip'), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in backups[keep:]:
        old.unlink(missing_ok=True)


class NoteSyncMixin:
    # ---- setup -------------------------------------------------------------------------------------------
    def build_note_sync(self, layout):
        self.note_sync_panel = QWidget()
        panel = QVBoxLayout(self.note_sync_panel)
        panel.setContentsMargins(0, 4, 0, 0)
        self.note_sync_label = caption('노트 폴더 동기화')
        self.note_sync_label.setWordWrap(True)
        self.note_sync_now = QPushButton('지금 동기화')
        self.note_sync_now.setToolTip('ComfyUI 노트 폴더와 지금 맞춥니다 · 일시 중지된 동기화도 다시 시작합니다')
        self.note_sync_now.clicked.connect(lambda: self.run_note_sync(manual=True))
        self.note_sync_conflict_button = QPushButton('충돌 확인…')
        self.note_sync_conflict_button.setProperty('primary', True)
        self.note_sync_conflict_button.clicked.connect(self.show_note_sync_conflicts)
        self.note_sync_conflict_button.hide()
        buttons = QWidget()
        line = QHBoxLayout(buttons)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(self.note_sync_now)
        line.addWidget(self.note_sync_conflict_button)
        panel.addWidget(self.note_sync_label)
        panel.addWidget(buttons)
        layout.addWidget(self.note_sync_panel)

    def init_note_sync(self):
        self.note_sync_job = None
        self.note_sync_again = False
        self.note_sync_paused = False
        self.note_sync_asking = False
        self.note_sync_final = False
        self.note_sync_started = 0.0
        self.note_sync_cache = {}
        self.note_sync_conflicts = []
        self.note_sync_problems = []
        self.note_sync_timer = QTimer(self)
        self.note_sync_timer.setSingleShot(True)
        self.note_sync_timer.setInterval(DEBOUNCE_MS)
        self.note_sync_timer.timeout.connect(self.run_note_sync)
        self.note_sync_poll = QTimer(self)
        self.note_sync_poll.setInterval(POLL_MS)
        self.note_sync_poll.timeout.connect(self.note_sync_tick)
        self.update_note_sync_panel()
        if self.note_sync_enabled():
            self.note_sync_poll.start()
            QTimer.singleShot(1500, self.note_sync_tick)

    def note_sync_config(self):
        value = self.store.state(SETTINGS_KEY)
        return value if isinstance(value, dict) else {}

    def note_sync_enabled(self):
        config = self.note_sync_config()
        return bool(config.get('enabled') and config.get('folder'))

    def update_note_sync_panel(self, text=None):
        enabled = self.note_sync_enabled()
        self.note_sync_panel.setVisible(enabled)
        if text is not None:
            self.note_sync_label.setText(text)
        elif enabled:
            self.note_sync_label.setText('노트 폴더 동기화 · ' + self.note_sync_config()['folder'])
        count = len(self.note_sync_conflicts)
        self.note_sync_conflict_button.setVisible(enabled and bool(count or self.note_sync_problems))
        self.note_sync_conflict_button.setText(f'충돌 {count}개…' if count else f'건너뜀 {len(self.note_sync_problems)}개…')

    # ---- settings ----------------------------------------------------------------------------------------
    def note_sync_settings_rows(self, layout, dialog):
        config = self.note_sync_config()
        folder = QLineEdit(config.get('folder', ''))
        folder.setPlaceholderText('ComfyUI bmk_notes 폴더 (예: …/ComfyUI/user/default/bmk_notes)')
        folder.setAccessibleName('ComfyUI 노트 폴더')
        browse = QPushButton('찾기…')

        def choose():
            chosen = QFileDialog.getExistingDirectory(dialog, 'ComfyUI 노트 폴더 (bmk_notes)', folder.text())
            if chosen:
                folder.setText(chosen)
        browse.clicked.connect(choose)
        enabled = QCheckBox('앱 노트를 이 폴더와 자동 동기화 (양방향)')
        enabled.setChecked(bool(config.get('enabled')))
        line = QWidget()
        box = QHBoxLayout(line)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(folder, 1)
        box.addWidget(browse)
        layout.addRow('ComfyUI 노트 폴더', line)
        layout.addRow(enabled)
        hint = QLabel('분류는 하위 폴더, 제목은 <제목>.json 파일이 됩니다. 처음 켜면 바뀔 내용을 먼저 보여 주고, 적용 전에 폴더를 ZIP으로 백업합니다.\n'
                      'ComfyUI 화면은 자동으로 새로 읽지 않으니, 앱에서 고친 노트는 ComfyUI에서 ↻ 또는 R을 누른 뒤 고치세요.')
        hint.setWordWrap(True)
        layout.addRow(hint)

        def values():
            return folder.text().strip(), enabled.isChecked()

        def validate():
            path, on = values()
            if on and not Path(path).is_dir():
                return 'ComfyUI 노트 폴더를 찾을 수 없습니다. 폴더 경로를 확인하세요.'
            if on and Path(path).resolve() == self.store.root.resolve():
                return '사용자 데이터 폴더는 노트 폴더로 쓸 수 없습니다.'
            return None
        return values, validate

    def apply_note_sync_settings(self, folder, enabled):
        config = self.note_sync_config()
        same = bool(config.get('folder')) and bool(folder) and folder_key(folder) == folder_key(config['folder'])
        if enabled and not (config.get('enabled') and same):
            # Switched on only after the confirmation of the first sync.
            self.store.state(SETTINGS_KEY, {'folder': folder, 'enabled': False})
            self.update_note_sync_panel()
            self.connect_note_folder(folder)
            return
        self.store.state(SETTINGS_KEY, {'folder': folder, 'enabled': bool(enabled and config.get('enabled'))})
        if not self.note_sync_enabled():
            self.note_sync_timer.stop()
            self.note_sync_poll.stop()
            self.note_sync_conflicts, self.note_sync_problems = [], []
        self.update_note_sync_panel()

    # ---- jobs --------------------------------------------------------------------------------------------
    def start_note_sync_job(self, fn, callback, quiet=True, title='노트 폴더 동기화'):
        job = SyncJob(fn, title)
        self.note_sync_job = job
        self.note_sync_started = time.monotonic()
        self.jobs.append(job)

        def result(value):
            if self.note_sync_job is job:
                self.note_sync_job = None
            self.safe(lambda: callback(value))

        def failed(message):
            if self.note_sync_job is job:
                self.note_sync_job = None
            self.update_note_sync_panel('노트 폴더 동기화 실패 · ' + ((message or '').splitlines() or ['알 수 없는 오류'])[0])
            if not quiet and not self.closing_requested:
                self.error(message)

        def finished():
            if job in self.jobs:
                self.jobs.remove(job)
            if self.note_sync_job is job:
                self.note_sync_job = None
            if self.note_sync_again and (self.note_sync_final or not self.closing_requested):
                self.note_sync_again = False
                self.run_note_sync(final=self.note_sync_final)
        job.result.connect(result)
        job.failed.connect(failed)
        job.finished.connect(finished)
        job.start()
        return job

    def note_sync_soon(self):
        """An app note changed: sync after a short pause so a half-typed name never becomes a folder."""
        if hasattr(self, 'note_sync_timer') and not self.closed and self.note_sync_enabled():
            self.note_sync_timer.start()

    def flush_note_editor(self):
        # Only pending note typing; a plain save_draft() would also rewrite the image draft and requery the gallery.
        if self.note_mode and self.autosave.isActive():
            self.save_draft()

    def note_sync_tick(self):
        if not self.note_sync_enabled() or self.note_sync_paused or self.note_sync_asking or self.closing_requested:
            return
        if self.autosave.isActive() or self.note_sync_timer.isActive() or time.monotonic() - self.note_sync_started < 2:
            return
        self.run_note_sync()

    def run_note_sync(self, manual=False, final=False):
        if not self.note_sync_enabled() or self.closed or self.note_sync_asking:
            return
        if self.closing_requested and not final:
            return
        if self.note_sync_job is not None:
            self.note_sync_again = True
            return
        if manual:
            self.note_sync_paused = False
        elif self.note_sync_paused:
            return
        self.flush_note_editor()  # the open editor's last keystrokes go to the database first
        self.note_sync_timer.stop()
        folder, root, cache = self.note_sync_config()['folder'], self.store.root, self.note_sync_cache

        def work():
            store = Store(root)
            try:
                engine = NoteFolderSync(store, folder, cache)
                if engine.fresh():
                    return {'unconnected': True}
                plan = engine.plan()
                if plan['blocked']:
                    return {'blocked': plan}
                return engine.apply(plan)
            finally:
                store.db.close()
        self.update_note_sync_panel('노트 폴더 동기화 중…')
        self.start_note_sync_job(work, lambda value: self.note_sync_result(value, manual), quiet=not manual)

    def note_sync_result(self, value, manual=False):
        if value.get('unconnected'):
            self.note_sync_paused = True
            self.update_note_sync_panel('노트 폴더 연결을 다시 확인해야 합니다 · 설정에서 동기화를 다시 켜세요.')
            return
        if 'blocked' in value:
            self.confirm_blocked_note_sync(value['blocked'])
            return
        self.note_sync_done(value)

    def confirm_blocked_note_sync(self, plan):
        if self.closing_requested:
            self.update_note_sync_panel('노트 폴더 동기화 보류 · 큰 변경은 다음 실행에서 확인합니다.')
            return
        if plan['blocked'] == 'missing':
            text = f"ComfyUI 노트 폴더에서 연결된 노트 파일 {plan['archives']:,}개가 사라졌습니다."
            info = ('드라이브가 분리됐거나 폴더를 옮겼다면 일시 중지하세요.\n'
                    'ComfyUI에서 지운 것이 맞다면 앱 노트를 보관함으로 옮깁니다. 내용과 이력은 남습니다.')
            accept = '보관함으로 옮기고 동기화'
        else:
            text = f"ComfyUI 노트 폴더에 새 노트 {plan['counts'].get('import', 0):,}개가 있습니다."
            info = '앱에 새 노트로 가져옵니다. 폴더 위치와 개수를 확인하세요.'
            accept = '가져오고 동기화'
        if self.ask_note_sync(text, info + '\n\n' + plan_question(plan), accept, plan, '일시 중지'):
            self.apply_note_sync_plan(plan)
        else:
            self.note_sync_paused = True
            self.update_note_sync_panel('노트 폴더 동기화 일시 중지 · [지금 동기화]로 다시 시작합니다.')

    def ask_note_sync(self, text, info, accept, plan, reject='취소'):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle('노트 폴더 동기화 확인')
        box.setText(text)
        box.setInformativeText(info)
        details = [conflict_label(item) for item in plan['conflicts'][:50]]
        details += [f"{item.get('path') or item.get('title')}: {item['reason']}" for item in plan['problems'][:50]]
        if details:
            box.setDetailedText('\n'.join(details))
        run = box.addButton(accept, QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton(reject, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        self.note_sync_asking = True
        try:
            box.exec()
        finally:
            self.note_sync_asking = False
        return box.clickedButton() is run

    def apply_note_sync_plan(self, plan, backup=False, then=None):
        folder, root, cache = plan['folder'], self.store.root, self.note_sync_cache

        def work():
            store = Store(root)
            try:
                saved = None
                if backup:
                    saved = backup_folder(folder, root / BACKUPS)
                    prune_backups(root / BACKUPS)
                report = NoteFolderSync(store, folder, cache).apply(plan)
                report['backup'] = saved
                return report
            finally:
                store.db.close()

        def done(report):
            if then:
                then()
            self.note_sync_done(report)
        self.update_note_sync_panel('노트 폴더 동기화 중…')
        self.start_note_sync_job(work, done, quiet=False)

    def connect_note_folder(self, folder):
        if self.note_sync_job is not None:
            self.error('노트 폴더 동기화가 진행 중입니다. 잠시 후 설정에서 다시 켜세요.')
            return
        self.flush_note_editor()
        root = self.store.root
        self.note_sync_cache = {}
        cache = self.note_sync_cache

        def scan():
            store = Store(root)
            try:
                return NoteFolderSync(store, folder, cache).plan()
            finally:
                store.db.close()

        def planned(plan):
            text = '이 폴더와 앱 노트를 동기화할까요?' if plan['fresh'] else '노트 폴더 동기화를 다시 켤까요?'
            info = (plan_question(plan) + '\n\n적용 직전에 폴더의 노트 파일(json·txt)을 앱 데이터의 ' + BACKUPS + ' 폴더에 ZIP으로 백업합니다.\n'
                    '충돌한 노트는 어느 쪽도 바꾸지 않고 목록에 남깁니다. 파일은 지우지 않고 폴더의 .trash로 옮깁니다.')
            if not self.ask_note_sync(text, info, '연결하고 동기화', plan):
                self.update_note_sync_panel()
                self.statusBar().showMessage('노트 폴더 동기화를 켜지 않았습니다. 폴더와 앱 노트는 그대로입니다.')
                return

            def enable():
                self.store.state(SETTINGS_KEY, {'folder': folder, 'enabled': True})
                self.note_sync_paused = False
                self.note_sync_poll.start()
            self.apply_note_sync_plan(plan, backup=True, then=enable)
        self.statusBar().showMessage('ComfyUI 노트 폴더를 확인하는 중…')
        self.start_note_sync_job(scan, planned, quiet=False)

    # ---- results -----------------------------------------------------------------------------------------
    def note_sync_done(self, report):
        self.note_sync_conflicts = report['conflicts']
        self.note_sync_problems = report['problems']
        changed = set(report['imported']) | set(report['updated']) | set(report['archived'])
        if changed:
            self.refresh_notes()
            for index in range(1, self.note_tabs.count()):
                nid = (self.note_tabs.tabData(index) or {}).get('id')
                record = self.store.note(nid) if nid in changed else None
                if record:
                    self.note_tabs.setTabText(index, record[1])
        message = None
        if self.note_mode and self.note_id in set(report['updated']):
            if self.note_loaded != (self.note_id, self.note_state()):
                # Typed while the folder version came in: keep the typing and let the user pick a side.
                forget_file_base(self.store, self.note_id)
                self.save_draft()
                message = '열린 노트가 ComfyUI에서도 바뀌었습니다. 편집 내용을 유지했고 다음 동기화에서 충돌로 표시합니다.'
            else:
                self.reload_open_note()
                message = '열린 노트를 ComfyUI 폴더의 내용으로 다시 읽었습니다. 이전 내용은 버전 이력에 있습니다.'
        elif self.note_mode and self.note_id in set(report['archived']):
            message = '열린 노트의 파일이 ComfyUI 폴더에서 사라져 노트를 보관함으로 옮겼습니다. 내용과 이력은 남습니다.'
        summary = report_summary(report)
        stamp = datetime.now().strftime('%H:%M:%S')
        self.update_note_sync_panel(f'노트 폴더 동기화 {stamp} · ' + (summary or '변경 없음'))
        backup = report.get('backup')
        if backup:
            summary = (summary or '변경 없음') + f" · 백업 {Path(backup['path']).name}"
        if message or summary:
            self.statusBar().showMessage(message or ('노트 폴더 동기화: ' + summary), 8000)

    def reload_open_note(self):
        from .app import replace_text
        record = self.store.note(self.note_id)
        if not record:
            return
        doc = json.loads(record[2])
        self.loading = True
        try:
            self.note_extra = doc.copy()
            if self.note_title.text() != record[1]:
                self.note_title.setText(record[1])
            if self.note_category.currentText() != record[3]:
                self.note_category.setCurrentText(record[3])
            for editor, key in ((self.draft, 'prompt'), (self.draft_negative, 'negative'), (self.memo, 'notes')):
                text = doc.get(key, '')
                if editor.toPlainText() != text:
                    replace_text(editor, text)  # Ctrl+Z brings back the previous text
            self.note_loaded = (self.note_id, self.note_state())
        finally:
            self.loading = False
        if self.document_index > 0:
            self.note_tabs.setTabText(self.document_index, record[1])

    def flush_note_sync_on_close(self):
        """Edits from the last seconds still reach the folder before the window closes."""
        if self.note_sync_final or not self.note_sync_enabled() or self.note_sync_paused:
            return
        if not (self.note_sync_timer.isActive() or self.autosave.isActive() or self.note_sync_job is not None):
            return
        self.note_sync_final = True
        self.flush_note_editor()
        if self.note_sync_job is not None:
            self.note_sync_again = True
        else:
            self.run_note_sync(final=True)

    def stop_note_sync(self):
        self.note_sync_timer.stop()
        self.note_sync_poll.stop()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow() and hasattr(self, 'note_sync_poll'):
            self.note_sync_tick()  # back from ComfyUI: pick up its edits now

    # ---- conflicts ---------------------------------------------------------------------------------------
    def show_note_sync_conflicts(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('노트 폴더 동기화 · 충돌과 건너뛴 항목')
        dialog.resize(760, 480)
        layout = QVBoxLayout(dialog)
        intro = QLabel('앱과 폴더가 서로 다른 노트는 어느 쪽도 덮어쓰지 않았습니다. 항목을 골라 맞출 쪽을 정하세요.\n'
                       '바뀌는 파일은 폴더의 .trash로, 바뀌는 앱 내용은 버전 이력에 남습니다. '
                       '파일이 사라진 노트에서 [파일 내용으로]를 고르면 앱 노트를 보관함으로 옮깁니다.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        listing = QListWidget()
        listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for item in self.note_sync_conflicts:
            entry = QListWidgetItem(conflict_label(item))
            entry.setData(Qt.ItemDataRole.UserRole, item)
            listing.addItem(entry)
        for item in self.note_sync_problems:
            entry = QListWidgetItem(f"[건너뜀] {item.get('path') or item.get('title')} — {item['reason']}")
            entry.setFlags(Qt.ItemFlag.ItemIsEnabled)
            listing.addItem(entry)
        layout.addWidget(listing, 1)
        status = QLabel('')
        status.setWordWrap(True)
        layout.addWidget(status)
        buttons = QDialogButtonBox()
        keep_app = buttons.addButton('앱 내용으로 파일 바꾸기', QDialogButtonBox.ButtonRole.ActionRole)
        keep_file = buttons.addButton('파일 내용으로 앱 바꾸기', QDialogButtonBox.ButtonRole.ActionRole)
        open_note = buttons.addButton('노트 열기', QDialogButtonBox.ButtonRole.ActionRole)
        close = buttons.addButton('닫기', QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

        def selected():
            return [entry.data(Qt.ItemDataRole.UserRole) for entry in listing.selectedItems() if entry.data(Qt.ItemDataRole.UserRole)]

        def refresh_buttons():
            items = selected()
            resolvable = bool(items) and all(item['kind'] in RESOLVABLE for item in items)
            keep_app.setEnabled(resolvable)
            keep_file.setEnabled(resolvable)
            open_note.setEnabled(len(items) == 1)
            status.setText('같은 이름이 되는 노트는 앱에서 이름이나 분류를 바꾸면 동기화됩니다.'
                           if any(item['kind'] not in RESOLVABLE for item in items) else '')

        def resolve(keep):
            items = selected()
            if self.note_sync_job is not None:
                status.setText('동기화가 진행 중입니다. 잠시 후 다시 누르세요.')
                return
            self.resolve_note_sync(items, keep)
            dialog.accept()

        def show_note():
            items = selected()
            dialog.accept()
            self.open_note_id(items[0]['note_id'])
        listing.itemSelectionChanged.connect(refresh_buttons)
        keep_app.clicked.connect(lambda: resolve('app'))
        keep_file.clicked.connect(lambda: resolve('file'))
        open_note.clicked.connect(show_note)
        close.clicked.connect(dialog.reject)
        refresh_buttons()
        self.note_sync_asking = True
        try:
            dialog.exec()
        finally:
            self.note_sync_asking = False

    def resolve_note_sync(self, items, keep):
        self.flush_note_editor()
        folder, root, cache = self.note_sync_config()['folder'], self.store.root, self.note_sync_cache

        def work():
            store = Store(root)
            try:
                engine = NoteFolderSync(store, folder, cache)
                errors = []
                for item in items:
                    try:
                        engine.resolve(item['note_id'], item.get('path'), keep)
                    except Exception as exc:
                        errors.append(f"{item['title']}: {exc}")
                plan = engine.plan()
                report = engine.apply(plan) if not plan['blocked'] else {**self.empty_note_sync_report(plan), 'blocked': True}
                report['resolve_errors'] = errors
                report['resolved'] = [item['note_id'] for item in items]
                return report
            finally:
                store.db.close()

        def done(report):
            # Notes taken from files changed under the editor: reload the open one.
            if keep == 'file':
                report['updated'] = list(dict.fromkeys(report['updated'] + report['resolved']))
            self.note_sync_done(report)
            if report['resolve_errors']:
                self.error('일부 충돌을 해결하지 못했습니다.\n' + '\n'.join(report['resolve_errors'][:20]))
        self.update_note_sync_panel('노트 폴더 충돌을 해결하는 중…')
        self.start_note_sync_job(work, done, quiet=False)

    @staticmethod
    def empty_note_sync_report(plan):
        return {'folder': plan['folder'], 'written': 0, 'moved': 0, 'trashed': 0, 'linked': 0, 'imported': [], 'updated': [],
                'archived': [], 'skipped': 0, 'failed': [], 'conflicts': plan['conflicts'], 'problems': plan['problems'],
                'deferred': plan['deferred']}
