from __future__ import annotations

import hashlib
import math
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ExifTags
from .vendor.bmk_prompt_from_image import _read_metadata, extract_prompts, _decode_user_comment
from .metadata import details

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff', '.exr'}

def data_dir():
    from .data_location import check_directory,resolve_directory
    return check_directory(resolve_directory())

def json_text(value):
    def fallback(v):
        if isinstance(v, bytes):
            return v.decode('utf-8', errors='replace')
        return str(v)
    return json.dumps(value, ensure_ascii=False, indent=2, default=fallback)

def fingerprint(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def load_image(path):
    from .color import high_precision,display_high_precision
    if high_precision(path):return display_high_precision(path)
    with Image.open(path) as im:
        return ImageOps.exif_transpose(im).convert('RGBA')

def inspect_image(path):
    path = Path(path).resolve()
    if path.suffix.lower()=='.exr':
        import OpenEXR
        with OpenEXR.File(str(path),header_only=True) as file:
            info=file.header();lo,hi=info['dataWindow'];size=[int(hi[0]-lo[0]+1),int(hi[1]-lo[1]+1)]
            raw={key:str(value) for key,value in info.items() if key!='channels'}
        return {'path':str(path),'size':size,'positive':'','negative':'','source':'EXR · 선형 sRGB 가정의 SDR 미리보기. 편집 탭에서 색상 해석을 지정하세요.','raw':raw,'characters':[],'candidates':[],**details({})}
    raw = _read_metadata(path)
    with Image.open(path) as im:
        size = ImageOps.exif_transpose(im).size
        exif = im.getexif()
        fields = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
        try:
            fields.update({ExifTags.TAGS.get(k, str(k)): v for k, v in exif.get_ifd(34665).items()})
        except (KeyError, TypeError):
            pass
        if fields:
            raw['EXIF'] = fields
        user_comment = fields.get('UserComment')
        if isinstance(user_comment, bytes): user_comment = _decode_user_comment(user_comment)
        if isinstance(user_comment, str) and user_comment.strip(): raw.setdefault('UserComment', user_comment)
        for key in ('Description', 'Comment', 'XML:com.adobe.xmp', 'xmp'):
            if key in im.info and key not in raw:
                raw[key] = im.info[key]
    parsed = details(raw)
    positive, negative, source = extract_prompts(raw, include_char_captions=False, apply_prefix_suffix=False)
    if not positive:
        for field in ('Description', 'ImageDescription'):
            value = raw.get(field) or fields.get(field)
            if isinstance(value, str) and value:
                positive, source = value, '파일 설명 (' + field + ')'
                break
    if not positive and parsed['xmp'].get('description'):
        positive, source = parsed['xmp']['description'], '파일 설명 (XMP dc:description)'
    # Preserve candidates without claiming to know the actual executed branch.
    candidates = []
    graph = raw.get('prompt', {})
    if isinstance(graph, str):
        try:
            graph = json.loads(graph)
        except ValueError:
            graph = {}
    if isinstance(graph, dict):
        for node_id, node in graph.items():
            if isinstance(node, dict):
                inputs = node.get('inputs', {})
                if not isinstance(inputs, dict): continue
                for key, value in inputs.items():
                    if key in ('text', 'text_g', 'text_l', 'positive', 'negative') and isinstance(value, str):
                        candidates.append({'node': node_id, 'type': node.get('class_type'), 'field': key, 'text': value})
    characters = []
    comment = raw.get('Comment', {})
    if isinstance(comment, str):
        try:
            comment = json.loads(comment)
        except ValueError:
            comment = {}
    if isinstance(comment, dict):
        for field in ('v4_prompt', 'v4_negative_prompt'):
            block = comment.get(field, {})
            if isinstance(block, dict):
                caption = block.get('caption', {})
                if isinstance(caption, dict):
                    characters.append({'field': field, 'characters': caption.get('char_captions', [])})
    return {'path': str(path), 'size': size, 'positive': positive, 'negative': negative,
            'source': source or '생성 프롬프트를 확인하지 못했습니다', 'raw': raw,
            'characters': characters, 'candidates': candidates, **parsed}

class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / 'library.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        from .organize import SCHEMA
        self.db.executescript(SCHEMA)
        from .discovery import SCHEMA as discovery_schema
        self.db.executescript(discovery_schema)
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, updated TEXT);
        CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, note_id TEXT, body TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS assets(path TEXT PRIMARY KEY, metadata TEXT, draft TEXT, negative TEXT, memo TEXT);
        CREATE TABLE IF NOT EXISTS tags(cache_key TEXT PRIMARY KEY, scores TEXT);
        CREATE TABLE IF NOT EXISTS image_index(path TEXT PRIMARY KEY, stamp TEXT, searchable TEXT, thumbnail BLOB);
        CREATE TABLE IF NOT EXISTS tag_runs(path TEXT, model_signature TEXT, stamp TEXT, cache_key TEXT,
            PRIMARY KEY(path, model_signature));
        CREATE TABLE IF NOT EXISTS note_meta(note_id TEXT PRIMARY KEY, category TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS history_meta(history_id INTEGER PRIMARY KEY, title TEXT, category TEXT);
        CREATE TABLE IF NOT EXISTS app_state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS library_hidden(path TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS source_identity(path TEXT PRIMARY KEY, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tag_search(path TEXT PRIMARY KEY, stamp TEXT NOT NULL, text TEXT NOT NULL);
        ''')

    def save_asset(self, path, metadata, draft, negative, memo):
        self.db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?)', (str(path), json_text(metadata), draft, negative, memo))
        self.db.commit()

    def state(self,key,value=None):
        if value is not None:
            with self.db:self.db.execute('INSERT OR REPLACE INTO app_state VALUES(?,?)',(key,json_text(value)))
            return value
        row=self.db.execute('SELECT value FROM app_state WHERE key=?',(key,)).fetchone()
        if not row:return None
        try:return json.loads(row[0])
        except ValueError:return None

    def remember_source(self,path,digest):
        with self.db:self.db.execute('INSERT OR REPLACE INTO source_identity VALUES(?,?)',(str(path),digest))

    def asset(self, path):
        return self.db.execute('SELECT draft,negative,memo FROM assets WHERE path=?', (str(path),)).fetchone()

    def save_note(self, title, body, note_id=None, category=None):
        note_id = note_id or uuid.uuid4().hex
        now = datetime.now().isoformat(timespec='seconds')
        encoded = json_text(body)
        prior=self.db.execute('SELECT category,archived FROM note_meta WHERE note_id=?',(note_id,)).fetchone()
        category=normalize_category(category if category is not None else (prior[0] if prior else ''))
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?)', (note_id, title, encoded, now))
            self.db.execute('INSERT OR REPLACE INTO note_meta VALUES(?,?,?)',(note_id,category,prior[1] if prior else 0))
            cursor=self.db.execute('INSERT INTO history(note_id,body,updated) VALUES(?,?,?)', (note_id, encoded, now))
            self.db.execute('INSERT INTO history_meta VALUES(?,?,?)',(cursor.lastrowid,title,category))
        return note_id

    def notes(self, query=''):
        return [(r[0],r[1],r[2]) for r in self.note_entries(query)]

    def note_entries(self,query='',archived=False):
        return self.db.execute('SELECT n.id,n.title,n.body,COALESCE(m.category,\'\'),COALESCE(m.archived,0) '
            'FROM notes n LEFT JOIN note_meta m ON m.note_id=n.id '
            'WHERE COALESCE(m.archived,0)=? AND (n.title LIKE ? OR n.body LIKE ? OR m.category LIKE ?) '
            'ORDER BY n.updated DESC,n.rowid DESC',(int(archived),*(['%'+query+'%']*3))).fetchall()

    def note(self,note_id):
        return self.db.execute('SELECT n.id,n.title,n.body,COALESCE(m.category,\'\'),COALESCE(m.archived,0) '
            'FROM notes n LEFT JOIN note_meta m ON n.id=m.note_id WHERE n.id=?',(note_id,)).fetchone()

    def archive_note(self,note_id,archived=True):
        record=self.note(note_id)
        if not record:raise ValueError('노트를 찾을 수 없습니다.')
        with self.db:self.db.execute('INSERT OR REPLACE INTO note_meta VALUES(?,?,?)',(note_id,record[3],int(archived)))

    def revisions(self,note_id):
        return self.db.execute('SELECT h.id,h.updated,h.body,COALESCE(m.title,n.title),COALESCE(m.category,\'\') '
            'FROM history h JOIN notes n ON n.id=h.note_id LEFT JOIN history_meta m ON m.history_id=h.id '
            'WHERE h.note_id=? ORDER BY h.id DESC',(note_id,)).fetchall()

    def restore_revision(self,note_id,revision_id):
        revision=next((r for r in self.revisions(note_id) if r[0]==revision_id),None)
        if revision is None:raise ValueError('이 노트에 속한 버전이 아닙니다.')
        self.save_note(revision[3],json.loads(revision[2]),note_id,revision[4])
        return self.note(note_id)

    def note_import_index(self):
        """Comparable bodies of every stored note (archived included) by (category, title)."""
        index={}
        for title,body,category in self.db.execute('SELECT n.title,n.body,COALESCE(m.category,\'\') FROM notes n LEFT JOIN note_meta m ON m.note_id=n.id'):
            try:content=note_content(json.loads(body))
            except (ValueError,TypeError,AttributeError):content=None
            index.setdefault((category,title),[]).append(content)
        return index

    def plan_note_import(self,paths,base=None):
        """Read and classify note JSON files without writing anything."""
        plan={'base':str(base) if base else None,'scanned':0,'import':[],'skipped':[],'failed':[]}
        index=self.note_import_index()
        for path in paths:
            path=Path(path);plan['scanned']+=1
            reason=note_import_exclusion(path,base)
            if reason:plan['skipped'].append({'path':str(path),'kind':'excluded','reason':reason});continue
            try:
                if path.stat().st_size>NOTE_IMPORT_MAX_BYTES:
                    plan['skipped'].append({'path':str(path),'kind':'not_note','reason':'BMK 노트로 보기에 너무 큰 파일'});continue
                doc=json.loads(path.read_text(encoding='utf-8-sig'))
                reason=note_skip_reason(doc)
                if reason:plan['skipped'].append({'path':str(path),'kind':'not_note','reason':reason});continue
                validate_note(doc)
                title=path.stem;category=doc.get('_studio_category','')
                if not category and base:
                    relative=path.parent.resolve().relative_to(Path(base).resolve())
                    category='' if str(relative)=='.' else relative.as_posix()
                category=normalize_category(category)
                existing=note_import_conflict(index,title,category,doc)
                if existing:plan['skipped'].append({'path':str(path),'title':title,'category':category,**existing});continue
                index.setdefault((category,title),[]).append(note_content(doc))
                plan['import'].append({'path':str(path),'title':title,'category':category,'doc':doc})
            except Exception as exc:plan['failed'].append({'path':str(path),'error':str(exc)})
        return plan

    def apply_note_import(self,plan):
        """Create the planned notes; never replaces a note that appeared since planning."""
        report={'base':plan['base'],'scanned':plan['scanned'],'imported':[],'skipped':list(plan['skipped']),'failed':list(plan['failed'])}
        # One import at a time, so a second run started meanwhile sees the first run's notes.
        with NOTE_IMPORT_LOCK:
            index=self.note_import_index()
            for entry in plan['import']:
                try:
                    existing=note_import_conflict(index,entry['title'],entry['category'],entry['doc'])
                    if existing:report['skipped'].append({'path':entry['path'],'title':entry['title'],'category':entry['category'],**existing});continue
                    nid=self.save_note(entry['title'],entry['doc'],category=entry['category'])
                    index.setdefault((entry['category'],entry['title']),[]).append(note_content(entry['doc']))
                    report['imported'].append({'path':entry['path'],'id':nid})
                except Exception as exc:report['failed'].append({'path':entry['path'],'error':str(exc)})
        return report

    def import_note_files(self,paths,base=None):
        return self.apply_note_import(self.plan_note_import(paths,base))

    def cache(self, key, scores=None):
        if scores is not None:
            self.db.execute('INSERT OR REPLACE INTO tags VALUES(?,?)', (key, json_text(scores)))
            self.db.commit()
            return scores
        row = self.db.execute('SELECT scores FROM tags WHERE cache_key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def index_image(self, path, stamp, searchable, thumbnail):
        self.db.execute('INSERT OR REPLACE INTO image_index VALUES(?,?,?,?)', (str(path), stamp, searchable, thumbnail))
        self.db.commit()

    def indexed_images(self):
        return self.db.execute('SELECT path,stamp,searchable,thumbnail FROM image_index WHERE path NOT IN (SELECT path FROM library_hidden) ORDER BY rowid DESC').fetchall()
    def indexed_references(self):
        return self.db.execute('SELECT path,stamp FROM image_index WHERE path NOT IN (SELECT path FROM library_hidden) ORDER BY rowid DESC').fetchall()

    def hidden_paths(self):return {r[0] for r in self.db.execute('SELECT path FROM library_hidden')}
    def hide_paths(self,paths):
        with self.db:self.db.executemany('INSERT OR IGNORE INTO library_hidden VALUES(?)',[(str(p),) for p in paths])
    def reveal_paths(self,paths):
        with self.db:self.db.executemany('DELETE FROM library_hidden WHERE path=?',[(str(p),) for p in paths])
    def search_extras(self,path=None):
        result={}
        where=' WHERE path=?' if path is not None else '';params=(str(path),) if path is not None else ()
        for key,draft,negative,memo in self.db.execute('SELECT path,draft,negative,memo FROM assets'+where,params):
            result[key]={'work':'\n'.join(v or '' for v in (draft,negative,memo))}
        for key,stamp,text in self.db.execute('SELECT path,stamp,text FROM tag_search'+where,params):
            result.setdefault(key,{}).update({'tags':text,'stamp':stamp})
        return result
    def needs_tag_search(self):
        return self.db.execute('SELECT 1 FROM tag_runs WHERE path NOT IN (SELECT path FROM tag_search) LIMIT 1').fetchone() is not None
    def backfill_tag_search(self):
        rows=self.db.execute('SELECT r.path,r.stamp,t.scores FROM tag_runs r JOIN tags t ON t.cache_key=r.cache_key '
                             'WHERE r.path NOT IN (SELECT path FROM tag_search) ORDER BY r.rowid DESC')
        seen=set()
        with self.db:
            for path,stamp,scores in rows:
                if path in seen:continue
                seen.add(path)
                try:text=searchable_tags(json.loads(scores))
                except (ValueError,TypeError,AttributeError):continue
                self.db.execute('INSERT OR IGNORE INTO tag_search VALUES(?,?,?)',(path,stamp,text))
        return len(seen)

    def record_tag_run(self, path, model_signature, stamp, key, result):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO tags VALUES(?,?)', (key,json_text(result)))
            self.db.execute('INSERT OR REPLACE INTO tag_runs VALUES(?,?,?,?)', (str(path),model_signature,stamp,key))
            self.db.execute('INSERT OR REPLACE INTO tag_search VALUES(?,?,?)',(str(path),stamp,searchable_tags(result)))

    def saved_tags(self, path, model_signature, stamp):
        row=self.db.execute('SELECT t.scores FROM tag_runs r JOIN tags t ON t.cache_key=r.cache_key '
                            'WHERE r.path=? AND r.model_signature=? AND r.stamp=?',
                            (str(path),model_signature,stamp)).fetchone()
        return json.loads(row[0]) if row else None

def file_stamp(path):
    st=Path(path).stat()
    return f'{st.st_mtime_ns}:{st.st_size}'

def searchable_tags(result):
    names=[]
    for item in result.get('scores',[]):
        if item.get('category')==9:continue
        threshold=.75 if item.get('category')==4 else .35
        if item.get('score',0)>=threshold and isinstance(item.get('tag'),str):
            names.extend((item['tag'],item['tag'].replace('_',' ')))
    return '\n'.join(names).casefold()

def normalize_category(category):
    return '/'.join(p.strip() for p in str(category).replace('\\','/').split('/') if p.strip() and p.strip() not in ('.','..'))

def validate_note(doc):
    if not isinstance(doc,dict):raise ValueError('노트는 JSON 객체여야 합니다.')
    for key in ('prompt','negative','notes','_studio_category'):
        if key in doc and not isinstance(doc[key],str):raise ValueError(f'{key} 필드는 문자열이어야 합니다.')
    return doc

# BMK notes (ComfyUI bmk_notes and this app's export) carry prompt/negative/notes text,
# usually with loras/params/ui. Anything else found in a scanned folder is not imported.
NOTE_TEXT_FIELDS=('prompt','negative','notes')
NOTE_MARKER_FIELDS=('loras','params','ui','_studio_category','_studio_image_transfers')
NOTE_APP_FIELDS=('schema','source')
NOTE_IMPORT_CONFIRM=200
NOTE_IMPORT_MAX_BYTES=5*1024*1024
NOTE_IMPORT_LOCK=threading.Lock()
NOTE_SAME='같은 분류·제목에 내용이 같은 노트가 이미 있음'
NOTE_CONFLICT='같은 분류·제목의 노트가 있지만 내용이 다름 · 기존 노트를 덮어쓰지 않음'

def note_json_files(folder):
    return sorted(Path(folder).rglob('*.json'))

def note_import_exclusion(path,base=None):
    """Why a file is never read as a note: BMK folder settings and the folder's trash."""
    path=Path(path)
    if path.name.casefold().startswith('.bmk_'):return 'BMK 노트 폴더 설정 파일 (.bmk_*)'
    if base is None:return None
    try:parts=path.parent.relative_to(base).parts
    except ValueError:
        try:parts=path.parent.resolve().relative_to(Path(base).resolve()).parts
        except ValueError:parts=()
    if any(part.casefold()=='.trash' for part in parts):return '휴지통 폴더 (.trash)'
    return None

def note_skip_reason(doc):
    """Why parsed JSON is not a BMK note (workflow, API prompt, other data), or None."""
    if not isinstance(doc,dict):return 'JSON 객체가 아님'
    if isinstance(doc.get('nodes'),list) and 'links' in doc:return 'ComfyUI 워크플로'
    if any(isinstance(value,dict) and 'class_type' in value for value in doc.values()):return 'ComfyUI API 프롬프트'
    if not any(isinstance(doc.get(key),str) for key in NOTE_TEXT_FIELDS):return 'BMK 노트 필드(prompt·negative·notes) 없음'
    # A lone "prompt"/"notes" string is common in settings and bot data; a note has more of its fields.
    if sum(key in doc for key in NOTE_TEXT_FIELDS)<2 and not any(key in doc for key in NOTE_MARKER_FIELDS):return 'BMK 노트 형식이 아님 (노트 필드 하나만 있음)'
    return None

def note_content(doc):
    """Note body compared on re-import; _studio_category only routes the note to a folder."""
    return {key:value for key,value in doc.items() if key!='_studio_category'}

def same_note(doc,body):
    """Whether a stored body matches the file; keys the editor adds on save (schema, source) count only when the file has them."""
    if not isinstance(body,dict):return False
    content=note_content(doc)
    return {key:value for key,value in body.items() if key in content or key not in NOTE_APP_FIELDS}==content

def note_import_conflict(index,title,category,doc):
    bodies=index.get((category,title))
    if not bodies:return None
    if any(same_note(doc,body) for body in bodies):return {'kind':'same','reason':NOTE_SAME}
    return {'kind':'conflict','reason':NOTE_CONFLICT}

def note_import_question(plan):
    from collections import Counter
    # Full folder paths make a too-high import root visible (e.g. "ComfyUI/user/default/bmk_notes/캐릭터").
    folders=Counter(entry['category'] or '(최상위)' for entry in plan['import'])
    lines=['폴더: '+plan['base'] if plan['base'] else f"선택한 파일 {plan['scanned']:,}개",
           f"JSON 파일 {plan['scanned']:,}개를 확인했습니다.",
           f"새로 가져올 노트: {len(plan['import']):,}개",
           f"건너뜀: {len(plan['skipped']):,}개 / 실패: {len(plan['failed']):,}개",
           '노트 폴더: '+', '.join(f'{name} {count:,}개' for name,count in folders.most_common(5))+(f' 외 {len(folders)-5:,}곳' if len(folders)>5 else ''),
           '','원본 JSON 파일은 바꾸지 않고 앱의 노트 목록에 새 노트로 복사합니다. 가져올까요?']
    return '\n'.join(lines)

def note_import_summary(report,limit=50):
    """(status line, message, details) for a finished import report."""
    from collections import Counter
    status=f"노트 가져오기: 성공 {len(report['imported']):,}개 / 건너뜀 {len(report['skipped']):,}개 / 실패 {len(report['failed']):,}개"
    lines=(['폴더: '+report['base']] if report.get('base') else [])+[status]
    reasons=Counter(item['reason'] for item in report['skipped'])
    lines+=[f'· 건너뜀 {count:,}개: {reason}' for reason,count in reasons.most_common()]
    if any(item['kind']=='conflict' for item in report['skipped']):lines.append('내용이 다른 노트는 기존 노트와 이력을 그대로 두었습니다. 아래 파일 목록에서 확인하세요.')
    details=[]
    def shown(path):
        if not report.get('base'):return path
        try:return str(Path(path).relative_to(report['base']))
        except ValueError:return path
    def section(title,rows):
        if not rows:return
        details.extend(['',f'[{title}] {len(rows):,}개']+rows[:limit]+([f'… 외 {len(rows)-limit:,}개'] if len(rows)>limit else []))
    section('실패',[f"{shown(item['path'])}: {item['error']}" for item in report['failed']])
    section('내용이 달라 건너뜀',[f"{shown(item['path'])} → {item['category'] or '(최상위)'} / {item['title']}" for item in report['skipped'] if item['kind']=='conflict'])
    for reason,_ in reasons.most_common():
        if reason!=NOTE_CONFLICT:section('건너뜀 · '+reason,[shown(item['path']) for item in report['skipped'] if item['reason']==reason])
    return status,'\n'.join(lines),'\n'.join(details).strip()

def unique_path(folder, stem, suffix='.png'):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (stem + suffix)
    i = 2
    while path.exists():
        path = folder / f'{stem}_{i}{suffix}'
        i += 1
    return path

def save_derived(image, destination, record):
    destination = Path(destination)
    base=destination;counter=1
    while True:
        sidecar=Path(str(destination)+'.bmk.json')
        if destination.exists() or sidecar.exists():
            counter+=1;destination=base.with_name(f'{base.stem}_{counter}{base.suffix}');continue
        try:output=destination.open('xb')
        except FileExistsError:continue
        try:
            try:metadata=sidecar.open('x',encoding='utf-8')
            except FileExistsError:
                output.close();destination.unlink();continue
            try:
                with output,metadata:
                    image.save(output,format='PNG');metadata.write(json_text(record))
            except Exception:
                destination.unlink(missing_ok=True);sidecar.unlink(missing_ok=True);raise
        except Exception:
            output.close();destination.unlink(missing_ok=True);raise
        return destination

def crop_image(image, box, rotation=0):
    rotated = image.rotate(-rotation, expand=True)
    x, y, w, h = map(int, box)
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > rotated.width or y+h > rotated.height:
        raise ValueError('크롭 영역이 이미지 범위를 벗어납니다.')
    return rotated.crop((x, y, x+w, y+h))

def stitch_image(original, edited, box, rotation=0, feather=24, mask=None, offset=(0,0), angle=0, scale=1):
    if not all(math.isfinite(float(v)) for v in (*offset,angle,scale)) or not .1<=scale<=4:
        raise ValueError('위치/각도는 유한한 값, 배율은 0.1~4여야 합니다.')
    base = original.convert('RGBA').rotate(-rotation, expand=True)
    x, y, w, h = map(int, box)
    crop_image(original, box, rotation)  # Validate geometry before modifying anything.
    scaled=(max(1,round(w*scale)),max(1,round(h*scale)))
    radians=math.radians(angle)
    bound_w=math.ceil(abs(scaled[0]*math.cos(radians))+abs(scaled[1]*math.sin(radians)))+2
    bound_h=math.ceil(abs(scaled[0]*math.sin(radians))+abs(scaled[1]*math.cos(radians)))+2
    if w*h>64_000_000 or bound_w*bound_h>64_000_000:raise ValueError('합성 패치가 64 MP 제한을 초과합니다.')
    patch = edited.convert('RGBA').resize((w,h), Image.Resampling.LANCZOS)
    yy, xx = np.mgrid[:h,:w]
    ramp = np.ones((h,w), dtype=np.float32)
    if feather > 0:
        distances = []
        if x > 0: distances.append(xx+1)
        if y > 0: distances.append(yy+1)
        if x+w < base.width: distances.append(w-xx)
        if y+h < base.height: distances.append(h-yy)
        for d in distances:
            ramp = np.minimum(ramp, d/feather)
    alpha = np.asarray(patch.getchannel('A'), dtype=np.float32)*ramp
    if mask is not None:
        alpha*=np.asarray(mask.convert('L').resize((w,h),Image.Resampling.BILINEAR),dtype=np.float32)/255
    patch.putalpha(Image.fromarray(np.uint8(np.clip(alpha,0,255))))
    if scale!=1:patch=patch.resize(scaled,Image.Resampling.LANCZOS)
    if angle%360:patch=patch.rotate(-angle,Image.Resampling.BICUBIC,expand=True)
    left=round(x+offset[0]+(w-patch.width)/2);top=round(y+offset[1]+(h-patch.height)/2)
    right=min(base.width,left+patch.width);bottom=min(base.height,top+patch.height)
    clipped_left=max(0,left);clipped_top=max(0,top)
    if right>clipped_left and bottom>clipped_top:
        visible=patch.crop((clipped_left-left,clipped_top-top,right-left,bottom-top))
        base.alpha_composite(visible,(clipped_left,clipped_top))
    return base.rotate(rotation, expand=True)

def low_frequency(a, levels):
    a = a.copy()
    for i in range(levels):
        r = 2**i
        for axis in (0,1):
            pads = [(0,0)]*3
            pads[axis] = (r,r)
            p = np.pad(a, pads, mode='edge')
            n = a.shape[axis]
            def part(start):
                slices = [slice(None)]*3
                slices[axis] = slice(start,start+n)
                return p[tuple(slices)]
            a = (part(0)+2*part(r)+part(2*r))*.25
    return a

def tone_delta(content, reference, levels=5, luminance=False):
    a = np.asarray(content.convert('RGB'), dtype=np.float32)/255
    b = np.asarray(reference.convert('RGB').resize(content.size, Image.Resampling.BICUBIC), dtype=np.float32)/255
    if luminance:
        weights = np.array([.2126,.7152,.0722], dtype=np.float32)
        delta = low_frequency((b@weights)[...,None],levels)-low_frequency((a@weights)[...,None],levels)
    else:
        delta = low_frequency(b,levels)-low_frequency(a,levels)
    return delta

def apply_tone_delta(content,delta,strength):
    a=np.asarray(content.convert('RGB'),dtype=np.float32)/255
    result = Image.fromarray(np.uint8(np.rint(np.clip(a+strength*delta,0,1)*255))).convert('RGBA')
    result.putalpha(content.convert('RGBA').getchannel('A'))
    if content.info.get('icc_profile'):result.info['icc_profile']=content.info['icc_profile']
    return result

def tone_restore(content,reference,strength=.8,levels=5,luminance=False):
    return apply_tone_delta(content,tone_delta(content,reference,levels,luminance),strength)

def resize_image(image,width,height,mode='contain',background='white'):
    width,height=int(width),int(height)
    if min(width,height)<1 or width*height>64_000_000:raise ValueError('출력은 양수 크기, 최대 6,400만 픽셀까지 지원합니다.')
    image=image.convert('RGBA')
    if mode=='stretch':return image.resize((width,height),Image.Resampling.LANCZOS)
    if mode=='cover':return ImageOps.fit(image,(width,height),method=Image.Resampling.LANCZOS)
    if mode!='contain':raise ValueError('지원하지 않는 리사이즈 방식입니다.')
    scale=min(width/image.width,height/image.height)
    scaled=image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(width,height),(0,0,0,0) if background=='transparent' else background)
    canvas.alpha_composite(scaled,((width-scaled.width)//2,(height-scaled.height)//2))
    return canvas
