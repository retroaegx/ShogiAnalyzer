"""Smoke a native executable without a Python command on PATH or engine downloads."""
import argparse
import json
import os
from pathlib import Path
from websockets.sync.client import connect
import socket
import shlex
import signal
import subprocess
import tempfile
import time
import urllib.request
import psutil


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('executable', type=Path)
    args = parser.parse_args()
    exe = args.executable.resolve()
    with tempfile.TemporaryDirectory(prefix='shogi_smoke_') as temp:
        env = {k:v for k,v in os.environ.items() if not k.startswith(('SHOGI_ANALYZER_', 'PYTHON'))}
        empty_bin = Path(temp) / 'empty-bin'
        empty_bin.mkdir()
        env['PATH'] = os.path.join(env.get('SystemRoot', 'C:/Windows'), 'System32') if os.name == 'nt' else str(empty_bin)
        env.update(SHOGI_ANALYZER_HOME=temp, SHOGI_ANALYZER_PASSWORD='FALSE', SHOGI_ANALYZER_TUNNEL='FALSE', SHOGI_ANALYZER_UPDATE_CHECK='FALSE')
        # A frozen Windows child ignores PYTHONIOENCODING and used to emit cp932
        # into the launcher's UTF-8 reader. Check real executable pipe bytes.
        sample='パスワード保護: ON / 最初の画面で設定してください。\n'
        pipe_probe=Path(temp)/'pipe_encoding.py'
        pipe_probe.write_text('import sys\nsys.stdout.write('+repr(sample)+')\nsys.stderr.write('+repr(sample)+')\n',encoding='utf-8')
        encoded=subprocess.run([str(exe),'--engine-python',str(pipe_probe)],
            env={**env,'PYTHONIOENCODING':'utf-8'},capture_output=True,check=True,timeout=20)
        assert encoded.stdout.replace(b'\r\n',b'\n')==sample.encode('utf-8'), 'Non-UTF-8 stdout from native executable'
        assert encoded.stderr.replace(b'\r\n',b'\n')==sample.encode('utf-8'), 'Non-UTF-8 stderr from native executable'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            env['SHOGI_ANALYZER_PORT'] = str(sock.getsockname()[1])
        subprocess.run([str(exe), '--self-check'], env=env, cwd=temp, check=True, timeout=60)
        # Exercise the normal installer path as well as --serve: this catches
        # frozen venv recursion, pip calls and wrong child entry arguments.
        peer = Path(__file__).resolve().parents[1] / 'tests' / 'fake_usi.py'
        argv = [str(exe), '--engine-python', str(peer)]
        env['SHOGI_ANALYZER_ENGINE_CMD'] = subprocess.list2cmdline(argv) if os.name == 'nt' else shlex.join(argv)
        with open(Path(temp) / 'server.log', 'w+', encoding='utf-8') as log:
            proc = subprocess.Popen([str(exe)], env=env, cwd=temp, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            try:
                url = 'http://127.0.0.1:' + env['SHOGI_ANALYZER_PORT']
                for attempt in range(150):
                    if proc.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read())
                    try:
                        with urllib.request.urlopen(url + '/healthz', timeout=1) as response:
                            assert response.status == 200
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    log.seek(0)
                    raise RuntimeError('Server startup timed out\n' + log.read())
                for path in ['/', '/js/reconnect.js', '/app.css', '/manifest.webmanifest']:
                    with urllib.request.urlopen(url + path, timeout=3) as response:
                        assert response.status == 200 and response.read()
                with connect(url.replace('http:','ws:') + '/ws?tab=portable-smoke') as ws:
                    session = json.loads(ws.recv(timeout=5))
                    assert session['type'] == 'session:granted'
                    payload = session['payload']
                    ws.send(json.dumps({'type':'analysis:set_enabled', 'payload':{'enabled':True},
                        'session_id':payload['session_id'], 'owner_token':payload['owner_token']}))
                    for attempt in range(30):
                        message = json.loads(ws.recv(timeout=5))
                        if message['type'] == 'analysis:update':
                            assert message['payload']['bestline']['score_value'] == 150
                            break
                    else:
                        raise AssertionError('Bundled server did not communicate with the external USI peer')
                assert (Path(temp) / 'server/data/app.db').is_file()
                assert not (Path(temp) / '.venv').exists()
                assert not (Path(temp) / 'engines').exists()
                print(json.dumps({'ok':True, 'normal_launcher':True, 'http_assets':True, 'no_python_on_path':True, 'no_engine_download':True, 'external_usi':True}))
            finally:
                children = psutil.Process(proc.pid).children(recursive=True)
                proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
                proc.wait(timeout=15)
                _, alive = psutil.wait_procs(children, timeout=10)
                if alive:
                    log.seek(0)
                    print(log.read(), flush=True)
                    details = [(child.pid, child.ppid(), child.name(), child.status(), child.cmdline() if child.status()!=psutil.STATUS_ZOMBIE else []) for child in alive]
                    for child in alive: child.kill()
                    psutil.wait_procs(alive, timeout=5)
                    raise RuntimeError(f'Launcher left child processes: {details}')


if __name__ == '__main__':
    main()
