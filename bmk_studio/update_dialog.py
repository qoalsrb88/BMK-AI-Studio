"""Non-blocking manual check; private repositories use the user's browser."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QCheckBox, QDialogButtonBox
from . import __version__
from .updates import API_URL, RELEASES_URL, MAX_RESPONSE, available_release


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('업데이트'); self.resize(480, 260)
        self.network = QNetworkAccessManager(self)
        self.reply = None; self.destination = RELEASES_URL
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'현재 버전: {__version__}'))
        self.status = QLabel('버전 확인 시 GitHub에 연결합니다. 이미지·노트는 전송하지 않습니다.\n'
                             '비공개 저장소는 권한이 있는 계정으로 브라우저에서 확인하세요.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.beta = QCheckBox('베타 버전 포함'); self.beta.setChecked(True); layout.addWidget(self.beta)
        self.check = QPushButton('새 버전 확인'); self.check.clicked.connect(self.start); layout.addWidget(self.check)
        self.open_page = QPushButton('GitHub 배포 페이지 열기')
        self.open_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.destination)))
        layout.addWidget(self.open_page)
        hint = QLabel('다운로드·설치는 직접 진행합니다. 기존 데이터 폴더와 원본은 보존하세요.')
        hint.setWordWrap(True); layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def start(self):
        if self.reply is not None:
            return
        self.destination = RELEASES_URL; self.check.setEnabled(False); self.beta.setEnabled(False)
        self.status.setText('새 버전을 확인하고 있습니다…')
        request = QNetworkRequest(QUrl(API_URL))
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
        self.reply = None; self.check.setEnabled(True); self.beta.setEnabled(True)
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error()
        payload = bytes(reply.read(MAX_RESPONSE + 1)); reply.deleteLater()
        if status in (401, 403, 404):
            self.status.setText('접근 권한 또는 GitHub 요청 제한 때문에 버전을 확인하지 못했습니다.\n'
                                '배포 페이지를 열고 저장소 접근 권한이 있는 계정으로 로그인하세요.')
            return
        if status != 200 or error != QNetworkReply.NetworkError.NoError:
            self.status.setText('연결 문제로 확인하지 못했습니다. 잠시 후 다시 시도하거나 배포 페이지를 열어 주세요.')
            return
        try:
            release = available_release(payload, __version__, self.beta.isChecked())
        except (ValueError, UnicodeError):
            self.status.setText('배포 정보를 읽지 못했습니다. 배포 페이지에서 직접 확인해 주세요.')
            return
        if release:
            self.destination = release['url']
            self.status.setText(f"새 버전 {release['version']}{' 베타' if release['beta'] else ''}가 있습니다.\n배포 페이지에서 변경 사항과 다운로드를 확인하세요.")
        else:
            self.status.setText('조회된 배포 목록에 현재 버전보다 새로운 버전이 없습니다.')

    def done(self, result):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort(); reply.deleteLater()
        super().done(result)


