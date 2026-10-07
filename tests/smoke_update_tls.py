"""Exercise each HTTPS button in a fresh process, without GitHub or stored credentials."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def probe(mode):
    # Include the normal application's imports (including Python's SSL library).
    from bmk_studio import app as studio_app, update_dialog, update_login, update_network
    from bmk_studio.update_credentials import LoginStore
    from bmk_studio.update_login_dialog import LoginDialog
    from PySide6.QtNetwork import QTcpServer,QHostAddress,QSslSocket
    from PySide6.QtWidgets import QApplication

    app=QApplication([])
    server=QTcpServer();assert server.listen(QHostAddress.SpecialAddress.LocalHost,0)
    hellos=[];sockets=[]

    def incoming():
        socket=server.nextPendingConnection();sockets.append(socket)
        def reject_handshake():
            data=bytes(socket.readAll())
            if data:
                hellos.append(data)
                socket.abort()
        socket.readyRead.connect(reject_handshake)
    server.newConnection.connect(incoming)

    with tempfile.TemporaryDirectory(prefix='bmk-update-tls-') as root:
        url=f'https://127.0.0.1:{server.serverPort()}/'
        if mode=='update':
            update_dialog.API_URL=url
            dialog=update_dialog.UpdateDialog()
            button=dialog.check
            pending=lambda:dialog.reply is not None
        else:
            update_login.DEVICE_URL=url
            dialog=LoginDialog('synthetic-client')
            button=dialog.start_button
            pending=lambda:dialog.flow.active
        dialog.show();button.click()
        deadline=time.monotonic()+10
        while pending() and time.monotonic()<deadline:
            app.processEvents();time.sleep(.005)
        assert not pending(),'HTTPS failure did not complete'
        # A real TLS ClientHello must be sent, then the UI must recover from the
        # closed handshake without accepting a plaintext or untrusted response.
        assert hellos and hellos[0].startswith(b'\x16\x03'),hellos
        assert button.isEnabled()
        if mode=='update':assert '연결 문제' in dialog.status.text()
        else:assert not dialog.code.text() and dialog.token is None
        if os.name=='nt':
            assert QSslSocket.activeBackend()=='schannel'
            # Missing/broken Schannel must show an error, never fall back to the
            # conflicting OpenSSL DLLs or leave the request button disabled.
            with patch.object(update_network,'QSslSocket') as ssl_socket:
                ssl_socket.setActiveBackend.return_value=False
                button.click()
                assert not pending() and button.isEnabled()
                assert 'Windows 보안 연결' in dialog.status.text()
        dialog.reject();app.processEvents()
    server.close()


if __name__=='__main__':
    if len(sys.argv)>1:
        probe(sys.argv[1])
    else:
        for mode in ('update','login'):
            result=subprocess.run([sys.executable,__file__,mode],capture_output=True,timeout=20)
            assert result.returncode==0,(mode,result.returncode,result.stdout,result.stderr)
        print('Update/login TLS initialization, failed handshake and unavailable backend checks passed')
