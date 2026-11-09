"""Exercise real native replacement and helper cleanup with no Python on PATH.

The worker runs inside the frozen app. Only the network transport is replaced
with a local release fixture; extraction, locks, swaps and both native self-checks
are the production updater. Never points at a user's actual installation.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from external_process import external_env, external_libraries


def spawn_args(env):
    value = external_env(env); value['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return value


def worker(job: Path, archive: Path):
    from installer.update import run_job
    # The helper's VERSION is deliberately 0.0.0. Read the real version from
    # the original release metadata, supplied by the controlling fixture.
    info = json.loads((archive.parent/'fixture-release.json').read_text())
    def download(url, dest, **options):
        shutil.copyfile(archive, dest)
        return hashlib.sha256(dest.read_bytes()).hexdigest()
    assert run_job(job, confirm=lambda: True, fetch_release=lambda repo: info, downloader=download)


def run(exe: Path, archive: Path, *, online_launcher=False):
    from installer.update import extract_archive, JOB_PREFIX
    script = Path(__file__).resolve()
    with tempfile.TemporaryDirectory(prefix='Shogi updater test ') as temp:
        root = Path(temp).resolve(); home=root/'user data'; home.mkdir()
        installed=extract_archive(archive,root/'unpacked')
        target=root/'App with spaces 日本語'; installed.rename(target)
        binary=target/exe.name
        version=(target/'_internal/VERSION').read_text().strip()
        (target/'_internal/VERSION').write_text('0.0.0')
        (target/'_internal/obsolete-runtime-marker').write_text('must disappear')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        keep={'.env':f'SHOGI_ANALYZER_PORT={port}\nSHOGI_ANALYZER_PASSWORD=FALSE\n'.encode(),
              'server/data/app.db':b'kifu bytes','server/data/auth.json':b'password storage',
              'engines/my-engine':b'engine','tools/cloudflared/cloudflared':b'tunnel',
              'server/data/share/keep.webp':b'private generated share'}
        for folder in (home,target):
            for name,data in keep.items():
                path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        fixture=root/archive.name;shutil.copyfile(archive,fixture)
        release={'tag_name':'v'+version,'assets':[{'name':archive.name,'size':fixture.stat().st_size,
            'browser_download_url':'https://example.invalid/'+archive.name,
            'digest':'sha256:'+hashlib.sha256(fixture.read_bytes()).hexdigest()}]}
        (root/'fixture-release.json').write_text(json.dumps(release))
        env={k:v for k,v in os.environ.items() if not k.startswith(('SHOGI_ANALYZER_','PYTHON'))}
        empty=root/'empty-bin';empty.mkdir()
        env['PATH']=os.path.join(env.get('SystemRoot','C:/Windows'),'System32') if os.name=='nt' else str(empty)
        env.update(SHOGI_ANALYZER_HOME=str(home),SHOGI_ANALYZER_ENGINE_PATH='',SHOGI_ANALYZER_ENGINE_EVAL_DIR='')
        job=root/(JOB_PREFIX+'native')
        with external_libraries():
            subprocess.run([str(binary),'--prepare-update',str(job)],env=spawn_args(env),check=True,timeout=90)
        helper=job/exe.name
        with external_libraries():
            subprocess.run([str(helper),'--engine-python',str(script),'--worker',str(job/'job.json'),str(fixture)],
                env=spawn_args(env),check=True,timeout=240)
        assert (target/'_internal/VERSION').read_text().strip()==version
        assert not (target/'_internal/obsolete-runtime-marker').exists()
        for folder in (home,target):
            for name,data in keep.items():assert (folder/name).read_bytes()==data,(folder,name)
        with external_libraries():
            subprocess.run([str(binary),'--cleanup-update',str(job)],env=spawn_args(env),check=True,timeout=60)
        assert not job.exists()
        assert not any(target.glob('.UpdateRecovery.*'))
        assert not any(target.glob('.shogianalyzer-update-*'))
        if online_launcher:
            # Exercise the actual distributed launcher and the real HTTPS version
            # query. Decline any future release; this probe must never install it.
            launcher_env=spawn_args(env)
            if os.name=='nt':
                launcher_env['SA_PROBE_LAUNCHER']=str(target/'Update.bat')
                command='"'+os.environ.get('COMSPEC','cmd.exe')+'" /d /s /c ""%SA_PROBE_LAUNCHER%""'
            else:
                for command_name in ('dirname','mktemp','rmdir','sh'):
                    (empty/command_name).symlink_to(shutil.which(command_name))
                command=['/bin/sh',str(target/('Update.command' if sys.platform=='darwin' else 'Update.sh'))]
            with external_libraries():
                result=subprocess.run(command,env=launcher_env,input=b'n\n\n',capture_output=True,timeout=180)
            print(result.stdout.decode('utf-8',errors='replace'),flush=True)
            assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
            assert b'[update]' in result.stdout and not any(target.glob('.UpdateRecovery.*'))
        print(json.dumps({'ok':True,'native_replacement':True,'no_python_on_path':True,
            'user_data_unchanged':True,'obsolete_runtime_removed':True,'helper_cleaned':True,
            'online_launcher':online_launcher,'platform':sys.platform}),flush=True)


if __name__=='__main__':
    if sys.argv[1:2]==['--worker']:
        worker(Path(sys.argv[2]),Path(sys.argv[3]))
    else:
        online_launcher='--online-launcher' in sys.argv
        if online_launcher:sys.argv.remove('--online-launcher')
        exe=Path(sys.argv[1]).resolve()
        if len(sys.argv)>2:archive=Path(sys.argv[2]).resolve()
        else:
            archives=list(exe.parents[2].glob('ShogiAnalyzer-v*.zip'))+list(exe.parents[2].glob('ShogiAnalyzer-v*.tar.gz'))
            assert len(archives)==1,archives
            archive=archives[0]
        run(exe,archive,online_launcher=online_launcher)
