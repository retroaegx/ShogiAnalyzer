"""Collect notices and corresponding LGPL sources for the actual runtime dependency graph."""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import ssl
import sqlite3
import subprocess
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
WINDOWS_RUNTIME_DLLS = ('vcruntime140.dll', 'vcruntime140_1.dll')


def collect_windows_licenses(licenses: Path, references: list) -> None:
    if sys.platform != 'win32':
        return
    documents = [
        ('Microsoft Visual C++ Runtime end-user terms', 'Microsoft-runtime-terms',
         'https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx',
         'f1e3d56ceb2ad68aae0711b910375009e651ac5530fa0760f0dea6e81e54fae1'),
        ('Visual Studio 2022 redistribution license reference', 'Microsoft-VS2022-terms',
         'https://visualstudio.microsoft.com/wp-content/uploads/2021/11/Visual-Studio-2022-Community-License-EN.docx',
         '41a207b10c8ab91d0d2f10a854715f73dca54509581692d2fe179aa3ffcb8540'),
    ]
    namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    for component, name, url, expected in documents:
        target = licenses / (name + '.docx')
        digest = fetch(url, target, expected)
        with zipfile.ZipFile(target) as document:
            tree = ET.fromstring(document.read('word/document.xml'))
        # Preserve the complete text and the unmodified official document.
        text = '\n'.join(''.join(node.text or '' for node in paragraph.findall('.//w:t', namespace))
                         for paragraph in tree.findall('.//w:p', namespace)) + '\n'
        (licenses / (name + '.txt')).write_text(text, encoding='utf-8')
        references.append({'component': component, 'url': url, 'file': target.name,
                           'sha256': digest, 'text_file': name + '.txt'})
    for component, name, url in [
        ('Visual Studio 2022 redistributable file list', 'Microsoft-REDIST.html',
         'https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution'),
        ('CPython Windows additional conditions', 'CPython-Windows-conditions.txt',
         f'https://raw.githubusercontent.com/python/cpython/v{platform.python_version()}/PC/crtlicense.txt'),
    ]:
        references.append({'component': component, 'url': url, 'file': name,
                           'sha256': fetch(url, licenses / name)})


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
        reviewed_mpl = name == 'certifi' and 'MPL' in expression.upper()
        if not reviewed_mpl and not any(token in expression.upper() for token in ('MIT', 'BSD', 'APACHE', 'PSF', 'LGPL', 'PUBLIC DOMAIN', 'ZLIB')):
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
        if 'LGPL' in expression.upper() or reviewed_mpl:
            if not reviewed_mpl and name not in LGPL_MODULES:
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
            if name in LGPL_MODULES:
                row['module'] = LGPL_MODULES[name]
        inventory.append(row)

    candidates = [Path(sys.base_prefix)/'LICENSE.txt', Path(sysconfig.get_path('stdlib'))/'LICENSE.txt']
    python_license = next((path for path in candidates if path.is_file()), None)
    if python_license is None:
        raise RuntimeError('Build interpreter must provide its complete Python LICENSE.txt')
    shutil.copyfile(python_license, licenses/'CPython-LICENSE.txt')
    references = []
    bootloader=metadata.distribution('pyinstaller')
    copying=next((Path(bootloader.locate_file(item)) for item in bootloader.files or []
                  if item.name=='COPYING.txt'),None)
    if copying is None or not copying.is_file():
        raise RuntimeError('PyInstaller licensing exception reference is missing')
    shutil.copyfile(copying,licenses/'PyInstaller-COPYING.txt')
    references.append({'component':'Unmodified PyInstaller bootloader licensing exception reference',
        'url':f'https://github.com/pyinstaller/pyinstaller/blob/v{bootloader.version}/COPYING.txt',
        'file':'PyInstaller-COPYING.txt','sha256':hashlib.sha256(copying.read_bytes()).hexdigest()})
    for name,directory in [('Barlow-Semi-Condensed','barlowsemicondensed'),('Shippori-Mincho-B1','shipporiminchob1')]:
        source=ROOT/'docs/third_party_fonts'/(name+'-OFL.txt')
        shutil.copyfile(source,licenses/source.name)
        references.append({'component':name+' external web font (font binary not bundled)',
            'url':f'https://github.com/google/fonts/blob/main/ofl/{directory}/OFL.txt',
            'file':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
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
    collect_windows_licenses(licenses, references)
    (licenses/'INVENTORY.json').write_text(json.dumps({'packages':inventory,'native_references':references,
        'interpreter':sys.version,'openssl':ssl.OPENSSL_VERSION,'sqlite':sqlite3.sqlite_version,
        'zlib':zlib.ZLIB_RUNTIME_VERSION},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (licenses/'DEPENDENCIES.txt').write_text(''.join(f"{r['name']}=={r['version']} — {r['license']}\n" for r in inventory),encoding='utf-8')
    (sources/'SOURCES.json').write_text(json.dumps([r for r in inventory if 'source' in r],indent=2)+'\n',encoding='utf-8')
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


def bundle_windows_runtime(folder: Path) -> None:
    if sys.platform != 'win32':
        return
    import pefile

    # Obtain original release DLLs from Visual Studio's REDIST directory, rather
    # than harvesting a user's System32 files. Build machines must be licensed
    # for redistribution under the relevant Visual Studio terms.
    vswhere=Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
    instances=json.loads(subprocess.check_output([
        str(vswhere), '-products', '*', '-version', '[17.0,18.0)', '-format', 'json', '-utf8'],
        encoding='utf-8'))
    candidates=[]
    for instance in instances:
        root=Path(instance['installationPath'])/'VC/Redist/MSVC'
        for directory in root.glob('*/x64/Microsoft.VC*.CRT'):
            if all((directory/name).is_file() for name in WINDOWS_RUNTIME_DLLS):
                with pefile.PE(str(directory/WINDOWS_RUNTIME_DLLS[0])) as image:
                    info=image.VS_FIXEDFILEINFO[0]
                    version=(info.FileVersionMS,info.FileVersionLS)
                candidates.append((version, str(directory), instance))
    if not candidates:
        roots=[str(Path(instance['installationPath'])/'VC/Redist/MSVC') for instance in instances]
        raise RuntimeError(f'Windows package builds require licensed Visual Studio 2022 C++ REDIST files; searched {roots}')
    _, directory, instance=max(candidates, key=lambda item:(item[0],item[1]))
    source_dir=Path(directory)
    signature_script="""
$ErrorActionPreference='Stop'
@('vcruntime140.dll','vcruntime140_1.dll') | ForEach-Object {
    $signature=Get-AuthenticodeSignature -LiteralPath (Join-Path $env:SHOGI_BUILD_VC_RUNTIME_SOURCE $_)
    if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw "Invalid Microsoft runtime signature: $_"
    }
    @{file=$_;status=$signature.Status.ToString();publisher=$signature.SignerCertificate.Subject}
} | ConvertTo-Json
"""
    # A parent pwsh session may export a module path containing PS7-only modules;
    # let Windows PowerShell initialize its own module search path.
    signature_env={key:value for key,value in os.environ.items() if key.lower() != 'psmodulepath'}
    signature_env['SHOGI_BUILD_VC_RUNTIME_SOURCE']=str(source_dir)
    signatures=json.loads(subprocess.check_output([
        'powershell.exe', '-NoProfile', '-NonInteractive', '-Command', signature_script],
        env=signature_env,encoding='utf-8'))
    signatures={row['file']:row for row in signatures}
    internal=(folder/'_internal').resolve()
    notices=internal/'third_party_notices'
    required_notices = ('CPython-LICENSE.txt', 'CPython-Windows-conditions.txt',
                        'Microsoft-runtime-terms.docx', 'Microsoft-runtime-terms.txt',
                        'Microsoft-VS2022-terms.docx', 'Microsoft-VS2022-terms.txt',
                        'Microsoft-REDIST.html')
    for name in required_notices:
        if not (notices/name).is_file():
            raise RuntimeError(f'Missing Microsoft redistribution document: {name}')
    runtime_files=[]
    for name in WINDOWS_RUNTIME_DLLS:
        source=source_dir/name
        with pefile.PE(str(source), fast_load=False) as image:
            if image.FILE_HEADER.Machine != 0x8664:
                raise RuntimeError(f'Expected x64 runtime: {source}')
            values={key.decode(): value.decode() for group in image.FileInfo
                    for entry in group if entry.Key == b'StringFileInfo'
                    for table in entry.StringTable for key,value in table.entries.items()}
            if values.get('CompanyName') != 'Microsoft Corporation':
                raise RuntimeError(f'Unexpected runtime publisher: {source}')
        target=internal/name
        shutil.copyfile(source,target)
        runtime_files.append({'file':name, 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                              'bytes':target.stat().st_size, 'source':str(source),
                              'version':values['FileVersion'], 'copyright':values['LegalCopyright'],
                              'publisher':values['CompanyName'], 'signature':signatures[name]})
    removed=[]
    for path in internal.rglob('*.dll'):
        name=path.name.lower()
        # UCRT is an OS component on supported Windows 10+. Do not ship copies of
        # Windows system DLLs or silently add unreviewed VC runtime components.
        if name.startswith(('api-ms-win-',)) or name=='ucrtbase.dll':
            if not path.resolve().is_relative_to(internal):
                raise RuntimeError('Unexpected library path outside application bundle')
            removed.append(path.relative_to(internal).as_posix())
            path.unlink()
        elif name.startswith(('vcruntime','msvcp','concrt','msvcr')) and name not in WINDOWS_RUNTIME_DLLS:
            raise RuntimeError(f'Unreviewed Microsoft runtime DLL: {path}')
    (notices/'WINDOWS_RUNTIME.json').write_text(json.dumps({
        'files':runtime_files, 'source_distribution':'Visual Studio 2022 C++ REDIST',
        'visual_studio':{'product':instance['productId'], 'version':instance['installationVersion']},
        'cpython_conditions':'CPython-Windows-conditions.txt',
        'runtime_terms':'Microsoft-runtime-terms.txt',
        'redistribution_reference':'Microsoft-VS2022-terms.txt',
        'removed_os_dlls':removed}, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
    # Retire the previous, incorrect OS-installed VC runtime prerequisite notice.
    old=notices/'WINDOWS_SYSTEM_RUNTIME.txt'
    if old.is_file(): old.unlink()
    (folder/'Start.bat').write_text('@echo off\nsetlocal\n"%~dp0ShogiAnalyzer.exe" %*\nset "SA_RESULT=%ERRORLEVEL%"\nif not "%SA_RESULT%"=="0" pause\nexit /b %SA_RESULT%\n',encoding='utf-8',newline='\r\n')
