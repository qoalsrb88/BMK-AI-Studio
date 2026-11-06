"""Two-way sync between the app's notes and a ComfyUI BMK Tabbed Notes folder (bmk_notes).

The folder keeps one note per file, <category folders>/<title>.json; ComfyUI rebuilds .bmk_meta.json and the
.txt mirrors itself. Each linked note remembers its base (file bytes hash, app content hash, title and category
at the last sync). A side is changed only while it still matches that base, so edits on both sides become
conflicts instead of overwrites. Files are never deleted: they move to the folder's .trash like ComfyUI does.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath

from .core import NOTE_IMPORT_CONFIRM, NOTE_IMPORT_LOCK, NOTE_IMPORT_MAX_BYTES, normalize_category, note_skip_reason, validate_note

APP_FIELDS = ('schema', 'source', '_studio_category', '_studio_image_transfers')  # app-only keys never written to files
UNSORTED = '미분류'  # folder for notes without a category; ComfyUI shows only notes inside category folders
UNTITLED = '제목 없는 노트'
MAX_ABS_PATH = 240  # same limit as the ComfyUI node
MASS_MISSING = 20
SETTINGS_KEY = 'note_sync'  # {'folder', 'enabled'}: chosen in the settings dialog
BASE_KEY = 'note_sync_base'  # {'folder', 'dirs'}: folder the links belong to, folders this app created
SYNC_LOCK = threading.Lock()
_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

KIND_REASONS = {
    'both': '앱과 폴더에서 모두 바뀜',
    'occupied': '같은 이름의 다른 노트 파일이 폴더에 있음',
    'deleted': '앱에서 고친 노트의 파일이 폴더에서 사라짐',
    'archived': '앱에서 보관했지만 폴더의 파일이 바뀜',
    'duplicate': '같은 파일 이름이 되는 노트가 앱에 여럿 있음 · 노트 이름을 바꾸면 동기화됩니다',
}
RESOLVABLE = ('both', 'occupied', 'deleted', 'archived')


class NoteSyncError(Exception):
    pass


class Changed(Exception):
    """A file changed after planning; the action waits for the next sync."""


def safe_name(name, fallback=''):
    """File or folder name exactly like the ComfyUI node makes it."""
    name = _INVALID.sub('_', str(name or ''))
    name = name.strip().rstrip('. ').lstrip('.').strip()
    return name or fallback


def note_path(title, category):
    """Relative posix path of a note file."""
    folders = [safe_name(part, '_') for part in (category.split('/') if category else [UNSORTED])]
    return '/'.join(folders + [safe_name(title, UNTITLED) + '.json'])


def path_category(rel):
    category = '/'.join(PurePosixPath(rel).parts[:-1])
    return '' if category == UNSORTED else normalize_category(category)


def title_for(rel, current=None):
    """Title for a file; keeps the app's own spelling while it still maps to that file name."""
    stem = PurePosixPath(rel).stem
    return current if current is not None and safe_name(current, UNTITLED) == stem else stem


def category_for(rel, current=None):
    folder = PurePosixPath(rel).parent.as_posix()
    if current is not None and PurePosixPath(note_path('x', current)).parent.as_posix() == folder:
        return current
    return path_category(rel)


def file_doc(body):
    """The part of an app note written to the folder: everything except the app's own keys."""
    return {key: value for key, value in body.items() if key not in APP_FIELDS}


def doc_hash(doc):
    text = json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def encode(doc):
    """File bytes in the node's own format: UTF-8, indent 1, LF, no final newline."""
    return json.dumps(doc, ensure_ascii=False, indent=1).encode('utf-8')


def merged_body(body, doc):
    """App body after taking a file's content: the file's fields plus the app's own keys."""
    return {**doc, **{key: body[key] for key in APP_FIELDS if key in body}}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_note(data):
    """(file doc, None) for a BMK note file, (None, reason) for other JSON; raises for unreadable notes."""
    doc = json.loads(data.decode('utf-8-sig'))
    reason = note_skip_reason(doc)
    if reason:
        return None, reason
    validate_note(doc)
    return file_doc(doc), None


def folder_key(folder):
    return os.path.normcase(os.path.abspath(str(folder)))


def _retry(fn, attempts=5):
    # Explorer, Dropbox or a virus scanner may briefly hold the file.
    for attempt in range(attempts):
        try:
            return fn()
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.1 * (attempt + 1))


class Entry:
    """A note file found in the folder; bytes are read only when its hash or content is needed."""

    def __init__(self, root, rel, stat, cache):
        self.root, self.rel, self.cache = root, rel, cache
        self.stamp = (stat.st_mtime_ns, stat.st_size)
        self.data = None
        cached = cache.get(rel)
        self.hash = cached[1] if cached and cached[0] == self.stamp else None

    def read(self):
        if self.data is None:
            if self.stamp[1] > NOTE_IMPORT_MAX_BYTES:
                raise ValueError('BMK 노트로 보기에 너무 큰 파일 (1MB 초과)')
            self.data = (self.root / self.rel).read_bytes()
            self.hash = digest(self.data)
            self.cache[self.rel] = (self.stamp, self.hash)
        return self.data

    def digest(self):
        if self.hash is None:
            self.read()
        return self.hash

    def note(self):
        return parse_note(self.read())


class Note:
    def __init__(self, nid, title, body, category, archived):
        self.id, self.title, self.category, self.archived = nid, title, category, bool(archived)
        self.body = json.loads(body)
        if not isinstance(self.body, dict):
            raise ValueError('노트 본문이 JSON 객체가 아닙니다.')
        self.doc = file_doc(self.body)
        self.hash = doc_hash(self.doc)

    def state(self):
        return (self.title, self.category, self.archived, self.hash)


def backup_folder(folder, destination):
    """ZIP of the folder's notes, settings, mirrors and trash (json/txt) before the first sync writes anything."""
    folder = Path(folder)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"bmk_notes-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    i = 2
    while target.exists():
        target = destination / f"{target.stem.split(' (')[0]} ({i}).zip"
        i += 1
    count = 0
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for current, dirs, names in os.walk(folder):
            dirs.sort()
            for name in sorted(names):
                if Path(name).suffix.lower() in ('.json', '.txt'):
                    path = Path(current) / name
                    archive.write(path, path.relative_to(folder).as_posix())
                    count += 1
    return {'path': str(target), 'files': count}


class NoteFolderSync:
    def __init__(self, store, folder, cache=None):
        self.store = store
        self.db = store.db
        self.root = Path(folder)
        self.cache = cache if cache is not None else {}
        self.created = set()

    # ---- stored state -------------------------------------------------------------------------------
    def base(self):
        value = self.store.state(BASE_KEY)
        return value if isinstance(value, dict) else {}

    def fresh(self):
        """True until a sync has been applied to this folder; links of another folder are ignored."""
        return self.base().get('folder') != folder_key(self.root)

    def rows(self):
        if self.fresh():
            return {}
        return {row[0]: {'path': row[1], 'file_hash': row[2], 'doc_hash': row[3], 'title': row[4], 'category': row[5]}
                for row in self.db.execute('SELECT note_id,path,file_hash,doc_hash,title,category FROM note_sync')}

    def put_row(self, nid, path, file_hash, hashed, title, category):
        self.db.execute('INSERT OR REPLACE INTO note_sync VALUES(?,?,?,?,?,?)', (nid, path, file_hash, hashed, title, category))

    def drop_row(self, nid):
        self.db.execute('DELETE FROM note_sync WHERE note_id=?', (nid,))

    def notes(self):
        notes, problems = {}, []
        for record in self.db.execute('SELECT n.id,n.title,n.body,COALESCE(m.category,\'\'),COALESCE(m.archived,0) FROM notes n '
                                      'LEFT JOIN note_meta m ON m.note_id=n.id ORDER BY n.updated DESC,n.rowid DESC'):
            try:
                notes[record[0]] = Note(*record)
            except (ValueError, TypeError) as exc:
                problems.append({'title': record[1], 'path': None, 'reason': '앱 노트를 읽지 못함: ' + str(exc)})
        return notes, problems

    def note(self, nid):
        record = self.db.execute('SELECT n.id,n.title,n.body,COALESCE(m.category,\'\'),COALESCE(m.archived,0) FROM notes n '
                                 'LEFT JOIN note_meta m ON m.note_id=n.id WHERE n.id=?', (nid,)).fetchone()
        return Note(*record) if record else None

    # ---- folder ---------------------------------------------------------------------------------------
    def check_root(self):
        if not self.root.is_dir():
            raise NoteSyncError(f'노트 폴더를 찾을 수 없습니다: {self.root}\n드라이브 연결과 설정의 폴더 경로를 확인하세요.')

    def scan(self):
        """Note files by casefolded path. Like the node: dot folders/files are hidden and the root holds no notes."""
        files, top = {}, os.fspath(self.root)
        for current, dirs, names in os.walk(top):
            dirs[:] = sorted(name for name in dirs if not name.startswith('.'))
            if current == top:
                continue
            for name in sorted(names):
                if name.startswith('.') or not name.lower().endswith('.json'):
                    continue
                path = Path(current) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                rel = path.relative_to(self.root).as_posix()
                files[rel.casefold()] = Entry(self.root, rel, stat, self.cache)
        return files

    def abs(self, rel):
        path = self.root.joinpath(*PurePosixPath(rel).parts)
        if '..' in PurePosixPath(rel).parts or not PurePosixPath(rel).parts:
            raise NoteSyncError('노트 폴더 밖의 경로는 쓰지 않습니다: ' + rel)
        return path

    def too_long(self, rel):
        return len(os.path.abspath(str(self.abs(rel)))) > MAX_ABS_PATH

    def current_hash(self, path):
        try:
            return digest(path.read_bytes())
        except FileNotFoundError:
            return None

    # ---- planning (reads only) ---------------------------------------------------------------------------
    def plan(self):
        self.check_root()
        fresh = self.fresh()
        rows = self.rows()
        notes, problems = self.notes()
        files = self.scan()
        actions, conflicts = [], []
        deferred = 0
        ignored = Counter()
        owner = {}  # casefolded file path -> note that keeps or takes it this round
        claimed = set()  # files accounted for (not imported as new notes)
        linked = {row['path'].casefold(): nid for nid, row in rows.items()}
        missing, moving = [], []

        def conflict(kind, note, path):
            conflicts.append({'kind': kind, 'note_id': note.id, 'path': path, 'title': note.title,
                              'category': note.category, 'reason': KIND_REASONS[kind]})

        def link(note, entry_or_path, file_hash):
            rel = entry_or_path if isinstance(entry_or_path, str) else entry_or_path.rel
            actions.append({'op': 'link', 'note_id': note.id, 'path': rel, 'file_hash': file_hash, 'doc_hash': note.hash,
                            'title': note.title, 'category': note.category})

        def readable(entry):
            try:
                doc, reason = entry.note()
            except (OSError, ValueError) as exc:
                problems.append({'title': None, 'path': entry.rel, 'reason': '파일을 읽지 못함 · 다음 동기화에서 다시 확인: ' + str(exc)})
                return None
            if reason:
                problems.append({'title': None, 'path': entry.rel, 'reason': 'BMK 노트가 아닌 JSON: ' + reason})
                return None
            return doc

        # 1. Linked notes whose file is still there.
        for nid, row in rows.items():
            note = notes.get(nid)
            if note is None:
                actions.append({'op': 'unlink', 'note_id': nid})
                continue
            key = row['path'].casefold()
            entry = files.get(key)
            if entry is None:
                missing.append((note, row))
                continue
            claimed.add(key)
            try:
                file_changed = entry.digest() != row['file_hash']
            except (OSError, ValueError) as exc:
                problems.append({'title': note.title, 'path': row['path'], 'reason': '파일을 읽지 못함: ' + str(exc)})
                owner[key] = nid
                continue
            content_changed = note.hash != row['doc_hash']
            renamed = (note.title, note.category) != (row['title'], row['category'])
            if note.archived:
                if file_changed:
                    conflict('archived', note, row['path'])
                else:
                    actions.append({'op': 'trash', 'note_id': nid, 'path': row['path'], 'file_hash': row['file_hash']})
                owner[key] = nid
                continue
            # A new title that keeps the same file name (e.g. "a:b" and "a_b") is not a move.
            target = note_path(note.title, note.category) if renamed else row['path']
            relocated = target != row['path']
            if not file_changed:
                if relocated:
                    moving.append((note, row, target, content_changed))
                    continue
                owner[key] = nid
                if content_changed:
                    actions.append({'op': 'write', 'note_id': nid, 'path': row['path'], 'expected': row['file_hash'],
                                    'data': encode(note.doc), 'doc_hash': note.hash, 'title': note.title, 'category': note.category})
                elif renamed:
                    link(note, entry, row['file_hash'])
                continue
            owner[key] = nid
            doc = readable(entry)
            if doc is None:
                continue
            if not content_changed and not relocated:
                if doc_hash(doc) == row['doc_hash']:
                    link(note, entry, entry.digest())  # same content saved again
                else:
                    actions.append({'op': 'update', 'note_id': nid, 'path': entry.rel, 'app': note.state(),
                                    'title': note.title, 'category': note.category})
            elif doc_hash(doc) == note.hash and not relocated:
                link(note, entry, entry.digest())  # both sides made the same change
            else:
                conflict('both', note, entry.rel)

        # 2. Notes renamed or moved to another folder in the app.
        # Files that another note moves away or sends to .trash this round are taken next round.
        vacating = {row['path'].casefold() for _, row, _, _ in moving} | {a['path'].casefold() for a in actions if a['op'] == 'trash'}
        for note, row, _, _ in moving:
            owner.setdefault(row['path'].casefold(), note.id)

        def wait(note, rel):
            nonlocal deferred
            deferred += 1
            problems.append({'title': note.title, 'path': rel, 'reason': '다른 노트가 이 파일 이름에서 옮겨 가는 중 · 다음 동기화에서 씀'})

        for note, row, target, content_changed in moving:
            key, tkey = row['path'].casefold(), target.casefold()
            if self.too_long(target):
                problems.append({'title': note.title, 'path': target, 'reason': f'경로가 {MAX_ABS_PATH}자를 넘어 옮기지 않음 · 이름이나 분류를 줄이세요'})
            elif tkey != key and tkey in vacating:
                wait(note, target)
            elif tkey != key and tkey in owner:
                conflict('duplicate', note, row['path'])
            elif tkey != key and tkey in files:
                owner[tkey] = note.id
                claimed.add(tkey)
                conflict('occupied', note, files[tkey].rel)
            else:
                owner[tkey] = note.id
                actions.append({'op': 'move', 'note_id': note.id, 'old': row['path'], 'path': target, 'file_hash': row['file_hash'],
                                'data': encode(note.doc) if content_changed else None, 'doc_hash': note.hash,
                                'title': note.title, 'category': note.category})

        # 3. Linked files gone from their place: renamed or moved in ComfyUI (same bytes elsewhere), else deleted.
        loose = {}
        for key, entry in files.items():
            if key in claimed or key in linked:
                continue
            try:
                loose.setdefault(entry.digest(), []).append(key)
            except (OSError, ValueError):
                pass
        wanted = Counter(row['file_hash'] for _, row in missing)
        archives = 0
        for note, row in missing:
            candidates = loose.get(row['file_hash'], [])
            if len(candidates) == 1 and wanted[row['file_hash']] == 1 and candidates[0] not in owner:
                key = candidates[0]
                entry = files[key]
                claimed.add(key)
                owner[key] = note.id
                unchanged = note.hash == row['doc_hash'] and (note.title, note.category) == (row['title'], row['category'])
                if note.archived:
                    actions.append({'op': 'trash', 'note_id': note.id, 'path': entry.rel, 'file_hash': row['file_hash']})
                elif unchanged:
                    actions.append({'op': 'update', 'note_id': note.id, 'path': entry.rel, 'app': note.state(),
                                    'title': title_for(entry.rel, note.title), 'category': category_for(entry.rel, note.category)})
                else:
                    conflict('both', note, entry.rel)
            elif note.archived:
                actions.append({'op': 'unlink', 'note_id': note.id})
            elif note.hash != row['doc_hash'] or (note.title, note.category) != (row['title'], row['category']):
                conflict('deleted', note, row['path'])
            else:
                actions.append({'op': 'archive', 'note_id': note.id, 'path': row['path'], 'app': note.state()})
                archives += 1

        # 4. App notes not linked yet: link to an identical file, write a new file, or report the name clash.
        leaving = {a['old'].casefold() for a in actions if a['op'] == 'move'} | {a['path'].casefold() for a in actions if a['op'] == 'trash'}
        for note in notes.values():
            if note.id in rows or note.archived:
                continue
            target = note_path(note.title, note.category)
            tkey = target.casefold()
            if self.too_long(target):
                problems.append({'title': note.title, 'path': target, 'reason': f'경로가 {MAX_ABS_PATH}자를 넘어 쓰지 않음 · 이름이나 분류를 줄이세요'})
                continue
            if tkey in leaving:
                wait(note, target)
                continue
            if tkey in owner:
                conflict('duplicate', note, None)
                continue
            if tkey in files:
                owner[tkey] = note.id
                claimed.add(tkey)
                entry = files[tkey]
                doc = readable(entry)
                if doc is None:
                    continue
                if doc_hash(doc) == note.hash:
                    link(note, entry, entry.digest())
                else:
                    conflict('occupied', note, entry.rel)
                continue
            owner[tkey] = note.id
            actions.append({'op': 'write', 'note_id': note.id, 'path': target, 'expected': None, 'data': encode(note.doc),
                            'doc_hash': note.hash, 'title': note.title, 'category': note.category})

        # 5. Files nobody has: new notes from ComfyUI.
        for key, entry in files.items():
            if key in claimed or key in owner or key in linked:
                continue
            try:
                doc, reason = entry.note()
            except (OSError, ValueError) as exc:
                problems.append({'title': None, 'path': entry.rel, 'reason': '파일을 읽지 못함 · 다음 동기화에서 다시 확인: ' + str(exc)})
                continue
            if reason:
                ignored[reason] += 1
                continue
            actions.append({'op': 'import', 'path': entry.rel, 'title': title_for(entry.rel), 'category': path_category(entry.rel)})

        counts = Counter(action['op'] for action in actions)
        new_dirs = Counter()
        for action in actions:
            if action['op'] in ('write', 'move'):
                parent = PurePosixPath(action['path']).parent
                if not self.abs(parent.as_posix()).is_dir():
                    new_dirs[parent.as_posix()] += 1
        imports = counts['import']
        blocked = None
        if archives >= MASS_MISSING:
            blocked = 'missing'
        elif imports >= NOTE_IMPORT_CONFIRM and not fresh:
            blocked = 'imports'
        return {'folder': str(self.root), 'fresh': fresh, 'actions': actions, 'conflicts': conflicts, 'problems': problems,
                'counts': dict(counts), 'archives': archives, 'deferred': deferred, 'ignored': dict(ignored),
                'new_dirs': dict(new_dirs), 'blocked': blocked, 'files': len(files)}

    # ---- applying --------------------------------------------------------------------------------------------
    def apply(self, plan):
        """Carry out a plan. Every action checks its side again first; changed items wait for the next sync."""
        report = {'folder': plan['folder'], 'written': 0, 'moved': 0, 'trashed': 0, 'linked': 0, 'imported': [], 'updated': [],
                  'archived': [], 'skipped': 0, 'failed': [], 'conflicts': plan['conflicts'], 'problems': plan['problems'],
                  'deferred': plan['deferred']}
        with SYNC_LOCK, NOTE_IMPORT_LOCK:
            self.check_root()
            if self.fresh() != plan['fresh']:
                raise NoteSyncError('동기화 기준이 바뀌었습니다. 다시 동기화하세요.')
            base = self.base()
            self.created = set(base.get('dirs') or []) if not plan['fresh'] else set()
            if plan['fresh']:
                with self.db:
                    self.db.execute('DELETE FROM note_sync')
                self.store.state(BASE_KEY, {'folder': folder_key(self.root), 'dirs': []})
            try:
                for action in plan['actions']:
                    try:
                        getattr(self, '_' + action['op'])(action, report)
                    except Changed:
                        report['skipped'] += 1
                    except Exception as exc:
                        if self.db.in_transaction:
                            self.db.rollback()
                        report['failed'].append({'path': action.get('path') or action.get('note_id'), 'error': str(exc)})
            finally:
                self.store.state(BASE_KEY, {'folder': folder_key(self.root), 'dirs': sorted(self.created)})
        return report

    def _commit_row(self, *values):
        with self.db:
            self.put_row(*values)

    def _link(self, a, report):
        self._commit_row(a['note_id'], a['path'], a['file_hash'], a['doc_hash'], a['title'], a['category'])
        report['linked'] += 1

    def _unlink(self, a, report):
        with self.db:
            self.drop_row(a['note_id'])

    def _write(self, a, report):
        self.write_file(a['path'], a['data'], a['expected'])
        self._commit_row(a['note_id'], a['path'], digest(a['data']), a['doc_hash'], a['title'], a['category'])
        report['written'] += 1

    def _move(self, a, report):
        row = self.db.execute('SELECT doc_hash FROM note_sync WHERE note_id=?', (a['note_id'],)).fetchone()
        self.move_file(a['old'], a['path'], a['file_hash'])
        file_hash, hashed = a['file_hash'], row[0] if row else a['doc_hash']
        if a['data'] is not None:
            try:
                self.write_file(a['path'], a['data'], a['file_hash'])
                file_hash, hashed = digest(a['data']), a['doc_hash']
            except Changed:
                pass  # moved; the new content is written next time unless the file changed meanwhile
        self._commit_row(a['note_id'], a['path'], file_hash, hashed, a['title'], a['category'])
        report['moved'] += 1

    def _trash(self, a, report):
        self.trash_file(a['path'], a['file_hash'])
        with self.db:
            self.drop_row(a['note_id'])
        report['trashed'] += 1

    def _read_note(self, rel):
        data = self.abs(rel).read_bytes()
        doc, reason = parse_note(data)
        if reason:
            raise ValueError('BMK 노트가 아닌 JSON: ' + reason)
        return data, doc

    def _update(self, a, report):
        data, doc = self._read_note(a['path'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            note = self.note(a['note_id'])
            if note is None or note.state() != tuple(a['app']):
                raise Changed()
            body = merged_body(note.body, doc)
            self.put_row(note.id, a['path'], digest(data), doc_hash(file_doc(body)), a['title'], a['category'])
            if body == note.body and (a['title'], a['category']) == (note.title, note.category):
                self.db.commit()
            else:
                self.store.save_note(a['title'], body, note.id, a['category'])  # commits with the link
                report['updated'].append(note.id)
        except BaseException:
            if self.db.in_transaction:
                self.db.rollback()
            raise

    def _import(self, a, report):
        data, doc = self._read_note(a['path'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            taken = {row[0].casefold() for row in self.db.execute('SELECT path FROM note_sync')}
            if a['path'].casefold() in taken:
                raise Changed()
            nid = uuid.uuid4().hex
            self.put_row(nid, a['path'], digest(data), doc_hash(doc), a['title'], a['category'])
            self.store.save_note(a['title'], doc, nid, a['category'])  # commits with the link
        except BaseException:
            if self.db.in_transaction:
                self.db.rollback()
            raise
        report['imported'].append(nid)

    def _archive(self, a, report):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            note = self.note(a['note_id'])
            if note is None or note.state() != tuple(a['app']) or self.abs(a['path']).exists():
                raise Changed()
            self.drop_row(note.id)
            self.store.archive_note(note.id, True)  # commits with the unlink
        except BaseException:
            if self.db.in_transaction:
                self.db.rollback()
            raise
        report['archived'].append(a['note_id'])

    # ---- file operations ---------------------------------------------------------------------------------------
    def ensure_dir(self, folder):
        missing = []
        current = folder
        while not current.exists() and current != self.root and self.root in current.parents:
            missing.append(current)
            current = current.parent
        folder.mkdir(parents=True, exist_ok=True)
        for path in missing:
            self.created.add(path.relative_to(self.root).as_posix())

    def tidy(self, folder):
        """Remove empty folders this app created, from the given folder upward."""
        while folder != self.root and self.root in folder.parents:
            rel = folder.relative_to(self.root).as_posix()
            if rel not in self.created:
                return
            try:
                folder.rmdir()
            except OSError:
                return
            self.created.discard(rel)
            folder = folder.parent

    def write_file(self, rel, data, expected):
        """Write through a dot temp file; replace only while the file is as expected (None: still absent)."""
        path = self.abs(rel)
        if len(os.path.abspath(str(path))) > MAX_ABS_PATH:
            raise NoteSyncError(f'경로가 {MAX_ABS_PATH}자를 넘습니다: {rel}')
        self.ensure_dir(path.parent)
        temp = path.with_name('.' + path.name + '.tmp')
        try:
            with open(temp, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self.current_hash(path) != expected:
                raise Changed()
            _retry(lambda: os.replace(temp, path))
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
        self.cache.pop(rel, None)

    def move_file(self, old, new, expected):
        source, target = self.abs(old), self.abs(new)
        if self.current_hash(source) != expected:
            raise Changed()
        if target.exists() and not os.path.samefile(source, target):
            raise Changed()
        self.ensure_dir(target.parent)
        _retry(lambda: os.rename(source, target))
        mirror, mirror_target = source.with_suffix('.txt'), target.with_suffix('.txt')
        if mirror.exists():
            if mirror_target.exists() and not os.path.samefile(mirror, mirror_target):
                self.to_trash(mirror)
            else:
                _retry(lambda: os.rename(mirror, mirror_target))
        self.cache.pop(old, None)
        self.tidy(source.parent)

    def trash_file(self, rel, expected=None):
        """Move a note file and its .txt mirror to .trash like ComfyUI; expected=None skips the content check."""
        path = self.abs(rel)
        if expected is not None and self.current_hash(path) != expected:
            raise Changed()
        moved = self.to_trash(path)
        mirror = path.with_suffix('.txt')
        if mirror.exists():
            self.to_trash(mirror)
        self.cache.pop(rel, None)
        self.tidy(path.parent)
        return moved

    def to_trash(self, path):
        trash = self.root / '.trash'
        trash.mkdir(exist_ok=True)
        base = time.strftime('%Y%m%d_%H%M%S') + '_' + path.name
        target = trash / base
        i = 2
        while target.exists():
            target = trash / f'{base} ({i})'
            i += 1
        _retry(lambda: os.rename(path, target))
        return target

    # ---- conflict resolution ------------------------------------------------------------------------------------
    def resolve(self, nid, path, keep):
        """Settle one conflict from the current state: keep='app' writes the app note, keep='file' takes the file."""
        with SYNC_LOCK, NOTE_IMPORT_LOCK:
            self.check_root()
            if self.fresh():
                raise NoteSyncError('먼저 노트 폴더 동기화를 실행하세요.')
            base = self.base()
            self.created = set(base.get('dirs') or [])
            try:
                note = self.note(nid)
                if note is None:
                    raise NoteSyncError('앱 노트를 찾을 수 없습니다.')
                rows = self.rows()
                others = {row['path'].casefold() for other, row in rows.items() if other != nid}
                own = rows.get(nid)
                if keep == 'app':
                    self._keep_app(note, own, path, others)
                else:
                    self._keep_file(note, own, path, others)
            finally:
                self.store.state(BASE_KEY, {'folder': folder_key(self.root), 'dirs': sorted(self.created)})

    def _keep_app(self, note, own, path, others):
        olds = [rel for rel in (path, own['path'] if own else None) if rel]
        if note.archived:
            for rel in dict.fromkeys(olds):
                if rel.casefold() not in others and self.abs(rel).exists():
                    self.trash_file(rel)
            with self.db:
                self.drop_row(note.id)
            return
        target = note_path(note.title, note.category)
        if target.casefold() in others:
            raise NoteSyncError('같은 파일 이름을 쓰는 다른 노트가 있습니다. 노트 이름이나 분류를 바꾸세요.')
        for rel in dict.fromkeys(olds + [target]):
            # The replaced files stay recoverable in .trash.
            if rel.casefold() not in others and self.abs(rel).exists():
                self.trash_file(rel)
        data = encode(note.doc)
        self.write_file(target, data, None)
        self._commit_row(note.id, target, digest(data), note.hash, note.title, note.category)

    def _keep_file(self, note, own, path, others):
        if not path or not self.abs(path).exists():
            # The file is gone: the app follows the folder and archives the note.
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.drop_row(note.id)
                self.store.archive_note(note.id, True)
            except BaseException:
                if self.db.in_transaction:
                    self.db.rollback()
                raise
            return
        if path.casefold() in others:
            raise NoteSyncError('이 파일은 다른 노트와 연결돼 있습니다.')
        data, doc = self._read_note(path)
        title, category = title_for(path, note.title), category_for(path, note.category)
        body = merged_body(note.body, doc)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.put_row(note.id, path, digest(data), doc_hash(file_doc(body)), title, category)
            self.db.execute('UPDATE note_meta SET archived=0 WHERE note_id=?', (note.id,))
            self.store.save_note(title, body, note.id, category)  # commits the link and the restored note
        except BaseException:
            if self.db.in_transaction:
                self.db.rollback()
            raise


def forget_file_base(store, nid):
    """Treat the file as changed once more: an edit made while the sync updated this note becomes a conflict."""
    with store.db:
        store.db.execute("UPDATE note_sync SET file_hash='' WHERE note_id=?", (nid,))


def plan_question(plan):
    """Summary shown before the first sync of a folder (or a large change)."""
    counts = plan['counts']
    folders = sorted(plan['new_dirs'].items(), key=lambda item: (-item[1], item[0]))
    lines = ['폴더: ' + plan['folder'], f"노트 파일 {plan['files']:,}개를 확인했습니다.",
             f"같은 내용으로 연결: {counts.get('link', 0):,}개",
             f"폴더 → 앱 새 노트: {counts.get('import', 0):,}개",
             f"앱 → 폴더 새 파일: {sum(1 for a in plan['actions'] if a['op'] == 'write' and a['expected'] is None):,}개",
             f"앱 → 폴더 내용 변경: {sum(1 for a in plan['actions'] if a['op'] == 'write' and a['expected'] is not None):,}개 / 이동: {counts.get('move', 0):,}개",
             f"폴더에서 사라져 보관함으로: {counts.get('archive', 0):,}개 / 휴지통(.trash)으로: {counts.get('trash', 0):,}개",
             f"충돌 (어느 쪽도 바꾸지 않음): {len(plan['conflicts']):,}개"]
    if plan['problems']:
        lines.append(f"건너뜀: {len(plan['problems']):,}개 (경로 길이·읽기 오류 등)")
    if folders:
        lines.append('새로 만들 폴더: ' + ', '.join(f'{name} ({count:,})' for name, count in folders[:5]) + (f' 외 {len(folders) - 5:,}곳' if len(folders) > 5 else ''))
    return '\n'.join(lines)


def report_summary(report):
    """One status line for a finished sync."""
    parts = []
    for count, label in ((report['written'], '파일 씀'), (report['moved'], '파일 이동'), (report['trashed'], '휴지통으로'),
                         (len(report['imported']), '새 노트'), (len(report['updated']), '앱 노트 갱신'), (len(report['archived']), '보관함으로')):
        if count:
            parts.append(f'{label} {count:,}개')
    if report['conflicts']:
        parts.append(f"충돌 {len(report['conflicts']):,}개")
    if report['failed']:
        parts.append(f"실패 {len(report['failed']):,}개")
    return ' · '.join(parts)


def conflict_label(item):
    where = (item['category'] or UNSORTED) + ' / ' + item['title']
    return f"{where} — {item['reason']}" + (f"\n    파일: {item['path']}" if item.get('path') else '')
