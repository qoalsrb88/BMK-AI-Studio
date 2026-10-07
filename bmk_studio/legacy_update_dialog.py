"""Legacy private/signed updater reference; not used by the public ZIP app."""
import time
import os
import tempfile
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QCheckBox, QDialogButtonBox, QHBoxLayout, QComboBox, QProgressBar, QMessageBox
from . import __version__, update_config
from .update_credentials import LoginStore
from .update_login_dialog import LoginDialog
from .update_network import configure_update_tls
from .update_assets import current_flavor
from .update_transfer import InstallerDownload
from .updates import API_URL, RELEASES_URL, MAX_RESPONSE, available_release


class UpdateDialog(QDialog):
    def __init__(self, parent=None, *, client_id=None, login_store=None):
        super().__init__(parent)
        self.setWindowTitle('업데이트'); self.resize(480, 260)
        self.client_id = update_config.GITHUB_CLIENT_ID if client_id is None else client_id
        self.login_store = login_store if login_store is not None else LoginStore()
        saved = self.login_store.load(self.client_id) if self.client_id else None
        self.token, self.expires_at = saved if saved else (None, 0)
        self.network = QNetworkAccessManager(self)
        self.reply = None; self.destination = RELEASES_URL
        self.job=None;self.asset=None;self.downloaded=None;self.install_request=None;self.close_result=None
        self.build_flavor=current_flavor()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'현재 버전: {__version__}'))
        self.status = QLabel('버전 확인 시 GitHub에 연결합니다. 이미지·노트는 전송하지 않습니다.\n'
                             '비공개 저장소는 GitHub 로그인 후 새 버전을 확인할 수 있습니다.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.login_state = QLabel(); layout.addWidget(self.login_state)
        auth_row = QHBoxLayout()
        self.login_button = QPushButton('GitHub 로그인'); self.login_button.clicked.connect(self.login)
        self.logout_button = QPushButton('이 PC에서 로그아웃'); self.logout_button.clicked.connect(self.logout)
        auth_row.addWidget(self.login_button); auth_row.addWidget(self.logout_button); layout.addLayout(auth_row)
        self.refresh_login()
        self.beta = QCheckBox('베타 버전 포함'); self.beta.setChecked(True); layout.addWidget(self.beta)
        self.flavor=QComboBox();self.flavor.addItem('CPU판','CPU');self.flavor.addItem('NVIDIA판','NVIDIA')
        self.flavor.setCurrentIndex(max(0,self.flavor.findData(self.build_flavor)))
        self.flavor.currentIndexChanged.connect(self.clear_download);layout.addWidget(self.flavor)
        self.check = QPushButton('새 버전 확인'); self.check.clicked.connect(self.start); layout.addWidget(self.check)
        self.open_page = QPushButton('GitHub 배포 페이지 열기')
        self.open_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.destination)))
        layout.addWidget(self.open_page)
        self.download=QPushButton('새 버전 다운로드');self.download.setEnabled(False)
        self.download.clicked.connect(self.start_download);layout.addWidget(self.download)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.hide();layout.addWidget(self.progress)
        self.cancel_download=QPushButton('다운로드 취소');self.cancel_download.hide()
        self.cancel_download.clicked.connect(self.cancel_transfer);layout.addWidget(self.cancel_download)
        self.open_download=QPushButton('다운로드 폴더 열기');self.open_download.setEnabled(False)
        self.open_download.clicked.connect(self.show_download);layout.addWidget(self.open_download)
        self.install=QPushButton('설치하고 다시 시작');self.install.setEnabled(False)
        self.install.clicked.connect(self.request_install);layout.addWidget(self.install)
        hint = QLabel('설치 전 파일과 게시자를 확인하고 새 폴더를 사용합니다. 이전 버전과 사용자 데이터는 보존합니다.')
        hint.setWordWrap(True); layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def refresh_login(self):
        self.login_state.setText('GitHub 로그인됨' if self.token else ('GitHub 로그인이 필요합니다.' if self.client_id else '로그인 연결 준비 중 · 현재는 배포 페이지를 이용하세요.'))
        self.login_button.setEnabled(bool(self.client_id))
        self.logout_button.setEnabled(bool(self.token) or self.login_store.path.exists())

    def login(self):
        dialog = LoginDialog(self.client_id, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:return
        self.token, self.expires_at = dialog.token, dialog.expires_at
        try:
            if dialog.remember.isChecked():self.login_store.save(self.client_id, self.token, self.expires_at)
            else:self.login_store.clear()
        except OSError:
            self.status.setText('현재 실행에서 로그인했습니다. Windows 로그인 보관 설정은 적용하지 못했습니다.')
        self.refresh_login()

    def logout(self):
        reply, self.reply = self.reply, None
        if reply is not None:reply.abort(); reply.deleteLater()
        self.token = None; self.expires_at = 0
        self.check.setEnabled(True); self.beta.setEnabled(True); self.flavor.setEnabled(True)
        try:self.login_store.clear()
        except OSError:self.status.setText('현재 실행에서 로그아웃했습니다. 보관된 정보는 삭제하지 못했습니다.')
        self.refresh_login()

    def start(self):
        if self.reply is not None or self.job is not None:
            return
        try:configure_update_tls()
        except RuntimeError as exc:
            self.status.setText(str(exc));return
        self.destination = RELEASES_URL; self.check.setEnabled(False); self.beta.setEnabled(False)
        self.clear_download();self.flavor.setEnabled(False)
        self.status.setText('새 버전을 확인하고 있습니다…')
        if self.token and time.time() >= self.expires_at:
            self.token = None; self.expires_at = 0; self.refresh_login()
        request = QNetworkRequest(QUrl(API_URL))
        if self.token:request.setRawHeader(b'Authorization', ('Bearer ' + self.token).encode('utf-8'))
        self.login_button.setEnabled(False)
        request.setRawHeader(b'Accept', b'application/vnd.github+json')
        request.setRawHeader(b'User-Agent', b'BMK-AI-Studio-Update-Check')
        request.setTransferTimeout(10000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self.reply = self.network.get(request)
        self.reply.readyRead.connect(self.limit_size)
        self.reply.finished.connect(self.handle_response)

    def limit_size(self):
        if self.reply is not None and self.reply.bytesAvailable() > MAX_RESPONSE:
            self.reply.abort()

    def handle_response(self):
        reply = self.reply
        if reply is None:
            return
        self.reply = None; self.check.setEnabled(True); self.beta.setEnabled(True); self.refresh_login()
        self.flavor.setEnabled(True)
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        payload = bytes(reply.read(MAX_RESPONSE + 1)); reply.deleteLater()
        if status == 401:
            self.token = None; self.expires_at = 0
            message = '로그인이 만료되었거나 취소되었습니다. GitHub에 다시 로그인해 주세요.'
            try:self.login_store.clear()
            except OSError:message += '\n이 PC에 보관된 로그인 정보는 삭제하지 못했습니다.'
            self.refresh_login(); self.status.setText(message)
            return
        if status in (403, 404):
            self.status.setText('접근 권한 또는 GitHub 요청 제한 때문에 버전을 확인하지 못했습니다.\n'
                                '로그인한 계정과 업데이트 앱에 저장소 접근 권한이 있는지 확인하세요.')
            return
        if status != 200 or error != QNetworkReply.NetworkError.NoError:
            self.status.setText('연결 문제로 확인하지 못했습니다. 잠시 후 다시 시도하거나 배포 페이지를 열어 주세요.')
            return
        try:
            release = available_release(payload, __version__, self.beta.isChecked(),self.flavor.currentData())
        except (ValueError, UnicodeError):
            self.status.setText('배포 정보를 읽지 못했습니다. 배포 페이지에서 직접 확인해 주세요.')
            return
        if release:
            self.asset=release.get('installer');self.download.setEnabled(self.asset is not None)
            self.destination = release['url']
            self.status.setText(f"새 버전 {release['version']}{' 베타' if release['beta'] else ''}가 있습니다.\n배포 페이지에서 변경 사항과 다운로드를 확인하세요.")
        else:
            self.status.setText('조회된 배포 목록에 현재 버전보다 새로운 버전이 없습니다.')

    def clear_download(self):
        self.asset=None;self.downloaded=None
        self.download.setEnabled(False);self.install.setEnabled(False);self.open_download.setEnabled(False)

    def start_download(self):
        if self.job is not None or self.asset is None:return
        if self.token and time.time()>=self.expires_at:
            self.status.setText('로그인이 만료되었습니다. 다시 로그인한 뒤 확인해 주세요.');return
        try:
            root=Path(os.environ.get('LOCALAPPDATA',Path.home()))/'BMK-AI-Studio-updates'
            root.mkdir(parents=True,exist_ok=True)
            folder=Path(tempfile.mkdtemp(prefix=self.asset['version']+'-',dir=root))
        except OSError:
            self.status.setText('다운로드 폴더를 만들지 못했습니다. 디스크 공간과 권한을 확인해 주세요.');return
        self.downloaded=None;self.install.setEnabled(False);self.open_download.setEnabled(False)
        for control in (self.check,self.beta,self.flavor,self.login_button,self.logout_button,self.download):control.setEnabled(False)
        self.status.setText('설치 파일을 내려받고 있습니다…');self.progress.setValue(0);self.progress.show();self.cancel_download.show()
        self.job=InstallerDownload(dict(self.asset),self.token,folder,update_config.SIGNING_THUMBPRINT,self)
        self.job.progress.connect(lambda done,total:self.progress.setValue(min(100,done*100//total)))
        self.job.ready.connect(self.download_ready);self.job.failed.connect(self.status.setText)
        self.job.finished.connect(self.transfer_finished);self.job.start()

    def download_ready(self,result):
        self.downloaded=result;self.open_download.setEnabled(True)
        can_install=result['verified'] and self.build_flavor==result['asset']['flavor']
        self.install.setEnabled(bool(can_install))
        self.status.setText('다운로드와 게시자 확인을 완료했습니다. 설치하면 앱을 종료하고 새 버전을 시작합니다.' if can_install
                            else '다운로드 무결성 확인을 완료했습니다. 이 빌드는 자동 설치를 지원하지 않으므로 다운로드 폴더에서 수동 설치하세요.')

    def transfer_finished(self):
        job,self.job=self.job,None
        if job is not None:job.deleteLater()
        self.cancel_download.hide();self.check.setEnabled(True);self.beta.setEnabled(True);self.flavor.setEnabled(True)
        self.download.setEnabled(self.asset is not None);self.refresh_login()
        if self.close_result is not None:
            result,self.close_result=self.close_result,None;self.done(result)

    def cancel_transfer(self):
        if self.job is not None:
            self.job.requestInterruption();self.status.setText('안전하게 다운로드를 취소하고 있습니다…')

    def show_download(self):
        if self.downloaded:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.downloaded['path']).parent)))

    def request_install(self):
        if self.job is not None or not self.downloaded or not self.install.isEnabled():return
        answer=QMessageBox.question(self,'업데이트 설치','작업을 저장하고 앱을 종료한 뒤 설치합니다. 사용자 데이터 백업과 이전 버전은 보존합니다. 계속할까요?')
        if answer==QMessageBox.StandardButton.Yes:
            self.install_request=self.downloaded;self.accept()

    def done(self, result):
        if self.job is not None:
            self.close_result=result;self.cancel_transfer();return
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort(); reply.deleteLater()
        super().done(result)
