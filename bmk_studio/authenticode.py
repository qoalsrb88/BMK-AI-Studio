"""Windows trust/publisher checks. No certificate import or private-key access."""
import json
import os
from pathlib import Path
import re
import subprocess

def normalize_thumbprint(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Fa-f]{40}', value):
        raise ValueError('A 40-character certificate thumbprint is required')
    return value.upper()

def inspect_signature(path):
    if os.name != 'nt':
        raise RuntimeError('Windows signature verification requires Windows')
    path = Path(path).resolve(strict=True)
    literal = "'" + str(path).replace("'", "''") + "'"
    script = (
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        "$ErrorActionPreference='Stop';"
        "$s=Get-AuthenticodeSignature -LiteralPath " + literal + ";"
        "[pscustomobject]@{status=[string]$s.Status;"
        "thumbprint=$s.SignerCertificate.Thumbprint;"
        "timestamped=($null -ne $s.TimeStamperCertificate)}|ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
         '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, timeout=60,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Windows signature verification failed')
    return json.loads(result.stdout.decode('utf-8-sig'))

def verify_publisher(path, thumbprint):
    expected = normalize_thumbprint(thumbprint)
    result = inspect_signature(path)
    if result.get('status') != 'Valid':
        raise ValueError('File does not have a trusted Windows signature')
    if str(result.get('thumbprint', '')).upper() != expected:
        raise ValueError('Unexpected signing certificate')
    if result.get('timestamped') is not True:
        raise ValueError('A trusted timestamp is required')
    return result

