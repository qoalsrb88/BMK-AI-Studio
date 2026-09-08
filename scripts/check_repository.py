"""Check proposed/staged source files; reports locations, never secret values."""
import argparse,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'.gitignore','.gitattributes','.editorconfig','README.md','LICENSE','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md','SECURITY.md','AGENTS.md','build_windows.py','package_entry.py','launch.pyw','Start.cmd','Start.vbs'}
DIRS={'.github','bmk_studio','tests','scripts','docs'}
TEXT={'.py','.pyw','.md','.txt','.yml','.yaml','.json','.toml','.cmd','.vbs'}
DENIED={'__pycache__','.venv','models','data','user','notes','cache','folder-thumbnails','.downloads','ImageSample'}
PATTERNS=[('private-key',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),('token',re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9_-]{30,})')),('personal-home-path',re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+(?!Public\b|Default\b|example\b)[^\s"\'<>]+'))]
def git(*args):return subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}',*args],cwd=ROOT)
def check(staged=False):
    args=['ls-files','-z','--cached']
    if not staged:args+=['--others','--exclude-standard']
    names=sorted(set(git(*args).decode('utf-8').strip('\0').split('\0'))- {''});issues=[];total=0
    for name in names:
        path=Path(name);parts=path.parts
        allowed=(parts[0] in DIRS or name in ROOT_FILES or (len(parts)==1 and name.startswith('requirements') and path.suffix=='.txt'))
        if not allowed or any(p in DENIED for p in parts) or path.name=='local-settings.json' or name.endswith('.private.json'):issues.append((name,'excluded path'));continue
        if name not in ROOT_FILES and path.suffix not in TEXT:issues.append((name,'non-source file'));continue
        if (ROOT/path).is_symlink():issues.append((name,'symlink'));continue
        content=git('show',':'+name) if staged else (ROOT/path).read_bytes();total+=len(content)
        if len(content)>5*1024**2:issues.append((name,'over 5 MiB source limit'));continue
        try:text=content.decode('utf-8-sig')
        except UnicodeError:issues.append((name,'not UTF-8 text'));continue
        if '\0' in text:issues.append((name,'binary content'));continue
        for label,pattern in PATTERNS:
            for match in pattern.finditer(text):issues.append((name,f'{label} at line {text.count(chr(10),0,match.start())+1}'))
    for name,reason in issues:print(f'{name}: {reason}')
    print(f'{len(names)} files, {total:,} bytes, {len(issues)} findings ({"index" if staged else "working tree"})')
    return not issues
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--staged',action='store_true');options=parser.parse_args();sys.exit(0 if check(options.staged) else 1)
