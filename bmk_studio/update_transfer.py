"""Cancellable private-release downloads; credentials never follow CDN redirects."""
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler,Request,build_opener
from PySide6.QtCore import QThread,Signal
from .update_assets import ASSET_API,redirect_url
from .update_download import stage_download,verify_installable,DownloadCancelled


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None


def download_installer(asset,token,folder,cancelled=lambda:False,progress=lambda done,total:None,opener=None):
    if asset['url']!=ASSET_API+str(asset['id']):raise ValueError('Unexpected asset endpoint')
    if Path(asset['name']).name!=asset['name'] or '/' in asset['name'] or '\\' in asset['name']:
        raise ValueError('Invalid installer filename')
    opener=opener or build_opener(NoRedirect())
    url=asset['url'];response=None
    try:
        for attempt in range(4):
            if cancelled():raise DownloadCancelled()
            headers={'Accept':'application/octet-stream','User-Agent':'BMK-AI-Studio','Accept-Encoding':'identity'}
            if attempt==0 and token:headers['Authorization']='Bearer '+token
            try:response=opener.open(Request(url,headers=headers),timeout=15)
            except HTTPError as exc:response=exc
            if response.status==200:break
            if response.status not in (301,302,303,307,308):
                raise ValueError('다운로드 권한 또는 네트워크 응답을 확인해 주세요. 다시 로그인해야 할 수 있습니다.')
            location=response.headers.get('Location');response.close();response=None
            url=redirect_url(location)
        else:raise ValueError('다운로드 리디렉션 횟수를 초과했습니다.')
        length=response.headers.get('Content-Length')
        if length is not None and (not length.isdigit() or int(length)!=asset['size']):
            raise ValueError('배포 파일 크기가 일치하지 않습니다.')
        def chunks():
            done=0
            while True:
                if cancelled():raise DownloadCancelled()
                block=response.read(256*1024)
                if not block:break
                done+=len(block);progress(done,asset['size']);yield block
        return stage_download(chunks(),Path(folder)/asset['name'],asset['size'],asset['sha256'],cancelled)
    finally:
        if response is not None:response.close()


class InstallerDownload(QThread):
    progress=Signal(int,int)
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self,asset,token,folder,thumbprint,parent=None):
        super().__init__(parent)
        self.asset=asset;self.token=token;self.folder=folder;self.thumbprint=thumbprint
    def run(self):
        try:
            path=download_installer(self.asset,self.token,self.folder,self.isInterruptionRequested,self.progress.emit)
            verified=False
            if self.thumbprint:
                verify_installable(path,self.asset['size'],self.asset['sha256'],self.thumbprint);verified=True
            if self.isInterruptionRequested():raise DownloadCancelled()
            self.ready.emit({'path':str(path),'asset':self.asset,'verified':verified})
        except DownloadCancelled:self.failed.emit('다운로드를 취소했습니다.')
        except Exception:self.failed.emit('다운로드 또는 무결성·게시자 확인에 실패했습니다. 로그인과 연결을 확인해 주세요.')
        finally:self.token=None
