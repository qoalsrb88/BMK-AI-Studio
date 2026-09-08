"""Personal classification is separate from source metadata and model ratings."""
import json

SCHEMA='''
CREATE TABLE IF NOT EXISTS favorites(path TEXT PRIMARY KEY, rating INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS collections(name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS collection_items(name TEXT NOT NULL,path TEXT NOT NULL,PRIMARY KEY(name,path));
'''

def metadata_record(searchable):
    try:
        value=json.loads((searchable or '').partition('\n')[2])
        return value if isinstance(value,dict) else {}
    except (ValueError,TypeError):return {}

def field(searchable,name):
    record=metadata_record(searchable)
    if name in ('positive','negative'):return str(record.get(name,'')).casefold()
    if name=='source':return str(record.get('source','')).casefold()+' '+str(record.get('settings_origin','')).casefold()
    if name=='models':
        names=[]
        def walk(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if str(key).casefold() in ('model','model name','model_name','ckpt_name','lora_name','checkpoint') and isinstance(item,str):names.append(item)
                    elif isinstance(item,(dict,list)):walk(item)
            elif isinstance(value,list):
                for item in value:walk(item)
        walk(record.get('settings',{}));walk(record.get('raw',{}))
        # Serialized Comfy graphs are candidates, never asserted to be the active branch.
        raw=record.get('raw',{})
        if isinstance(raw,dict) and isinstance(raw.get('prompt'),str):
            try:walk(json.loads(raw['prompt']))
            except ValueError:pass
        return '\n'.join(names).casefold()
    if name=='pixels':
        size=record.get('size')
        return size[0]*size[1] if isinstance(size,list) and len(size)==2 and all(isinstance(n,(int,float)) and n>0 for n in size) else 0
    if name=='aspect':
        size=record.get('size')
        if isinstance(size,list) and len(size)==2 and all(isinstance(n,(int,float)) and n>0 for n in size):
            return 'portrait' if size[0]<size[1] else 'landscape' if size[0]>size[1] else 'square'
        return 'unknown'
    return ''

def set_favorites(db,paths,on):
    with db:
        if on:db.executemany('INSERT OR IGNORE INTO favorites(path) VALUES(?)',[(p,) for p in paths])
        else:db.executemany('DELETE FROM favorites WHERE path=?',[(p,) for p in paths])

def set_rating(db,paths,rating):
    if rating not in range(6):raise ValueError('별점은 0~5입니다.')
    # Rated items also belong to favorites; zero removes only the rating.
    with db:db.executemany('INSERT INTO favorites VALUES(?,?) ON CONFLICT(path) DO UPDATE SET rating=excluded.rating',[(p,rating) for p in paths])
