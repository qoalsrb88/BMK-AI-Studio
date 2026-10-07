"""Actual download QThread, button signals, cancellation and deferred dialog close."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,time,tempfile,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QMessageBox
from bmk_studio import legacy_update_dialog as update_dialog,update_transfer
from bmk_studio.update_credentials import LoginStore
from bmk_studio.update_download import DownloadCancelled

app=QApplication([])
app.setQuitOnLastWindowClosed(False)

def wait(test):
    deadline=time.monotonic()+5
    while not test() and time.monotonic()<deadline:app.processEvents();time.sleep(.005)
    assert test()

def transfer(asset,token,folder,cancelled,progress):
    for step in range(20):
        if cancelled():raise DownloadCancelled()
        time.sleep(.01);progress(step+1,20)
    path=folder/asset['name'];path.write_bytes(b'synthetic fixture');return path

with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{'LOCALAPPDATA':temporary}),\
     patch.object(update_transfer,'download_installer',side_effect=transfer),\
     patch.object(update_dialog.update_config,'SIGNING_THUMBPRINT',''):
    root=Path(temporary)
    dialog=update_dialog.UpdateDialog(client_id='synthetic',login_store=LoginStore(root/'login.bin'))
    dialog.asset={'name':'fixture.exe','version':'99.0.0','flavor':'CPU','size':17,'sha256':'0'*64}
    dialog.build_flavor='CPU';dialog.download.setEnabled(True);dialog.show()
    ticks=[];dialog.download.click();job=dialog.job
    QTimer.singleShot(30,lambda:ticks.append(True));wait(lambda:bool(ticks))
    assert dialog.job is not None and not dialog.check.isEnabled()
    wait(lambda:dialog.job is None)
    assert dialog.downloaded and not dialog.downloaded['verified']
    assert not dialog.install.isEnabled() and dialog.open_download.isEnabled()
    assert dialog.progress.value()==100 and dialog.check.isEnabled()

    with patch.object(update_dialog.update_config,'SIGNING_THUMBPRINT','1'*40),\
         patch.object(update_transfer,'verify_installable',side_effect=ValueError('untrusted')):
        dialog.download.click();wait(lambda:dialog.job is None)
        assert dialog.downloaded is None and not dialog.install.isEnabled()
        assert '실패' in dialog.status.text() and dialog.download.isEnabled()

    with patch.object(update_dialog.update_config,'SIGNING_THUMBPRINT','1'*40),\
         patch.object(update_transfer,'verify_installable'):
        dialog.download.click();wait(lambda:dialog.job is None)
        assert dialog.install.isEnabled()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):dialog.install.click()
        assert dialog.install_request is None and dialog.isVisible()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):dialog.install.click()
        assert dialog.install_request==dialog.downloaded and not dialog.isVisible()

    closing=update_dialog.UpdateDialog(client_id='synthetic',login_store=LoginStore(root/'login.bin'))
    closing.asset=dict(dialog.asset);closing.download.setEnabled(True);closing.show()
    closing.download.click();closing.reject()
    assert closing.job is not None and closing.isVisible()
    wait(lambda:closing.job is None)
    assert not closing.isVisible() and closing.downloaded is None
    app.processEvents()

print('Legacy download responsiveness, trust rejection and cancellation passed')
