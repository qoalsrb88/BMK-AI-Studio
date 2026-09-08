"""Read-only discovery helpers: dates, completion and visual candidate groups."""
import json,re,sqlite3,hashlib,math
from datetime import datetime
from collections import Counter
from contextlib import closing
import numpy as np
from .organize import metadata_record,field
from .core import file_stamp,load_image

SCHEMA='''
CREATE TABLE IF NOT EXISTS visual_signatures(path TEXT PRIMARY KEY,stamp TEXT,hash TEXT,aspect REAL,color TEXT);
CREATE TABLE IF NOT EXISTS semantic_vectors(path TEXT,source TEXT,signature TEXT,model TEXT,vector BLOB,PRIMARY KEY(path,source));
CREATE TABLE IF NOT EXISTS large_thumbnails(path TEXT PRIMARY KEY,stamp TEXT,thumbnail BLOB,used REAL);
'''

def generated_date(searchable):
    """Only explicit creation fields; no filename, seed or file-time guessing."""
    record=metadata_record(searchable);raw=record.get('raw',{})
    if not isinstance(raw,dict):return ''
    raw={str(key).casefold():value for key,value in raw.items()};exif=raw.get('exif',{});xmp=record.get('xmp',{})
    candidates=[raw.get('creation time'),raw.get('datetimeoriginal')]
    if isinstance(exif,dict):candidates.append({str(k).casefold():v for k,v in exif.items()}.get('datetimeoriginal'))
    if isinstance(xmp,dict):
        xmp={str(k).casefold():v for k,v in xmp.items()};candidates.extend(xmp.get(k) for k in ('createdate','create_date','created','datecreated'))
    for value in candidates:
        if not isinstance(value,str):continue
        match=re.match(r'^(\d{4})[-:](\d{2})[-:](\d{2})(?:[ Tt]|$)',value.strip())
        if match:
            try:return datetime(*map(int,match.groups())).strftime('%Y-%m-%d')
            except ValueError:pass
    return ''

def date_value(searchable,stamp,kind):
    if kind=='generated':return generated_date(searchable)
    if not isinstance(stamp,str):return ''
    try:return datetime.fromtimestamp(int(stamp.split(':')[0])/1e9).strftime('%Y-%m-%d')
    except (ValueError,TypeError,OverflowError,OSError):return ''

def timeline(database,kind,cancelled=lambda:False):
    counts=Counter();missing=0
    with closing(sqlite3.connect(database)) as db:
        for searchable,stamp in db.execute('SELECT searchable,stamp FROM image_index WHERE path NOT IN (SELECT path FROM library_hidden)'):
            if cancelled():break
            value=date_value(searchable,stamp,kind)
            if value:counts[value[:7]]+=1
            else:missing+=1
    return sorted(counts.items(),reverse=True),missing

def completions(database,prefix,scope='all',cancelled=lambda:False):
    tokens=prefix.rsplit(' ',1);head=tokens[0]+' ' if len(tokens)==2 else '';needle=tokens[-1].casefold()
    if not needle:return []
    counts=Counter()
    with closing(sqlite3.connect(database)) as db:
        rows=db.execute("SELECT i.path,i.searchable,a.draft,a.negative,t.text FROM image_index i LEFT JOIN assets a ON a.path=i.path LEFT JOIN tag_search t ON t.path=i.path AND t.stamp=i.stamp WHERE i.path NOT IN (SELECT path FROM library_hidden)")
        for path,metadata,draft,negative,tags in rows:
            if cancelled():return []
            source={'filename':path.replace('\\','/').rsplit('/',1)[-1],'positive':field(metadata,'positive'),'negative':field(metadata,'negative'),'work':(draft or '')+' '+(negative or ''),'tags':tags or ''}
            text=source.get(scope,' '.join(source.values()))
            words={word for word in re.findall(r'[\w-]{2,80}',text.casefold()) if word.startswith(needle)}
            # Per-file frequency, bounded candidate memory even for huge libraries.
            for word in words:
                if word in counts or len(counts)<5000:counts[word]+=1
    return [head+word for word,count in sorted(counts.items(),key=lambda item:(-item[1],item[0]))[:20]]

def visual_signature(image):
    from PIL import Image
    gray=np.asarray(image.convert('L').resize((32,32),Image.Resampling.LANCZOS),dtype=np.float32)
    matrix=np.cos(np.pi/32*(np.arange(32)+.5)[None,:]*np.arange(8)[:,None])
    low=(matrix@gray@matrix.T).ravel()[1:];bits=low>np.median(low)
    value=sum(int(bit)<<n for n,bit in enumerate(bits))
    color=np.asarray(image.convert('RGB').resize((1,1)),dtype=np.float32).ravel()/255
    return value,image.width/image.height,color.tolist()

class HashTree:
    def __init__(self):self.root=None
    def add(self,value,index):
        if self.root is None:self.root=[value,[index],{}];return
        node=self.root
        while True:
            distance=(node[0]^value).bit_count()
            if distance==0:node[1].append(index);return
            if distance not in node[2]:node[2][distance]=[value,[index],{}];return
            node=node[2][distance]
    def find(self,value,radius):
        stack=[self.root] if self.root else []
        while stack:
            node=stack.pop();distance=(node[0]^value).bit_count()
            if distance<=radius:yield from node[1]
            stack.extend(child for edge,child in node[2].items() if distance-radius<=edge<=distance+radius)

def similar_groups(database,paths,radius=8,cancelled=lambda:False,progress=lambda value:None):
    tree=HashTree();anchors=[];groups=[];failed=[]
    with closing(sqlite3.connect(database)) as db:
        for n,path in enumerate(paths):
            if cancelled():break
            try:
                stamp=file_stamp(path);row=db.execute('SELECT hash,aspect,color FROM visual_signatures WHERE path=? AND stamp=?',(path,stamp)).fetchone()
                if row:value,aspect,color=int(row[0],16),row[1],json.loads(row[2])
                else:
                    value,aspect,color=visual_signature(load_image(path))
                    if stamp!=file_stamp(path):raise ValueError('읽는 중 변경됨')
                    with db:db.execute('INSERT OR REPLACE INTO visual_signatures VALUES(?,?,?,?,?)',(path,stamp,hex(value),aspect,json.dumps(color)))
                match=None
                for index in tree.find(value,radius):
                    anchor=anchors[index]
                    if abs(math.log(aspect/anchor[1]))<.15 and np.linalg.norm(np.asarray(color)-anchor[2])<.25:match=index;break
                if match is None:
                    match=len(anchors);anchors.append((value,aspect,np.asarray(color)));groups.append([]);tree.add(value,match)
                groups[match].append(path)
            except Exception as exc:failed.append((path,str(exc)))
            progress((n+1,len(paths),'시각 유사도 색인'))
    return {'groups':[group for group in groups if len(group)>1],'failed':failed,'cancelled':cancelled()}
