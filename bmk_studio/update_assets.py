"""Select installer assets from authenticated GitHub release metadata."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from .update_download import validate_expectations

ASSET_API='https://api.github.com/repos/qoalsrb88/BMK-AI-Studio/releases/assets/'
DOWNLOAD_HOSTS={'release-assets.githubusercontent.com','objects.githubusercontent.com','github-releases.githubusercontent.com'}


def installer_asset(release,version,flavor):
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or flavor not in ('CPU','NVIDIA'):
        raise ValueError('Invalid release or build flavor')
    name=f'BMK-AI-Studio-{version}-Windows-x64-{flavor}-Setup.exe'
    assets=release.get('assets',[])
    if not isinstance(assets,list):return None
    matches=[item for item in assets if isinstance(item,dict) and item.get('name')==name]
    if len(matches)!=1:return None
    item=matches[0];digest=item.get('digest','');identifier=item.get('id')
    if item.get('state')!='uploaded' or type(identifier) is not int or identifier<=0:return None
    if not isinstance(digest,str) or not digest.startswith('sha256:'):return None
    try:validate_expectations(item.get('size'),digest[7:])
    except ValueError:return None
    return {'name':name,'id':identifier,'size':item['size'],'sha256':digest[7:],
            'version':version,'flavor':flavor,'url':ASSET_API+str(identifier)}


def redirect_url(value):
    if not isinstance(value,str) or any(c.isspace() for c in value):raise ValueError('Unsafe download redirect')
    url=urlsplit(value)
    if (url.scheme!='https' or url.hostname not in DOWNLOAD_HOSTS or url.port not in (None,443)
            or url.username or url.password or url.fragment):
        raise ValueError('Unsafe download redirect')
    return value


def current_flavor():
    if not getattr(sys,'frozen',False):return None
    info=json.loads((Path(sys.executable).parent/'build-info.json').read_text(encoding='utf-8'))
    return 'NVIDIA' if info.get('cuda') else 'CPU'
