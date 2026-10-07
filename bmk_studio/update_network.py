"""Use Windows TLS for updates without loading another application's OpenSSL DLLs."""
import os
from PySide6.QtNetwork import QSslSocket


def configure_update_tls():
    # Select before constructing an HTTPS request or any Qt SSL objects.
    # Qt's default OpenSSL backend can mix Python and PATH-provided DLLs.
    if os.name == 'nt' and not QSslSocket.setActiveBackend('schannel'):
        raise RuntimeError('Windows 보안 연결을 초기화하지 못했습니다. 앱의 Qt TLS 구성 요소를 확인해 주세요.')
