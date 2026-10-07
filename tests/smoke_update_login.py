"""Browser login + authenticated release check through a real loopback HTTP server."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QTcpServer,QHostAddress
from PySide6.QtWidgets import QApplication
from bmk_studio import update_login,legacy_update_dialog as update_dialog
from bmk_studio.update_credentials import LoginStore
app=QApplication([])
root=Path(tempfile.mkdtemp(prefix='bmk-login-test-')).resolve()
server=QTcpServer();assert server.listen(QHostAddress.SpecialAddress.LocalHost,0)
base=f'http://127.0.0.1:{server.serverPort()}'
update_login.DEVICE_URL=base+'/device';update_login.TOKEN_URL=base+'/token';update_dialog.API_URL=base+'/releases'
device={'device_code':'test-device-code','user_code':'ABCD-1234','verification_uri':update_login.VERIFY_URL,'expires_in':600,'interval':1}
token={'access_token':'synthetic-app-token','token_type':'bearer','expires_in':600}
responses=[device,token,[{'tag_name':'v99.0.0','prerelease':True,'draft':False}]]
requests=[];sockets=[]
def incoming():
    socket=server.nextPendingConnection();sockets.append(socket);received=bytearray();sent=[False]
    def respond():
        received.extend(bytes(socket.readAll()))
        if sent[0] or b'\r\n\r\n' not in received:return
        head,body=bytes(received).split(b'\r\n\r\n',1)
        length=next((int(line.split(b':',1)[1]) for line in head.split(b'\r\n') if line.lower().startswith(b'content-length:')),0)
        if len(body)<length:return
        sent[0]=True;requests.append(bytes(received))
        if not responses:return
        payload=json.dumps(responses.pop(0)).encode()
        socket.write(f'HTTP/1.1 200 OK\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n'.encode()+payload);socket.disconnectFromHost()
    socket.readyRead.connect(respond)
server.newConnection.connect(incoming)
def wait(predicate,seconds=5):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert predicate()
store=LoginStore(root/'login.bin')
dialog=update_dialog.UpdateDialog(client_id='synthetic-client',login_store=store);dialog.show()
ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(True));timer.start(20)
def begin():
    modal=app.activeModalWidget()
    modal.remember.setChecked(True);modal.start_button.click()
QTimer.singleShot(0,begin);dialog.login_button.click()
assert dialog.token=='synthetic-app-token' and len(ticks)>5
assert store.load('synthetic-client')[0]==dialog.token
assert b'synthetic-app-token' not in store.path.read_bytes()
dialog.check.click();wait(lambda:dialog.reply is None)
assert '99.0.0' in dialog.status.text()
assert b'Authorization: Bearer synthetic-app-token' in requests[-1]
dialog.logout_button.click();assert dialog.token is None and not store.path.exists()
flow=update_login.DeviceLogin('synthetic-client')
flow.active=True;flow.deadline=time.monotonic()+600;flow.interval=1
flow.process({'error':'slow_down'},'token')
assert flow.interval>=6 and flow.timer.remainingTime()>5000
flow.cancel();assert not flow.timer.isActive()
events=[];flow.authorized.connect(lambda *args:events.append('authorized'))
flow.start();wait(lambda:flow.reply is not None);flow.cancel();app.processEvents();assert not events and not flow.active
dialog.reject();timer.stop();server.close()
print('Device login, encrypted persistence, private authorization header, slowdown and cancellation passed')

