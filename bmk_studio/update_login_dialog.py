"""Device-code dialog: browser authorization is always performed by the user."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton,
                               QCheckBox, QDialogButtonBox, QApplication)
from .update_login import DeviceLogin, VERIFY_URL

class LoginDialog(QDialog):
    def __init__(self, client_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle('GitHub 로그인'); self.resize(460, 280)
        self.token = None; self.expires_at = 0
        layout = QVBoxLayout(self)
        self.status = QLabel('연결 코드를 받은 뒤 브라우저에서 본인의 GitHub 계정으로 승인하세요.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.code = QLineEdit(); self.code.setReadOnly(True); layout.addWidget(self.code)
        self.copy = QPushButton('연결 코드 복사'); self.copy.setEnabled(False)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.code.text())); layout.addWidget(self.copy)
        self.browser = QPushButton('브라우저에서 GitHub 로그인'); self.browser.setEnabled(False)
        self.browser.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(VERIFY_URL))); layout.addWidget(self.browser)
        self.remember = QCheckBox('이 Windows 계정에 로그인 정보 보관'); layout.addWidget(self.remember)
        self.start_button = QPushButton('연결 코드 받기')
        self.start_button.clicked.connect(self.start); layout.addWidget(self.start_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.flow = DeviceLogin(client_id, self)
        self.flow.code_ready.connect(self.ready)
        self.flow.failed.connect(self.failed)
        self.flow.authorized.connect(self.authorized)

    def start(self):
        self.code.clear(); self.copy.setEnabled(False); self.browser.setEnabled(False)
        self.start_button.setEnabled(False); self.status.setText('연결 코드를 요청하고 있습니다…')
        self.flow.start()
    def ready(self, code):
        self.code.setText(code); self.copy.setEnabled(True); self.browser.setEnabled(True)
        self.status.setText('코드를 복사한 뒤 브라우저에서 입력하고 승인하세요. 완료되면 자동으로 연결됩니다.')
    def failed(self, message):
        self.status.setText(message); self.code.clear()
        self.copy.setEnabled(False); self.browser.setEnabled(False); self.start_button.setEnabled(True)
    def authorized(self, token, expires_at):
        self.token = token; self.expires_at = expires_at; self.accept()
    def done(self, result):
        self.flow.cancel(); super().done(result)

