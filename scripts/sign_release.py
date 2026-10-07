"""Sign a NEW copy of a bundle using an explicitly selected Windows-store certificate."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bmk_studio.authenticode import normalize_thumbprint, verify_publisher
from package_release import inspect_bundle, digest

class Signer:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve(strict=True)
        config = json.loads(self.config_path.read_text(encoding='utf-8-sig'))
        if set(config) != {'signtool', 'certificate_thumbprint', 'timestamp_url'}:
            raise ValueError('Only signtool, certificate_thumbprint and timestamp_url are supported')
        self.tool = Path(config['signtool']).resolve(strict=True)
        if not self.tool.is_file():
            raise ValueError('SignTool executable required')
        self.thumbprint = normalize_thumbprint(config['certificate_thumbprint'])
        self.timestamp_url = config['timestamp_url']
        parsed = urlsplit(self.timestamp_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError('An HTTPS RFC 3161 timestamp URL without credentials is required')
        if any(c.isspace() for c in self.timestamp_url):
            raise ValueError('Invalid timestamp URL')

    def verify(self, path):
        subprocess.run([str(self.tool), 'verify', '/pa', '/all', '/tw', str(path)],
                       check=True, capture_output=True, timeout=120,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return verify_publisher(path, self.thumbprint)

    def sign_generated_file(self, path):
        path = Path(path).resolve(strict=True)
        if path.suffix.lower() != '.exe':
            raise ValueError('Only generated EXE files may be signed')
        subprocess.run([str(self.tool), 'sign', '/s', 'My', '/sha1', self.thumbprint,
                        '/fd', 'SHA256', '/tr', self.timestamp_url, '/td', 'SHA256', str(path)],
                       check=True, capture_output=True, timeout=180,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return self.verify(path)

    def inno_command(self):
        # Inno substitutes dollar sequences itself; paths must remain literals.
        literal = subprocess.list2cmdline([sys.executable, str(Path(__file__).resolve()),
                                          '--config', str(self.config_path)])
        return literal.replace('$', '$$') + ' --sign-generated-file $f'

def sign_bundle(source, destination, signer):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Existing bundles are preserved')
    if source == destination or source in destination.parents:
        raise ValueError('The signed copy must be outside the source bundle')
    report = inspect_bundle(source)
    shutil.copytree(source, destination)
    for item in report['files']:
        if digest(destination / item['path']) != item['sha256']:
            raise RuntimeError('Source changed during copy; no signature applied')
    info = dict(report['build'])
    info['signed'] = False; info.pop('signature', None)
    (destination / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    signature = signer.sign_generated_file(destination / 'BMK-AI-Studio.exe')
    info.update(signed=True, signature=signature)
    (destination / 'build-info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    # Recheck data exclusions and record hashes AFTER signing.
    receipt = inspect_bundle(destination)
    receipt['unsigned_source_preserved'] = True
    return receipt

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--sign-generated-file', type=Path)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    signer = Signer(args.config)
    if args.sign_generated_file:
        if args.bundle or args.output:parser.error('Choose one signing operation')
        signer.sign_generated_file(args.sign_generated_file)
    else:
        if not args.bundle or not args.output:parser.error('--bundle and --output required')
        report = sign_bundle(args.bundle, args.output, signer)
        print(json.dumps({'signed': True, 'file_count': report['file_count'],
                          'source_commit': report['build']['source_commit']}))

