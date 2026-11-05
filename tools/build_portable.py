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
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def notices(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
        name = dist.metadata['Name']
        if name.lower() in {'pip', 'setuptools', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'pefile', 'pywin32-ctypes', 'wheel'}:
            continue
        rows.append(f"{name}=={dist.version} — {dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'See bundled license files'}")
        for item in dist.files or []:
            if any(part.lower().startswith(('license', 'copying', 'notice', 'authors')) for part in item.parts):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = dest / name / str(item)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        python_license = Path(sys.base_prefix) / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copyfile(python_license, dest / 'CPython-LICENSE.txt')
    else:
        # CPython's sysconfig points to the license on several Linux layouts.
        import sysconfig
        license_path = Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt'
        if not license_path.is_file():
            raise RuntimeError('CPython LICENSE.txt missing from build interpreter')
        shutil.copyfile(license_path, dest / 'CPython-LICENSE.txt')
    (dest / 'DEPENDENCIES.txt').write_text('\n'.join(rows) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'portable')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    license_dir = output / 'notices'
    notices(license_dir)
    # Explicit allowlist: never add the whole repository, engines, evaluation files,
    # .env, databases or user-generated shares to the frozen bundle.
    resources = [('.env.template', '.'), ('VERSION', '.'), ('LICENSE', '.'),
        ('installer/manifest.json', 'installer'), ('server/assets_web', 'server/assets_web'),
        ('server/app/services/share_fonts', 'server/app/services/share_fonts')]
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--noupx',
        '--name', 'ShogiAnalyzer', '--paths', str(ROOT), '--distpath', str(output / 'app'),
        '--workpath', str(output / 'build'), '--specpath', str(output),
        '--exclude-module', 'pytest', '--exclude-module', 'tkinter', '--exclude-module', 'numpy',
        '--exclude-module', 'setuptools', '--exclude-module', 'pip', '--exclude-module', 'uvloop',
        '--exclude-module', 'watchfiles', '--exclude-module', 'httptools', '--exclude-module', 'IPython']
    for source, target in resources:
        cmd += ['--add-data', f'{ROOT / source}:{target}']
    cmd += ['--add-data', f'{license_dir}:third_party_notices']
    for module in ['argparse', 'server.app.main', 'uvicorn.logging', 'uvicorn.loops.asyncio', 'uvicorn.protocols.http.h11_impl',
            'uvicorn.protocols.websockets.websockets_impl', 'uvicorn.lifespan.on']:
        cmd += ['--hidden-import', module]
    cmd += [str(ROOT / 'installer' / 'portable_entry.py')]
    subprocess.run(cmd, check=True, cwd=ROOT)
    folder = output / 'app' / 'ShogiAnalyzer'
    exe = folder / ('ShogiAnalyzer.exe' if sys.platform == 'win32' else 'ShogiAnalyzer')
    subprocess.run([str(exe), '--self-check'], check=True)
    shutil.copyfile(ROOT / 'docs' / 'PORTABLE.md', folder / 'README.txt')
    if sys.platform == 'darwin':
        start = folder / 'Start.command'
        start.write_text('#!/bin/sh\ncd -- "$(dirname -- "$0")" || exit 1\nexec ./ShogiAnalyzer\n', encoding='utf-8')
        start.chmod(0o755)
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
        'platform': platform.platform(), 'engines_included': False, 'evaluations_included': False}
    (output / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (output / 'build-requirements.lock').write_text(''.join(sorted(f"{d.metadata['Name']}=={d.version}\n" for d in metadata.distributions())), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
