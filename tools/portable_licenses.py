"""Collect notices and corresponding LGPL sources for the actual runtime dependency graph."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shutil
import ssl
import sqlite3
import sys
import sysconfig
import urllib.request
import zlib
import zipfile
import xml.etree.ElementTree as ET

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
LGPL_MODULES = {'py7zr': 'py7zr', 'pybcj': 'bcj', 'inflate64': 'inflate64',
    'multivolumefile': 'multivolumefile', 'pyppmd': 'pyppmd'}


def runtime_distributions() -> list:
    pending = []
    for line in (ROOT / 'tools/requirements-portable.txt').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            req = Requirement(line)
            if canonicalize_name(req.name) != 'pyinstaller':
                pending.append(req)
    found = {}
    while pending:
        req = pending.pop()
        if req.marker and not req.marker.evaluate({'extra': ''}):
            continue
        name = canonicalize_name(req.name)
        if name in found:
            continue
        dist = metadata.distribution(name)
        if req.specifier and not req.specifier.contains(dist.version):
            raise RuntimeError(f'Installed version does not satisfy {req}')
        found[name] = dist
        pending.extend(Requirement(item) for item in dist.requires or [])
    return [found[key] for key in sorted(found)]


def fetch(url: str, dest: Path, expected: str | None = None) -> str:
    if not url.startswith('https://'):
        raise ValueError('Use HTTPS for source and license downloads')
    if dest.is_file() and expected and hashlib.sha256(dest.read_bytes()).hexdigest() == expected:
        return expected
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={'User-Agent':'ShogiAnalyzer-license-builder'})
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
    digest = hashlib.sha256(content).hexdigest()
    if expected and digest != expected:
        raise RuntimeError(f'Source digest mismatch: {dest.name}')
    dest.write_bytes(content)
    return digest


def collect(output: Path) -> tuple[Path, Path]:
    licenses, sources = output / 'notices', output / 'third_party_sources'
    licenses.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    inventory = []
    for dist in runtime_distributions():
        name = canonicalize_name(dist.metadata['Name'])
        expression = dist.metadata.get('License-Expression') or dist.metadata.get('License') or ''
        if name == 'python-shogi' or ('GPL' in expression.upper() and 'LGPL' not in expression.upper()):
            raise RuntimeError(f'Unreviewed GPL runtime dependency: {name}')
        if not any(token in expression.upper() for token in ('MIT', 'BSD', 'APACHE', 'PSF', 'LGPL', 'PUBLIC DOMAIN', 'ZLIB')):
            raise RuntimeError(f'Unreviewed runtime license: {name}: {expression}')
        copied = []
        for item in dist.files or []:
            if any(part.lower().startswith(('license','copying','notice','authors')) for part in item.parts):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = licenses / name / str(item)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    copied.append(target.relative_to(licenses).as_posix())
        if not copied:
            raise RuntimeError(f'No license text supplied by installed distribution: {name}')
        row = {'name':name, 'version':dist.version, 'license':expression, 'notices':copied}
        if 'LGPL' in expression.upper():
            if name not in LGPL_MODULES:
                raise RuntimeError(f'No replacement test for LGPL dependency: {name}')
            url = f'https://pypi.org/pypi/{name}/{dist.version}/json'
            with urllib.request.urlopen(url, timeout=30) as response:
                release = json.load(response)
            sdists = [item for item in release['urls'] if item['packagetype'] == 'sdist']
            if len(sdists) != 1:
                raise RuntimeError(f'Expected exactly one source distribution: {name}')
            item = sdists[0]
            filename = Path(item['filename']).name
            digest = fetch(item['url'], sources / filename, item['digests']['sha256'])
            row['source'] = {'file':filename, 'url':item['url'], 'sha256':digest}
            row['module'] = LGPL_MODULES[name]
        inventory.append(row)

    candidates = [Path(sys.base_prefix)/'LICENSE.txt', Path(sysconfig.get_path('stdlib'))/'LICENSE.txt']
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license is None:
        raise RuntimeError('Build interpreter must provide its complete Python LICENSE.txt')
    shutil.copyfile(python_license, licenses/'CPython-LICENSE.txt')
    references = []
    version = platform.python_version()
    url = f'https://docs.python.org/release/{version}/license.html'
    references.append({'component':'CPython incorporated software', 'url':url,
        'file':'Python-incorporated-software.html', 'sha256':fetch(url, licenses/'Python-incorporated-software.html')})
    # Includes source acknowledgements for libffi, zlib, xz and other runtime libs.
    url = 'https://raw.githubusercontent.com/astral-sh/python-build-standalone/20250409/python-licenses.rst'
    references.append({'component':'Additional native-library license reference (may list unused components)', 'url':url,
        'file':'native-library-licenses.rst', 'sha256':fetch(url,licenses/'native-library-licenses.rst')})
    openssl = ssl.OPENSSL_VERSION.split()[1]
    url = f'https://raw.githubusercontent.com/openssl/openssl/openssl-{openssl}/LICENSE.txt'
    references.append({'component':'OpenSSL '+openssl, 'url':url,
        'file':'OpenSSL-LICENSE.txt', 'sha256':fetch(url,licenses/'OpenSSL-LICENSE.txt')})
    url = 'https://raw.githubusercontent.com/gcc-mirror/gcc/master/COPYING.RUNTIME'
    references.append({'component':'GCC Runtime Library Exception (if GCC runtimes are present)', 'url':url,
        'file':'GCC-RUNTIME-EXCEPTION.txt', 'sha256':fetch(url,licenses/'GCC-RUNTIME-EXCEPTION.txt')})
    url = 'https://raw.githubusercontent.com/gcc-mirror/gcc/master/COPYING3'
    references.append({'component':'GCC GPL text (subject to runtime exception)', 'url':url,
        'file':'GCC-COPYING3.txt', 'sha256':fetch(url,licenses/'GCC-COPYING3.txt')})
    (licenses/'INVENTORY.json').write_text(json.dumps({'packages':inventory,'native_references':references,
        'interpreter':sys.version,'openssl':ssl.OPENSSL_VERSION,'sqlite':sqlite3.sqlite_version,
        'zlib':zlib.ZLIB_RUNTIME_VERSION},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (licenses/'DEPENDENCIES.txt').write_text(''.join(f"{r['name']}=={r['version']} — {r['license']}\n" for r in inventory),encoding='utf-8')
    (sources/'SOURCES.json').write_text(json.dumps([r for r in inventory if 'source' in r],indent=2)+'\n',encoding='utf-8')
    # Reusing an output folder must not retain earlier development-only notices.
    # Only generated files under this notices folder are removed.
    for old in ('Microsoft-runtime-terms.html','Microsoft-runtime-terms.docx','Microsoft-runtime-terms.txt'):
        path=licenses/old
        if path.is_file(): path.unlink()
    return licenses, sources


def audit_bundle(folder: Path) -> None:
    internal = folder/'_internal'
    for module in LGPL_MODULES.values():
        if not (internal/module/'__init__.py').is_file():
            raise RuntimeError(f'LGPL module is not present as replaceable source: {module}')
    from PyInstaller.archive.readers import ZlibArchiveReader
    pyz = folder.parent.parent/'build'/'ShogiAnalyzer'/'PYZ-00.pyz'
    modules = ZlibArchiveReader(str(pyz)).toc
    forbidden = {'shogi',*LGPL_MODULES.values()}
    embedded = [name for name in modules if name.split('.')[0] in forbidden]
    if embedded:
        raise RuntimeError(f'Excluded or replaceable libraries embedded in PYZ: {embedded}')
    names = [path.name.lower() for path in internal.rglob('*') if path.is_file()]
    for name in names:
        if re.search(r'lib(readline|history|gdbm|db-|gmp)', name):
            raise RuntimeError(f'Unreviewed native copyleft component: {name}')
    (internal/'third_party_notices'/'NATIVE_FILES.txt').write_text('\n'.join(sorted(
        path.relative_to(internal).as_posix() for path in internal.rglob('*')
        if path.is_file() and (path.suffix.lower() in {'.dll','.pyd','.dylib'} or '.so' in path.name)))+'\n',encoding='utf-8')


def windows_system_runtime(folder: Path) -> None:
    if sys.platform != 'win32':
        return
    # Do not redistribute Microsoft's runtime DLLs under the PSF/MIT license.
    # Windows 10+ supplies UCRT; VC runtime comes from the user's official install.
    internal=(folder/'_internal').resolve()
    removed=[]
    for path in internal.rglob('*.dll'):
        name=path.name.lower()
        if name.startswith(('api-ms-win-','vcruntime','msvcp','concrt','msvcr')) or name=='ucrtbase.dll':
            if not path.resolve().is_relative_to(internal):
                raise RuntimeError('Unexpected library path outside application bundle')
            removed.append(path.relative_to(internal).as_posix())
            path.unlink()
    (internal/'third_party_notices'/'WINDOWS_SYSTEM_RUNTIME.txt').write_text(
        'Microsoft Windows / VC Runtime DLLs are not redistributed in this package.\n'
        'Requires Windows 10 or later and the official Microsoft Visual C++ x64 Runtime.\n'
        'Start.bat checks the runtime and links to Microsoft if it is absent.\n'
        'https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist\n'
        'Removed from generated bundle:\n'+'\n'.join(removed)+'\n',encoding='utf-8')
    (folder/'Start.bat').write_text('@echo off\nsetlocal\nset "SA_SYSTEM=%SystemRoot%\\System32"\nif defined PROCESSOR_ARCHITEW6432 set "SA_SYSTEM=%SystemRoot%\\Sysnative"\nif not exist "%SA_SYSTEM%\\vcruntime140.dll" goto missing_runtime\nif not exist "%SA_SYSTEM%\\vcruntime140_1.dll" goto missing_runtime\n"%~dp0ShogiAnalyzer.exe" %*\nset "SA_RESULT=%ERRORLEVEL%"\nif not "%SA_RESULT%"=="0" pause\nexit /b %SA_RESULT%\n:missing_runtime\necho Microsoft Visual C++ Runtime x64 is required. Python is included.\necho Install it from Microsoft\'s official page, then run Start.bat again.\necho https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist\nstart "" "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist"\npause\nexit /b 2\n',encoding='utf-8',newline='\r\n')
