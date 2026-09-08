"""Bounded local wildcard expansion and safe derived-output naming."""
import random,re,string,unicodedata
from datetime import datetime
from pathlib import Path

TOKEN=re.compile(r'__([\w/-]+)__')

def wildcard_path(folder,name):
    root=Path(folder).resolve()
    if not re.fullmatch(r'[\w/-]+',name) or name.startswith('/') or any(p in ('','..','.') for p in name.split('/')):
        raise ValueError('와일드카드 이름에는 문자/숫자/밑줄/하위 폴더만 사용하세요.')
    path=(root/(name+'.txt')).resolve()
    try:path.relative_to(root)
    except ValueError:raise ValueError('와일드카드 폴더 밖의 파일은 읽을 수 없습니다.')
    return path

def expand_wildcards(text,folder,seed=0):
    rng=random.Random(int(seed));used=[];cache={}
    def expand(value,stack=()):
        if len(stack)>8:raise ValueError('와일드카드 중첩은 최대 8단계입니다.')
        if len(value)>100000:raise ValueError('확장 결과가 너무 깁니다 (최대 100,000자).')
        def choose(match):
            name=match.group(1)
            if name in stack:raise ValueError('와일드카드 순환 참조: '+' → '.join((*stack,name)))
            if name not in cache:
                path=wildcard_path(folder,name)
                if not path.is_file():raise ValueError(f'와일드카드 파일이 없습니다: {name}.txt')
                if path.stat().st_size>1024*1024:raise ValueError('와일드카드 파일은 최대 1 MB입니다.')
                cache[name]=[line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#')]
            if not cache[name]:raise ValueError('와일드카드에 선택 가능한 줄이 없습니다: '+name)
            selected=rng.choice(cache[name]);used.append({'name':name,'choice':selected})
            if len(used)>1000:raise ValueError('와일드카드는 한 번에 최대 1,000개입니다.')
            return expand(selected,(*stack,name))
        result=TOKEN.sub(choose,value)
        if len(result)>100000:raise ValueError('확장 결과가 너무 깁니다 (최대 100,000자).')
        return result
    return expand(text),used

def clean_filename(stem):
    stem=unicodedata.normalize('NFC',stem)
    stem=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',stem)
    stem=re.sub(r'\s+',' ',stem).strip(' .')
    # Keep headroom for collision suffixes and the sidecar extension on Windows.
    while len(stem.encode('utf-16-le'))>300:stem=stem[:-1]
    if not stem:stem='image'
    if stem.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'{p}{i}' for p in ('COM','LPT') for i in range(1,10)]}:stem='_'+stem
    return stem.rstrip(' .')

def export_stem(pattern,source,size,note='',now=None):
    now=now or datetime.now()
    fields={'source':Path(source).stem,'date':now.strftime('%Y%m%d'),'time':now.strftime('%H%M%S'),'width':str(size[0]),'height':str(size[1]),'note':note}
    pieces=[]
    for literal,field,format_spec,conversion in string.Formatter().parse(pattern):
        pieces.append(literal)
        if field is not None:
            if field not in fields or format_spec or conversion:raise ValueError('사용 가능한 이름 항목: '+', '.join('{'+key+'}' for key in fields))
            pieces.append(fields[field])
    return clean_filename(''.join(pieces))
