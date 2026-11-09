"""Build an app-only native package. Run in a clean venv with requirements-portable.txt."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from portable_licenses import collect, audit_bundle, bundle_windows_runtime
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer.update_launchers import write_launchers

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'portable')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    license_stage = tempfile.TemporaryDirectory(prefix='license-stage-', dir=output)
    if not Path(license_stage.name).resolve().is_relative_to(output):
        raise RuntimeError('License staging escaped build output')
    license_dir, source_dir = collect(Path(license_stage.name))
    # Explicit allowlist: never add the whole repository, engines, evaluation files,
    # .env, databases or user-generated shares to the frozen bundle.
    resources = [('.env.template', '.'), ('VERSION', '.'), ('LICENSE', '.'),
        ('installer/manifest.json', 'installer'), ('server/assets_web', 'server/assets_web'),
        ('server/app/services/share_fonts', 'server/app/services/share_fonts')]
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--noupx',
        '--name', 'ShogiAnalyzer', '--paths', str(ROOT), '--distpath', str(output / 'app'),
        '--workpath', str(output / 'build'), '--specpath', str(output),
        '--additional-hooks-dir', str(ROOT / 'tools' / 'pyinstaller_hooks'),
        '--exclude-module', 'shogi', '--exclude-module', 'pytest', '--exclude-module', 'tkinter', '--exclude-module', 'numpy',
        '--exclude-module', 'setuptools', '--exclude-module', 'pip', '--exclude-module', 'uvloop',
        '--exclude-module', 'watchfiles', '--exclude-module', 'httptools', '--exclude-module', 'IPython', '--exclude-module', 'readline',
        '--exclude-module', 'dbm', '--exclude-module', '_gdbm', '--exclude-module', '_dbm']
    for source, target in resources:
        cmd += ['--add-data', f'{ROOT / source}:{target}']
    if sys.platform.startswith('linux'):
        cmd += ['--collect-data', 'certifi']
    cmd += ['--add-data', f'{license_dir}:third_party_notices']
    for module in ['argparse', 'server.app.main', 'uvicorn.logging', 'uvicorn.loops.asyncio', 'uvicorn.protocols.http.h11_impl',
            'uvicorn.protocols.websockets.websockets_impl', 'uvicorn.lifespan.on']:
        cmd += ['--hidden-import', module]
    cmd += [str(ROOT / 'installer' / 'portable_entry.py')]
    subprocess.run(cmd, check=True, cwd=ROOT)
    folder = output / 'app' / 'ShogiAnalyzer'
    exe = folder / ('ShogiAnalyzer.exe' if sys.platform == 'win32' else 'ShogiAnalyzer')
    shutil.copytree(source_dir, folder / 'third_party_sources', dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'docs/THIRD_PARTY.md', folder / 'THIRD_PARTY.txt')
    bundle_windows_runtime(folder)
    audit_bundle(folder)
    subprocess.run([str(exe), '--self-check'], check=True)
    shutil.copyfile(ROOT / 'docs' / 'PORTABLE.md', folder / 'README.txt')
    if sys.platform == 'darwin':
        start = folder / 'Start.command'
        start.write_text('#!/bin/sh\ncd -- "$(dirname -- "$0")" || exit 1\nexec ./ShogiAnalyzer\n', encoding='utf-8')
        start.chmod(0o755)
    write_launchers(folder, sys.platform)
    build_info = {'version': (ROOT/'VERSION').read_text().strip(),
        'commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'worktree_dirty': bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        'python': sys.version, 'platform': platform.platform(),
        'license_inventory': '_internal/third_party_notices/INVENTORY.json',
        'library_sources': 'third_party_sources/SOURCES.json'}
    (folder/'BUILD_INFO.json').write_text(json.dumps(build_info, indent=2)+'\n',encoding='utf-8')
    version = (ROOT / 'VERSION').read_text().strip()
    arch = {'x86_64': 'amd64', 'x64': 'amd64', 'aarch64': 'arm64'}.get(platform.machine().lower(), platform.machine().lower())
    os_key = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, sys.platform)
    basename = f'ShogiAnalyzer-v{version}-{os_key}-{arch}'
    archive = output / (basename + ('.zip' if sys.platform == 'win32' else '.tar.gz'))
    if sys.platform == 'win32':
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for path in folder.rglob('*'):
                if path.is_file():
                    package.write(path, Path('ShogiAnalyzer') / path.relative_to(folder))
    else:
        # tar preserves POSIX permissions and PyInstaller's symlinks.
        with tarfile.open(archive, 'w:gz', dereference=False) as package:
            package.add(folder, arcname='ShogiAnalyzer')
    report = {'archive': archive.name, 'compressed_bytes': archive.stat().st_size,
        'expanded_bytes': sum(p.stat().st_size for p in folder.rglob('*') if p.is_file() and not p.is_symlink()),
        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'python': sys.version,
        'platform': platform.platform(), 'engines_included': False, 'evaluations_included': False,
        'commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'license_sources_included': True, 'lgpl_modules_external': True,
        'microsoft_runtime_bundled': sys.platform == 'win32'}
    (output / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (output / 'build-requirements.lock').write_text(''.join(sorted(f"{d.metadata['Name']}=={d.version}\n" for d in metadata.distributions())), encoding='utf-8')
    license_stage.cleanup()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
