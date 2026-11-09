"""Data-preserving source/native updates. Native helpers run outside the installation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_paths import installation_root, is_frozen, runtime_home
from external_process import external_env, external_libraries
from https_client import verified_urlopen
from installer.update_lock import LOCK_NAME, installation_lock

KEEP = ('.env', '.venv', '.git', 'engines', 'tools/cloudflared', 'server/data', LOCK_NAME,
        '.UpdateRecovery.bat', '.UpdateRecovery.sh', '.UpdateRecovery.json')
NATIVE_NAMES = {'ShogiAnalyzer.exe', 'ShogiAnalyzer', '_internal', 'third_party_sources',
                'BUILD_INFO.json', 'README.txt', 'THIRD_PARTY.txt', 'THIRD-PARTY.txt',
                'Start.bat', 'Start.command', 'Update.bat', 'Update.sh', 'Update.command', 'LICENSE'}
WORK_PREFIX = '.shogianalyzer-update-'
JOB_PREFIX = 'ShogiAnalyzer-update-'
MAX_EXPANDED = 4 * 1024**3


class UpdateError(RuntimeError):
    pass


def kept(rel: Path) -> bool:
    parts = tuple(p.casefold() for p in rel.parts)
    return (bool(parts) and parts[0].startswith(WORK_PREFIX)) or any(
        parts[:len(k.split('/'))] == tuple(k.casefold().split('/')) for k in KEEP)


def target_platform(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    os_key = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'macos'}.get(system or platform.system())
    arch = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(
        (machine or platform.machine()).lower())
    if not os_key or not arch:
        raise UpdateError('このOS・CPU用の配布物には対応していません。')
    return os_key, arch


def select_asset(release: dict, *, native: bool, system=None, machine=None) -> dict:
    tag = str(release.get('tag_name') or '')
    if not re.fullmatch(r'v?\d+(?:\.\d+){1,3}(?:-[A-Za-z0-9.-]+)?', tag):
        raise UpdateError('リリースのバージョン情報が不正です。')
    version = tag.removeprefix('v')
    if native:
        os_key, arch = target_platform(system, machine)
        name = f'ShogiAnalyzer-v{version}-{os_key}-{arch}' + ('.zip' if os_key == 'windows' else '.tar.gz')
    else:
        name = f'ShogiAnalyzer-v{version}.zip'
    matches = [a for a in release.get('assets', []) if a.get('name') == name]
    if len(matches) != 1:
        raise UpdateError(f'対応する配布物 {name} が見つかりません。現在のファイルは変更しません。')
    return matches[0]


def download(url: str, dest: Path, *, expected_size: int | None = None) -> str:
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise UpdateError('更新ファイルの取得にはHTTPSが必要です。')
    request = urllib.request.Request(url, headers={'User-Agent': 'ShogiAnalyzer updater'})
    digest = hashlib.sha256(); size = 0
    with verified_urlopen(request, timeout=120) as response, dest.open('xb') as output:
        if urllib.parse.urlsplit(response.geturl()).scheme != 'https':
            raise UpdateError('HTTPS以外への転送は受け付けません。')
        while chunk := response.read(1024 * 1024):
            output.write(chunk); digest.update(chunk); size += len(chunk)
            if size > MAX_EXPANDED:
                raise UpdateError('更新ファイルが大きすぎます。')
        advertised = response.headers.get('Content-Length')
        if (advertised and size != int(advertised)) or (expected_size is not None and size != expected_size):
            raise UpdateError('ダウンロードが途中で切れています。')
    return digest.hexdigest()


def asset_digest(asset: dict, release: dict, work: Path, downloader=download) -> str:
    digest = str(asset.get('digest') or '')
    if re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        return digest.split(':', 1)[1].lower()
    checksums = next((a for a in release.get('assets', []) if a.get('name') == 'SHA256SUMS.txt'), None)
    if checksums:
        path = work / 'SHA256SUMS.txt'
        downloader(checksums['browser_download_url'], path, expected_size=checksums.get('size'))
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?(.+)', line)
            if match and match[2] == asset['name']:
                return match[1].lower()
    raise UpdateError('更新ファイルのSHA256を確認できません。現在のファイルは変更しません。')


def member_path(name: str) -> Path:
    # Reject Windows drive/ADS paths on every OS, before any extraction.
    if '\\' in name or ':' in name or '\x00' in name:
        raise UpdateError(f'配布物に不正なパスがあります: {name}')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise UpdateError(f'配布物に不正なパスがあります: {name}')
    if any(p.endswith(('.', ' ')) or PureWindowsPath(p).is_reserved() for p in path.parts):
        raise UpdateError(f'配布物に不正なパスがあります: {name}')
    return Path(*path.parts)


def extract_archive(archive: Path, destination: Path) -> Path:
    """Extract regular files first, then validated internal POSIX symlinks."""
    destination.mkdir(); links = []; seen = set(); total = 0; directories = []
    def register(name, size):
        nonlocal total
        rel = member_path(name); folded = rel.as_posix().casefold()
        if folded in seen:
            raise UpdateError('配布物に重複するパスがあります。')
        seen.add(folded); total += size
        if total > MAX_EXPANDED:
            raise UpdateError('展開後の容量が大きすぎます。')
        return destination / rel
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as package:
            for item in package.infolist():
                dst = register(item.filename, item.file_size); mode = item.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise UpdateError('ZIP内のシンボリックリンクは受け付けません。')
                if item.is_dir():
                    dst.mkdir(parents=True, exist_ok=True); continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                with package.open(item) as source, dst.open('xb') as out:
                    shutil.copyfileobj(source, out)
                if mode: dst.chmod(mode & 0o777 & ~0o022)
    else:
        with tarfile.open(archive, 'r:gz') as package:
            for item in package:
                dst = register(item.name, item.size)
                if item.isdir():
                    dst.mkdir(parents=True, exist_ok=True); directories.append((dst, item.mode)); continue
                if item.issym():
                    link = PurePosixPath(item.linkname)
                    if link.is_absolute() or '\\' in item.linkname or ':' in item.linkname:
                        raise UpdateError('配布物のリンク先が不正です。')
                    # Links may contain '..', but must stay within this package's top folder.
                    resolved = (dst.parent / item.linkname).resolve()
                    top = destination / member_path(item.name).parts[0]
                    if not resolved.is_relative_to(top.resolve()):
                        raise UpdateError('配布物のリンク先がフォルダー外です。')
                    links.append((dst, item.linkname)); continue
                if not item.isfile():
                    raise UpdateError('配布物に未対応の特殊ファイルがあります。')
                dst.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(item) as source, dst.open('xb') as out:
                    shutil.copyfileobj(source, out)
                dst.chmod(item.mode & 0o777 & ~0o022)
        for dst, link in links:
            # No archive path may be an ancestor of another through a symlink.
            if dst.exists() or any(p.is_symlink() for p in dst.parents if p != destination.parent):
                raise UpdateError('配布物のリンクが通常ファイルと衝突しています。')
            dst.parent.mkdir(parents=True, exist_ok=True); dst.symlink_to(link)
        for path, mode in reversed(directories): path.chmod(mode & 0o777 & ~0o022)
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise UpdateError('配布物のフォルダー構成が想定と違います。')
    root = roots[0].resolve()
    for path in root.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            raise UpdateError('配布物のリンク先がフォルダー外です。')
    return root


def _remove(path: Path, root: Path):
    # Never follow a symlink/junction during rollback or cleanup.
    if path == root or not path.absolute().is_relative_to(root.absolute()):
        raise UpdateError('削除対象が作業フォルダー外です。')
    if not path.parent.resolve().is_relative_to(root.resolve()):
        raise UpdateError('削除対象の親が作業フォルダー外です。')
    if path.is_symlink(): path.unlink()
    elif getattr(path, 'is_junction', lambda: False)(): path.rmdir()
    elif path.is_dir(): shutil.rmtree(path)
    elif path.exists(): path.unlink()


def _journal(path: Path, value: dict):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as out:
        temp = Path(out.name)
        try:
            json.dump(value, out, ensure_ascii=False, indent=2); out.flush(); os.fsync(out.fileno())
        except BaseException:
            out.close(); temp.unlink(missing_ok=True); raise
    try: os.replace(temp, path)
    finally: temp.unlink(missing_ok=True)


def rollback(work: Path, target: Path):
    journal_path = work / 'transaction.json'; value = json.loads(journal_path.read_text(encoding='utf-8'))
    if (value.get('target') != str(target) or work.resolve().parent != target
            or not work.name.startswith(WORK_PREFIX)
            or len(member_path(value['package']).parts) != 1):
        raise UpdateError('復旧記録の対象が一致しません。')
    for operation in reversed(value['operations']):
        rel = member_path(operation['path'])
        if kept(rel): raise UpdateError('復旧記録に利用者データが含まれています。')
        dst = target / rel; backup = work / 'backup' / rel; staged = work / 'unpacked' / value['package'] / rel
        if backup.exists() or backup.is_symlink():
            _remove(dst, target); dst.parent.mkdir(parents=True, exist_ok=True); os.replace(backup, dst)
        elif not operation['had_old'] and not staged.exists() and not staged.is_symlink():
            _remove(dst, target)
    value['status'] = 'rolled_back'; _journal(journal_path, value)


def recover_pending(target: Path):
    for work in sorted(target.glob(WORK_PREFIX + '*')):
        if work.is_symlink() or not work.is_dir(): continue
        path = work / 'transaction.json'
        if not path.is_file(): continue
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('target') != str(target): continue
        if value.get('status') not in ('complete', 'rolled_back'):
            print('[update] 前回中断した更新を元に戻しています。', flush=True); rollback(work, target)
        _remove(work, target)


def app_running(home: Path) -> bool:
    from installer.installer_lib import load_env_file
    load_env_file(home / '.env')
    try: port = int(os.environ.get('SHOGI_ANALYZER_PORT') or 31145)
    except ValueError: port = 31145
    for host in ('127.0.0.1', '::1'):
        try:
            with socket.create_connection((host, port), timeout=.3): return True
        except OSError: pass
    return False


def self_check(root: Path):
    exe = root / ('ShogiAnalyzer.exe' if sys.platform == 'win32' else 'ShogiAnalyzer')
    env = external_env(); env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    with external_libraries():
        result = subprocess.run([str(exe), '--self-check'], cwd=root, env=env,
                                capture_output=True, timeout=120)
    if result.returncode:
        raise UpdateError('新しいアプリの起動確認に失敗しました。')


def apply_package(package: Path, target: Path, work: Path, *, native: bool, home: Path, version: str):
    from server.app.services.update_checker import compare_versions
    version_file = package / ('_internal/VERSION' if native else 'VERSION')
    if not version_file.is_file() or compare_versions(version_file.read_text().strip(), version) != 0:
        raise UpdateError('配布物内のバージョンが一致しません。')
    if native:
        names = {p.name for p in package.iterdir()}
        if names - NATIVE_NAMES - {LOCK_NAME} or not (package/'_internal').is_dir() or (package/'_internal').is_symlink():
            raise UpdateError('ネイティブ配布物の構成が想定と違います。')
        executable = 'ShogiAnalyzer.exe' if sys.platform == 'win32' else 'ShogiAnalyzer'
        if not (package/executable).is_file() or (package/executable).is_symlink():
            raise UpdateError('対応する実行ファイルがありません。')
        self_check(package)
        paths = [Path(n) for n in sorted(names - {LOCK_NAME})]
    else:
        if not (package/'installer/run.py').is_file() or not (package/'server/assets_web/index.html').is_file():
            raise UpdateError('ソース配布物の構成が想定と違います。')
        paths = [p.relative_to(package) for p in sorted(package.rglob('*')) if p.is_file() or p.is_symlink()]
        if any((package/p).is_symlink() for p in paths):
            raise UpdateError('ソース配布物にリンクが含まれています。')
        paths = [p for p in paths if not kept(p)]
        paths.sort(key=lambda p: (p.name == 'VERSION', str(p)))
    for rel in paths:
        if kept(rel): raise UpdateError('利用者データを上書きする配布物です。')
        if home != target and (home == target/rel or home.is_relative_to(target/rel)):
            raise UpdateError('データ保存先がアプリの置換対象と重なっています。')
        for key in ('SHOGI_ANALYZER_ENGINE_PATH', 'SHOGI_ANALYZER_ENGINE_EVAL_DIR'):
            configured = os.environ.get(key, '').strip()
            if configured:
                engine = (home / configured).resolve()
                if engine == target/rel or engine.is_relative_to(target/rel):
                    raise UpdateError('エンジンの保存先がアプリの置換対象と重なっています。')
        for parent in (target/rel).parents:
            if parent == target: break
            if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
                raise UpdateError('更新先の親がリンクになっています。')
            if parent.exists() and not parent.is_dir(): raise UpdateError('更新先のフォルダーがファイルと衝突しています。')
    if app_running(home): raise UpdateError('ShogiAnalyzerを終了してから更新してください。')
    value = {'target': str(target), 'package': package.name, 'status': 'applying', 'operations': []}
    path = work/'transaction.json'; _journal(path, value)
    try:
        for rel in paths:
            dst = target/rel; old = work/'backup'/rel
            value['operations'].append({'path': rel.as_posix(), 'had_old': dst.exists() or dst.is_symlink()})
            _journal(path, value)  # Record intent before either atomic rename.
            if dst.exists() or dst.is_symlink():
                old.parent.mkdir(parents=True, exist_ok=True)
                if dst.is_dir() and not dst.is_symlink(): os.replace(dst, old)
                elif dst.is_symlink(): old.symlink_to(os.readlink(dst))
                else:
                    with tempfile.NamedTemporaryFile(dir=old.parent, delete=False) as partial:
                        partial_path = Path(partial.name)
                    shutil.copy2(dst, partial_path); os.replace(partial_path, old)
            dst.parent.mkdir(parents=True, exist_ok=True); os.replace(package/rel, dst)
        if native: self_check(target)
        value['status'] = 'complete'; _journal(path, value)
    except BaseException as exc:
        try: rollback(work, target)
        except BaseException as recovery_error:
            raise UpdateError(f'自動復旧が完了していません。バックアップを残しました: {work}') from recovery_error
        raise UpdateError('更新に失敗したため、元のアプリへ戻しました。') from exc


def perform_update(target: Path, home: Path, *, native: bool, confirm=None, fetch_release=None, downloader=download):
    from installer.installer_lib import load_env_file
    from server.app.services.update_checker import _latest_release, _repo, compare_versions
    target = target.resolve(); home = home.resolve(); load_env_file(home/'.env')
    current_file = target / ('_internal/VERSION' if native else 'VERSION')
    with installation_lock(target):
        if app_running(home): raise UpdateError('ShogiAnalyzerを終了してから更新してください。')
        recover_pending(target)
        if not current_file.is_file(): raise UpdateError('更新対象のアプリが見つかりません。')
        release = (fetch_release or _latest_release)(_repo())
        current = current_file.read_text().strip(); latest = str(release.get('tag_name') or '')
        if not re.fullmatch(r'v?\d+(?:\.\d+){1,3}(?:-[A-Za-z0-9.-]+)?', latest):
            raise UpdateError('最新リリースのバージョン情報を確認できません。')
        print(f'[update] 現在: v{current} / 最新: {latest}', flush=True)
        if compare_versions(current, latest) >= 0:
            print('[update] 最新です。更新は必要ありません。', flush=True); return False
        asset = select_asset(release, native=native)
        answer = confirm() if confirm else input('[update] 設定・棋譜・エンジンを残して更新しますか？ [y/N]: ').strip().lower() in ('y', 'yes')
        if not answer:
            print('[update] 更新を中止しました。', flush=True); return False
        work = Path(tempfile.mkdtemp(prefix=WORK_PREFIX, dir=target))
        try:
            expected = asset_digest(asset, release, work, downloader)
            archive = work/asset['name']; print('[update] 更新ファイルをダウンロードしています。', flush=True)
            actual = downloader(asset['browser_download_url'], archive, expected_size=asset.get('size'))
            if actual.lower() != expected: raise UpdateError('SHA256が一致しません。アプリは変更していません。')
            package = extract_archive(archive, work/'unpacked')
            apply_package(package, target, work, native=native, home=home, version=latest)
        except BaseException:
            journal = work/'transaction.json'
            if not journal.exists() or json.loads(journal.read_text())['status'] == 'rolled_back': _remove(work, target)
            raise
        try: _remove(work, target)
        except OSError:
            print(f'[update] 更新は完了しました。削除できなかった作業フォルダー: {work}', flush=True)
        print('[update] 更新しました。通常どおりShogiAnalyzerを起動してください。', flush=True); return True


def _prepare_helper(job: Path):
    if not is_frozen(): raise UpdateError('更新用実行環境の準備はネイティブ版で行ってください。')
    target = installation_root().resolve(); job = job.absolute()
    if job.is_symlink() or not job.name.startswith(JOB_PREFIX) or not job.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise UpdateError('更新用の一時フォルダーが不正です。')
    if job.resolve().is_relative_to(target) or target.is_relative_to(job.resolve()):
        raise UpdateError('更新用一時フォルダーとアプリの場所が重なっています。')
    job.mkdir(mode=0o700, exist_ok=True)
    if any(job.iterdir()): raise UpdateError('更新用一時フォルダーが空ではありません。')
    try:
        exe = Path(sys.executable)
        shutil.copy2(exe, job/exe.name)
        shutil.copytree(target/'_internal', job/'_internal', symlinks=True)
        info = {'schema': 1, 'target': str(target), 'home': str(runtime_home().resolve())}
        (job/'job.json').write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8'); (job/'job.json').chmod(0o600)
        (job/'RunUpdate.bat').write_text('@echo off\n"%~dp0ShogiAnalyzer.exe" --update-job "%~dp0job.json"\nset "SA_UPDATE_RESULT=%ERRORLEVEL%"\n"%SA_UPDATE_INSTALL%ShogiAnalyzer.exe" --cleanup-update "%~dp0." & pause & exit /b %SA_UPDATE_RESULT%\n', encoding='utf-8', newline='\r\n')
        # This small launcher survives a power loss while _internal is being swapped.
        # Its helper and runtime live outside the installation, including on Windows.
        _journal(target/'.UpdateRecovery.json', {'job': str(job.resolve())})
        if sys.platform == 'win32':
            recovery = target/'.UpdateRecovery.bat'
            text = '@echo off\nsetlocal DisableDelayedExpansion\nset "SA_UPDATE_INSTALL=%~dp0"\n"' + str(job/'RunUpdate.bat').replace('%','%%') + '"\n'
            newline = '\r\n'
        else:
            import shlex
            recovery = target/'.UpdateRecovery.sh'
            text = '#!/bin/sh\nmain() {\n here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || return 1\n job=' + shlex.quote(str(job)) + '\n "$job/ShogiAnalyzer" --update-job "$job/job.json"\n result=$?\n "$here/ShogiAnalyzer" --cleanup-update "$job"\n return "$result"\n}\nmain "$@"; exit "$?"\n'
            newline = '\n'
        partial = recovery.with_suffix(recovery.suffix + '.tmp')
        with partial.open('w', encoding='utf-8', newline=newline) as out:
            out.write(text); out.flush(); os.fsync(out.fileno())
        partial.chmod(0o700); os.replace(partial, recovery)
    except BaseException:
        for name in ('.UpdateRecovery.bat', '.UpdateRecovery.sh', '.UpdateRecovery.json'):
            (target/name).unlink(missing_ok=True)
        _remove(job, Path(tempfile.gettempdir()).resolve()); raise


def prepare_helper(job: Path):
    with installation_lock(installation_root()):
        if any((installation_root()/name).exists() for name in ('.UpdateRecovery.bat', '.UpdateRecovery.sh')):
            raise UpdateError('前回の更新処理が残っています。Updateから再実行してください。')
        if app_running(runtime_home()): raise UpdateError('ShogiAnalyzerを終了してから更新してください。')
        _prepare_helper(job)


def cleanup_helper(job: Path):
    job = job.resolve(); temp = Path(tempfile.gettempdir()).resolve()
    if job == temp or not job.is_relative_to(temp) or not job.name.startswith(JOB_PREFIX):
        raise UpdateError('削除対象が更新用一時フォルダーではありません。')
    info = json.loads((job/'job.json').read_text(encoding='utf-8'))
    if info.get('target') != str(installation_root().resolve()):
        raise UpdateError('更新用一時フォルダーの対象が一致しません。')
    target = installation_root().resolve()
    for work in target.glob(WORK_PREFIX + '*'):
        journal = work/'transaction.json'
        if journal.is_file() and json.loads(journal.read_text(encoding='utf-8')).get('status') not in ('complete', 'rolled_back'):
            raise UpdateError('未完了の復旧記録があるため、更新用実行環境を残します。Updateから再実行してください。')
    # Do not remove a helper which another update invocation is still using.
    with installation_lock(job): pass
    pointer = target/'.UpdateRecovery.json'
    if pointer.is_file() and json.loads(pointer.read_text(encoding='utf-8')).get('job') == str(job):
        for name in ('.UpdateRecovery.bat', '.UpdateRecovery.sh', '.UpdateRecovery.json'):
            (target/name).unlink(missing_ok=True)
    _remove(job, temp)


def run_job(path: Path, **options):
    path = path.resolve(); info = json.loads(path.read_text(encoding='utf-8'))
    if info.get('schema') != 1 or path.parent != installation_root().resolve():
        raise UpdateError('更新処理は準備済みの一時フォルダーから実行してください。')
    target = Path(info['target']).resolve()
    if target == path.parent or path.parent.is_relative_to(target): raise UpdateError('更新元と対象が同じです。')
    os.environ['SHOGI_ANALYZER_HOME'] = info['home']
    with installation_lock(path.parent):
        return perform_update(target, Path(info['home']), native=True, **options)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) == 2 and args[0] == '--prepare-update': prepare_helper(Path(args[1]))
        elif len(args) == 2 and args[0] == '--cleanup-update': cleanup_helper(Path(args[1]))
        elif len(args) == 2 and args[0] == '--update-job': run_job(Path(args[1]))
        elif not args and not is_frozen(): perform_update(installation_root(), runtime_home(), native=False)
        else: raise UpdateError('Update.bat / Update.sh / Update.commandから実行してください。')
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f'[update] {exc or "中断しました。"}', file=sys.stderr, flush=True); return 1


if __name__ == '__main__':
    raise SystemExit(main())
