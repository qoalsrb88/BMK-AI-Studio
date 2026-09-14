"""Stage a download without replacement or execution; verify again before future install."""
import hashlib
import os
from pathlib import Path
import re
import uuid
from .authenticode import verify_publisher

MAX_INSTALLER_BYTES = 2 * 1024**3 - 1

class DownloadCancelled(Exception):
    pass

def validate_expectations(size, sha256):
    if type(size) is not int or not 0 < size <= MAX_INSTALLER_BYTES:
        raise ValueError('Invalid expected installer size')
    if not isinstance(sha256, str) or not re.fullmatch('[0-9a-f]{64}', sha256):
        raise ValueError('A SHA256 digest from authenticated release metadata is required')

def stage_download(chunks, destination, expected_size, expected_sha256, cancelled=lambda: False):
    validate_expectations(expected_size, expected_sha256)
    destination = Path(destination).absolute()
    if destination.suffix.lower() != '.exe':
        raise ValueError('Expected an installer EXE')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Existing downloads are preserved')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + uuid.uuid4().hex + '.download')
    digest = hashlib.sha256(); total = 0
    try:
        with temporary.open('xb') as stream:
            for block in chunks:
                if cancelled():raise DownloadCancelled()
                if not isinstance(block, bytes):raise ValueError('Invalid download data')
                total += len(block)
                if total > expected_size:raise ValueError('Download exceeds expected size')
                digest.update(block); stream.write(block)
            if cancelled():raise DownloadCancelled()
            if total != expected_size or digest.hexdigest() != expected_sha256:
                raise ValueError('Download integrity check failed')
            stream.flush(); os.fsync(stream.fileno())
        # Windows rename refuses an existing destination, including racing writers.
        if os.name == 'nt':os.rename(temporary, destination)
        else:
            os.link(temporary, destination)
            temporary.unlink()
        return destination
    finally:
        temporary.unlink(missing_ok=True)

def verify_installable(path, expected_size, expected_sha256, publisher_thumbprint):
    validate_expectations(expected_size, expected_sha256)
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected_size:
        raise ValueError('Installer changed after download')
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    if actual != expected_sha256:
        raise ValueError('Installer changed after download')
    return verify_publisher(path, publisher_thumbprint)

