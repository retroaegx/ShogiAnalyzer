"""Verify source digests, no embedded GPL module, and actual LGPL source replacement."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from portable_licenses import LGPL_MODULES, WINDOWS_RUNTIME_DLLS, audit_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    args = parser.parse_args()
    exe = args.executable.resolve()
    folder = exe.parent
    audit_bundle(folder)
    inventory=json.loads((folder/'_internal/third_party_notices/INVENTORY.json').read_text(encoding='utf-8'))
    if os.name == 'nt':
        notices=folder/'_internal/third_party_notices'
        runtime=json.loads((notices/'WINDOWS_RUNTIME.json').read_text(encoding='utf-8'))
        assert {row['file'] for row in runtime['files']} == set(WINDOWS_RUNTIME_DLLS)
        for row in runtime['files']:
            assert hashlib.sha256((folder/'_internal'/row['file']).read_bytes()).hexdigest()==row['sha256']
        for row in inventory['native_references']:
            assert hashlib.sha256((notices/row['file']).read_bytes()).hexdigest()==row['sha256']
        assert 'MICROSOFT SOFTWARE LICENSE TERMS' in (notices/runtime['runtime_terms']).read_text(encoding='utf-8')
        assert 'DISTRIBUTABLE CODE' in (notices/runtime['redistribution_reference']).read_text(encoding='utf-8')
        assert 'System32' not in (folder/'Start.bat').read_text(encoding='utf-8')
    assert all(item['name']!='python-shogi' for item in inventory['packages'])
    source_rows=json.loads((folder/'third_party_sources/SOURCES.json').read_text(encoding='utf-8'))
    assert {row['name'] for row in source_rows} == set(LGPL_MODULES)
    for row in source_rows:
        path=folder/'third_party_sources'/row['source']['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['source']['sha256']
    originals={}
    try:
        for name in LGPL_MODULES.values():
            file=folder/'_internal'/name/'__init__.py'
            originals[file]=file.read_bytes()
            file.write_bytes(originals[file]+b'\nSHOGI_REPLACEMENT_PROBE = "modified-library-loaded"\n')
        with tempfile.TemporaryDirectory() as home:
            env={k:v for k,v in os.environ.items() if not k.startswith('SHOGI_ANALYZER_')}
            env['SHOGI_ANALYZER_HOME']=home
            result=subprocess.run([str(exe),'--self-check'],env=env,check=True,capture_output=True,text=True,encoding='utf-8',timeout=60)
            reply=json.loads(result.stdout)
        assert reply['replacement_probes']=={name:'modified-library-loaded' for name in LGPL_MODULES.values()}
        print(json.dumps({'ok':True,'sources_verified':len(source_rows),'external_modified_modules_loaded':len(originals),'no_shogi_in_pyz':True}))
    finally:
        for file,original in originals.items():
            file.write_bytes(original)


if __name__=='__main__':
    main()
