"""Bounded thumbnail pages and worker-side SQL search over persisted metadata."""
import sqlite3
from contextlib import closing
from collections import OrderedDict
from PySide6.QtCore import QThread,Signal

class ThumbnailPages:
    def __init__(self,database,page_size=64,max_pages=8):
        self.database=database;self.page_size=page_size;self.max_pages=max_pages;self.pages=OrderedDict();self.reads=0
    def clear(self):self.pages.clear()
    def get(self,path):
        # Lightweight path lookups remain indexed; only the containing blob page is read.
        with closing(sqlite3.connect(self.database)) as db:
            row=db.execute('SELECT rowid FROM image_index WHERE path=?',(path,)).fetchone()
            if row is None:return b''
            page=row[0]//self.page_size
            if page not in self.pages:
                start=page*self.page_size
                self.pages[page]={p:blob for p,blob in db.execute('SELECT path,thumbnail FROM image_index WHERE rowid>=? AND rowid<?',(start,start+self.page_size))}
                self.reads+=1
                while len(self.pages)>self.max_pages:self.pages.popitem(last=False)
            self.pages.move_to_end(page)
            return self.pages[page].get(path,b'')

class SearchJob(QThread):
    result=Signal(object);failed=Signal(str)
    def __init__(self,database,references,query,generation,parent=None,filters=None):
        super().__init__(parent);self.database=database;self.references=references;self.query=query;self.generation=generation
        self.filters=dict(filters or {})
    def run(self):
        db=sqlite3.connect(self.database)
        try:
            db.set_progress_handler(lambda:int(self.isInterruptionRequested()),1000)
            db.create_function('casefold',1,lambda value:(value or '').casefold())
            from .organize import field
            db.create_function('metadata_field',2,field)
            from .discovery import date_value
            db.create_function('image_date',3,date_value)
            db.execute('CREATE TEMP TABLE refs(path TEXT PRIMARY KEY,title TEXT)')
            db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?)',self.references)
            # SQL streams disk pages. Python receives only matching references, never all blobs/text.
            text="casefold(r.title||char(10)||coalesce(i.searchable,'')||char(10)||coalesce(a.draft,'')||char(10)||coalesce(a.negative,'')||char(10)||coalesce(a.memo,'')||char(10)||coalesce(t.text,''))"
            scope=self.filters.get('scope','all')
            text={'filename':'casefold(r.title)','positive':"metadata_field(i.searchable,'positive')",'negative':"metadata_field(i.searchable,'negative')",'work':"casefold(coalesce(a.draft,'')||char(10)||coalesce(a.negative,'')||char(10)||coalesce(a.memo,''))",'tags':"casefold(t.text)"}.get(scope,text)
            words=self.query.casefold().split();clauses=[f'instr({text},?)>0' for word in words];params=list(words)
            if self.filters.get('source'):
                clauses.append("instr(metadata_field(i.searchable,'source'),?)>0");params.append(self.filters['source'].casefold())
            if self.filters.get('models'):
                clauses.append("instr(metadata_field(i.searchable,'models'),?)>0");params.append(self.filters['models'].casefold())
            if self.filters.get('pixels'):
                clauses.append("metadata_field(i.searchable,'pixels')>=?");params.append(int(self.filters['pixels']))
            if self.filters.get('days'):
                import time
                clauses.append("CAST(substr(i.stamp,1,instr(i.stamp,':')-1) AS INTEGER)>=?");params.append(int((time.time()-int(self.filters['days'])*86400)*1e9))
            if self.filters.get('aspect'):
                clauses.append("metadata_field(i.searchable,'aspect')=?");params.append(self.filters['aspect'])
            if self.filters.get('date_unknown'):
                clauses.append("image_date(i.searchable,i.stamp,?)=''");params.append(self.filters.get('date_kind','modified'))
            else:
                for key,operator in [('date_from','>='),('date_to','<=')]:
                    if self.filters.get(key):
                        clauses.append(f"image_date(i.searchable,i.stamp,?)<>'' AND image_date(i.searchable,i.stamp,?){operator}?")
                        params.extend([self.filters.get('date_kind','modified')]*2+[self.filters[key]])
            if self.filters.get('favorite'):clauses.append('EXISTS (SELECT 1 FROM favorites f WHERE f.path=r.path)')
            if self.filters.get('rating'):
                clauses.append('EXISTS (SELECT 1 FROM favorites f WHERE f.path=r.path AND f.rating>=?)');params.append(int(self.filters['rating']))
            if self.filters.get('collection'):
                clauses.append('EXISTS (SELECT 1 FROM collection_items c WHERE c.path=r.path AND c.name=?)');params.append(self.filters['collection'])
            if self.filters.get('tagged'):clauses.append('t.path IS '+('NULL' if self.filters['tagged']=='no' else 'NOT NULL'))
            where=' AND '.join(clauses) or '1'
            matches={path for (path,) in db.execute('SELECT r.path FROM refs r LEFT JOIN image_index i ON i.path=r.path LEFT JOIN assets a ON a.path=r.path LEFT JOIN tag_search t ON t.path=r.path AND t.stamp=i.stamp WHERE '+where,params)}
            if not self.isInterruptionRequested():self.result.emit((self.generation,matches))
        except sqlite3.OperationalError as exc:
            if not self.isInterruptionRequested():self.failed.emit(str(exc))
        finally:db.close()

class SearchExtras(OrderedDict):
    """Compatibility cache for the active work/tag callbacks, bounded to 128 paths."""
    def __init__(self,store):super().__init__();self.store=store
    def get(self,key,default=None):return self.setdefault(key,default if default is not None else {})
    def setdefault(self,key,default=None):
        if key not in self:
            value=self.store.search_extras(key).get(key,default if default is not None else {})
            self[key]=value
            while len(self)>128:self.popitem(last=False)
        self.move_to_end(key);return self[key]
