"""GitHub App device login, with cancellable Qt networking and no client secret."""
import time
from urllib.parse import urlencode
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import json
from .update_network import configure_update_tls

DEVICE_URL = 'https://github.com/login/device/code'
TOKEN_URL = 'https://github.com/login/oauth/access_token'
VERIFY_URL = 'https://github.com/login/device'
MAX_BODY = 64 * 1024

class DeviceLogin(QObject):
    code_ready = Signal(str)
    authorized = Signal(str, float)
    failed = Signal(str)
    def __init__(self, client_id, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.network = QNetworkAccessManager(self)
        self.timer = QTimer(self); self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.poll)
        self.reply = None; self.device_code = ''; self.deadline = 0; self.interval = 5
        self.active = False

    def start(self):
        self.cancel()
        if not self.client_id:
            self.failed.emit('업데이트용 GitHub App 등록이 필요합니다.'); return
        try:configure_update_tls()
        except RuntimeError as exc:
            self.failed.emit(str(exc));return
        self.active = True
        self.post(DEVICE_URL, {'client_id': self.client_id}, 'device')

    def post(self, url, values, phase):
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b'Accept', b'application/json')
        request.setRawHeader(b'Content-Type', b'application/x-www-form-urlencoded')
        request.setRawHeader(b'User-Agent', b'BMK-AI-Studio')
        request.setTransferTimeout(15000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.network.post(request, urlencode(values).encode())
        self.reply = reply
        reply.readyRead.connect(lambda: reply.abort() if reply.bytesAvailable() > MAX_BODY else None)
        reply.finished.connect(lambda: self.receive(reply, phase))

    def receive(self, reply, phase):
        if reply is not self.reply or not self.active:
            reply.deleteLater(); return
        self.reply = None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        error = reply.error(); data = bytes(reply.read(MAX_BODY + 1)); reply.deleteLater()
        try:
            if error != QNetworkReply.NetworkError.NoError or status != 200 or len(data) > MAX_BODY:
                raise ValueError()
            value = json.loads(data)
            if not isinstance(value, dict):raise ValueError()
            self.process(value, phase)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            self.fail('로그인 응답을 확인하지 못했습니다. 다시 시도해 주세요.')

    def process(self, value, phase):
        if phase == 'device':
            if value.get('error'):
                self.fail('GitHub App의 Client ID와 Device Flow 설정을 확인해 주세요.'); return
            code = value['device_code']; user_code = value['user_code']
            lifetime = value['expires_in']; interval = value.get('interval', 5)
            if not isinstance(code, str) or not 1 <= len(code) <= 256:raise ValueError()
            if not isinstance(user_code, str) or not 1 <= len(user_code) <= 32:raise ValueError()
            if value['verification_uri'] != VERIFY_URL:raise ValueError()
            if type(lifetime) is not int or not 1 <= lifetime <= 1800:raise ValueError()
            if type(interval) is not int or not 1 <= interval <= 300:raise ValueError()
            self.device_code = code; self.interval = interval
            self.deadline = time.monotonic() + lifetime
            self.code_ready.emit(user_code); self.schedule()
        else:
            if time.monotonic() >= self.deadline:
                self.fail('로그인 시간이 만료되었습니다. 다시 시작해 주세요.'); return
            error = value.get('error')
            if error == 'authorization_pending':
                self.schedule(); return
            if error == 'slow_down':
                self.interval += 5
                requested = value.get('interval')
                if type(requested) is int:self.interval = max(self.interval, requested)
                self.interval = min(self.interval, 1800)
                self.schedule(); return
            if error:
                self.fail('로그인이 취소되었거나 만료되었습니다. 다시 시작해 주세요.'); return
            token = value.get('access_token')
            expires = value.get('expires_in', 28800)
            if not isinstance(token, str) or not 1 <= len(token) <= 4096 or any(c.isspace() for c in token):raise ValueError()
            if type(expires) is not int or not 1 <= expires <= 28800:raise ValueError()
            if not isinstance(value.get('token_type'), str) or value['token_type'].lower() != 'bearer':raise ValueError()
            self.active = False; self.device_code = ''; self.timer.stop()
            self.authorized.emit(token, time.time() + expires)

    def schedule(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:self.fail('로그인 시간이 만료되었습니다.'); return
        self.timer.start(max(1, int(min(self.interval, remaining) * 1000)))

    def poll(self):
        if not self.active:return
        if time.monotonic() >= self.deadline:self.fail('로그인 시간이 만료되었습니다.'); return
        self.post(TOKEN_URL, {'client_id': self.client_id, 'device_code': self.device_code,
                             'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'}, 'token')

    def fail(self, message):
        self.cancel(); self.failed.emit(message)

    def cancel(self):
        self.active = False; self.timer.stop(); self.device_code = ''
        reply, self.reply = self.reply, None
        if reply is not None:reply.abort(); reply.deleteLater()

