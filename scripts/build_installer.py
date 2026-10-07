"""Create a version-isolated installer; signed builds require verified publisher signatures."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from package_release import inspect_bundle, digest


def quoted(value):
    value = str(value)
    if any(c in value for c in '\r\n"{}'):
        raise ValueError('Unsupported character in installer input')
    return '"' + value + '"'


def make_script(bundle, output, report, signer=None):
    version = report['build']['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Numeric release version required')
    flavor = 'NVIDIA' if report['build'].get('cuda') else 'CPU'
    title = f'BMK AI Studio {version} ({flavor})'
    # Separate versions preserve working installations and avoid stale DLL mixing.
    lines = [
        '[Setup]', f'AppId=BMK-AI-Studio-{version}-{flavor}',
        f'AppName={title}', f'AppVersion={version}', 'AppPublisher=qoalsrb88',
        'AppPublisherURL=https://github.com/qoalsrb88/BMK-AI-Studio',
        f'DefaultDirName={{localappdata}}\\Programs\\BMK-AI-Studio\\{version}-{flavor}',
        'UsePreviousAppDir=no', 'PrivilegesRequired=lowest',
        'ArchitecturesAllowed=x64compatible', 'ArchitecturesInstallIn64BitMode=x64compatible',
        'MinVersion=10.0', 'DisableProgramGroupPage=yes',
        f'OutputDir={quoted(output)}',
        f'OutputBaseFilename=BMK-AI-Studio-{version}-Windows-x64-{flavor}-Setup',
        'Compression=lzma2/fast', 'SolidCompression=no', 'WizardStyle=modern',
        'UninstallDisplayIcon={app}\\BMK-AI-Studio.exe',
        'CloseApplications=no', 'RestartApplications=no',
        f'LicenseFile={quoted(bundle / "LICENSE")}',
        '[Tasks]', 'Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked',
        '[Files]',
    ]
    if signer is not None:
        lines[1:1] = ['SignTool=bmkpublisher', 'SignedUninstaller=yes',
                      'SignedUninstallerDir=' + quoted(output / 'signed-uninstaller')]
    for item in report['files']:
        rel = Path(item['path'])
        dest = '{app}' + ('\\' + str(rel.parent) if rel.parent != Path('.') else '')
        lines.append(f'Source: {quoted(bundle / rel)}; DestDir: "{dest}"; Flags: ignoreversion')
    lines += ['[Icons]',
              f'Name: "{{userprograms}}\\{title}"; Filename: "{{app}}\\BMK-AI-Studio.exe"',
              f'Name: "{{userdesktop}}\\{title}"; Filename: "{{app}}\\BMK-AI-Studio.exe"; Tasks: desktopicon',
              '[Code]',
              'function NextButtonClick(CurPageID: Integer): Boolean;',
              'var Entry: TFindRec; Occupied: Boolean;',
              'begin',
              '  Result := True;',
              '  if CurPageID <> wpSelectDir then exit;',
              '  Occupied := False;',
              "  if FindFirst(AddBackslash(WizardDirValue) + '*', Entry) then begin",
              '    try',
              '      repeat',
              "        if (Entry.Name <> '.') and (Entry.Name <> '..') then Occupied := True;",
              '      until not FindNext(Entry);',
              '    finally FindClose(Entry); end;',
              '  end;',
              '  if Occupied then begin',
              "    SuppressibleMsgBox('Choose a new empty folder. Existing programs and user data are preserved.', mbError, MB_OK, IDOK);",
              '    Result := False;',
              '  end;',
              'end;',
              # Silent installs skip the directory page: enforce the same guard.
              'function PrepareToInstall(var NeedsRestart: Boolean): String;',
              'begin',
              "  Result := '';",
              "  if not NextButtonClick(wpSelectDir) then Result := 'Installation folder must be empty.';",
              'end;']
    return '\n'.join(lines) + '\n'


def build(bundle, output, compiler, signer=None):
    bundle, output = Path(bundle).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new installer output directory')
    if bundle == output or bundle in output.parents:
        raise ValueError('Output must be outside the bundle')
    report = inspect_bundle(bundle)
    if signer is not None:
        if report['build'].get('signed') is not True:
            raise ValueError('Sign a copy of the application bundle first')
        signer.verify(bundle / 'BMK-AI-Studio.exe')
    script = make_script(bundle, output, report, signer)
    output.mkdir(parents=True)
    source = output / 'installer.iss'
    source.write_text(script, encoding='utf-8-sig')
    command = [str(Path(compiler).resolve()), '/Q']
    if signer is not None:
        command.append('/Sbmkpublisher=' + signer.inno_command())
    command.append(str(source))
    with (output / 'compiler.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    installers = list(output.glob('*-Setup.exe'))
    if len(installers) != 1:
        raise RuntimeError('Expected exactly one installer')
    exe = installers[0]
    signatures = {}
    if signer is not None:
        signatures['setup'] = signer.verify(exe)
        uninstallers = list((output / 'signed-uninstaller').glob('*.exe'))
        if not uninstallers:
            raise RuntimeError('Signed uninstaller evidence missing')
        signatures['uninstallers'] = [signer.verify(path) for path in uninstallers]
    receipt = {'build': report['build'], 'installer': exe.name, 'bytes': exe.stat().st_size,
               'sha256': digest(exe), 'signed': signer is not None, 'signatures': signatures, 'tested_install_uninstall': False,
               'layout': 'Version-isolated; original data and previous versions retained'}
    (output / 'installer.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle'); parser.add_argument('output'); parser.add_argument('--compiler', required=True)
    parser.add_argument('--signing-config', type=Path)
    args = parser.parse_args()
    from sign_release import Signer
    signer = Signer(args.signing_config) if args.signing_config else None
    build(args.bundle, args.output, args.compiler, signer)
