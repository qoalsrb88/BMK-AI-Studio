"""Real local HTTP responses, delayed replies and cancellation; no GitHub traffic."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,time,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QTcpServer,QHostAddress
from PySide6.QtWidgets import QApplication
from bmk_studio import update_dialog
from bmk_studio.update_credentials import LoginStore
app=QApplication([])
server=QTcpServer();assert server.listen(QHostAddress.SpecialAddress.LocalHost,0)
update_dialog.API_URL=f'http://127.0.0.1:{server.serverPort()}/releases'
responses=[];sockets=[];requests=[]
def incoming():
    socket=server.nextPendingConnection();sockets.append(socket)
    def respond():
        if not socket.canReadLine():return
        requests.append(bytes(socket.readAll()))
        if not responses:return
        code,body=responses.pop(0)
        socket.write(f'HTTP/1.1 {code} Test\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body)
        socket.disconnectFromHost()
    socket.readyRead.connect(respond)
server.newConnection.connect(incoming)
def wait(test):
    end=time.monotonic()+5
    while not test() and time.monotonic()<end:app.processEvents();time.sleep(.005)
    assert test()
with patch.object(LoginStore,'load',side_effect=AssertionError('Public updates must not load credentials')):
    dialog=update_dialog.UpdateDialog()
dialog.show()
responses.append((404,b'{}'));dialog.check.click();wait(lambda:dialog.reply is None)
assert '확인하지 못했습니다' in dialog.status.text() and dialog.check.isEnabled()
responses.append((200,json.dumps([dict(tag_name='v99.0.0',prerelease=True,draft=False)]).encode()))
dialog.check.click();wait(lambda:dialog.reply is None)
assert '99.0.0' in dialog.status.text() and dialog.destination.endswith('/tag/v99.0.0')
with patch.object(update_dialog.QDesktopServices,'openUrl',return_value=True) as open_url:
    dialog.open_page.click()
    assert open_url.call_args.args[0].toString()==dialog.destination
dialog.beta.setChecked(False)
responses.append((200,json.dumps([dict(tag_name='v99.0.0',prerelease=True,draft=False)]).encode()))
dialog.check.click();wait(lambda:dialog.reply is None)
assert '새로운 버전이 없습니다' in dialog.status.text()
assert dialog.destination==update_dialog.RELEASES_URL
responses.append((200,b'not-json'));dialog.check.click();wait(lambda:dialog.reply is None)
assert '읽지 못했습니다' in dialog.status.text()

for code in (401,403,429):
    responses.append((code,b'{}'));dialog.check.click();wait(lambda:dialog.reply is None)
    assert '확인하지 못했습니다' in dialog.status.text() and '로그인' not in dialog.status.text()
assert requests and all(b'authorization:' not in request.lower() for request in requests)
dialog.check.click();assert dialog.reply is not None
ticks=[];QTimer.singleShot(30,lambda:ticks.append(True));wait(lambda:bool(ticks))
assert not dialog.check.isEnabled()
dialog.reject();app.processEvents();assert dialog.reply is None
server.close()
print('Anonymous update HTTP/errors/beta/browser/cancel/responsive checks passed')

