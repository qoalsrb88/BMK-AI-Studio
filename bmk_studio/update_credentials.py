"""DPAPI-encrypted optional login persistence, isolated from transferable user data."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import time
import uuid

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def transform(data, decrypt=False):
    if os.name != 'nt':raise RuntimeError('Windows login storage required')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]; kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), 'BMK update login', None, None, None, 1, ctypes.byref(target))
    if not ok:raise OSError('Windows login protection failed')
    try:return ctypes.string_at(target.data, target.size)
    finally:kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))

def default_path():
    return Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'BMK-AI-Studio-config' / 'update-login.bin'

class LoginStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_path()
    def save(self, client_id, token, expires_at):
        data = json.dumps({'client_id': client_id, 'token': token, 'expires_at': expires_at}).encode()
        encrypted = transform(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with pending.open('xb') as stream:stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
            os.replace(pending, self.path)
        finally:pending.unlink(missing_ok=True)
    def load(self, client_id):
        try:
            if not self.path.is_file() or self.path.stat().st_size > 32768:return None
            value = json.loads(transform(self.path.read_bytes(), True))
            expires = value['expires_at']; token = value['token']
            if value['client_id'] != client_id or not isinstance(token, str) or not token:return None
            if not isinstance(expires, (int, float)) or not 0 < expires - time.time() <= 28800:return None
            return token, expires
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):return None
    def clear(self):
        self.path.unlink(missing_ok=True)

