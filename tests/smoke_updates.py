"""Real local HTTP responses, delayed replies and cancellation; no GitHub traffic."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,time,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QTcpServer,QHostAddress
from PySide6.QtWidgets import QApplication
from bmk_studio import update_dialog
from bmk_studio.update_credentials import LoginStore
app=QApplication([])
server=QTcpServer();assert server.listen(QHostAddress.SpecialAddress.LocalHost,0)
update_dialog.API_URL=f'http://127.0.0.1:{server.serverPort()}/releases'
responses=[];sockets=[]
def incoming():
    socket=server.nextPendingConnection();sockets.append(socket)
    def respond():
        if not socket.canReadLine():return
        socket.readAll()
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
dialog=update_dialog.UpdateDialog(client_id='synthetic-client',login_store=LoginStore(Path(tempfile.mkdtemp())/'login.bin'));dialog.show()
responses.append((404,b'{}'));dialog.check.click();wait(lambda:dialog.reply is None)
assert '확인하지 못했습니다' in dialog.status.text() and dialog.check.isEnabled()
responses.append((200,json.dumps([dict(tag_name='v99.0.0',prerelease=True,draft=False)]).encode()))
dialog.check.click();wait(lambda:dialog.reply is None)
assert '99.0.0' in dialog.status.text() and dialog.destination.endswith('/tag/v99.0.0')
responses.append((200,b'not-json'));dialog.check.click();wait(lambda:dialog.reply is None)
assert '읽지 못했습니다' in dialog.status.text()

# A revoked remembered login must not reappear when the dialog is reopened.
dialog.token = 'synthetic-revoked-token'; dialog.expires_at = time.time() + 600
dialog.login_store.save(dialog.client_id, dialog.token, dialog.expires_at)
responses.append((401,b'{}'));dialog.check.click();wait(lambda:dialog.reply is None)
assert dialog.token is None and not dialog.login_store.path.exists()
assert '다시 로그인' in dialog.status.text()
reopened=update_dialog.UpdateDialog(client_id=dialog.client_id,login_store=dialog.login_store)
assert reopened.token is None
reopened.reject()
dialog.check.click();assert dialog.reply is not None
ticks=[];QTimer.singleShot(30,lambda:ticks.append(True));wait(lambda:bool(ticks))
assert not dialog.check.isEnabled()
dialog.reject();app.processEvents();assert dialog.reply is None
server.close()
print('Update HTTP/error/version/cancel/responsive checks passed')

