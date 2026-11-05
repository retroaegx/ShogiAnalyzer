"""Check password lifecycle and cross-site protections on an isolated HTTP server."""
import http.cookiejar
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from server.app.api import _client_ip
from server.app import auth
from unittest.mock import patch


class AuthenticationHTTPTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'POSIX file permissions')
    def test_existing_auth_file_becomes_private_at_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'auth.json'
            with patch.object(auth, 'auth_file', return_value=path), patch.object(auth, 'required', return_value=True):
                auth.save_password('test-only-password')
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                path.chmod(0o644)
                auth.apply_setting()
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_direct_clients_cannot_spoof_rate_limit_address(self):
        remote=SimpleNamespace(client=SimpleNamespace(host='198.51.100.12'),headers={'cf-connecting-ip':'different-address'})
        self.assertEqual(_client_ip(remote),'198.51.100.12')

    def test_password_lifecycle_and_cross_site_setup_rejected(self):
        with tempfile.TemporaryDirectory(prefix='shogi_auth_audit_') as directory:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            env={key:value for key,value in os.environ.items() if not key.startswith('SHOGI_ANALYZER_')}
            env.update(SHOGI_ANALYZER_HOME=directory,SHOGI_ANALYZER_PASSWORD='TRUE',
                       SHOGI_ANALYZER_UPDATE_CHECK='FALSE',SHOGI_ANALYZER_PORT=str(port))
            root=Path(__file__).resolve().parents[1]
            base=f'http://127.0.0.1:{port}'
            cookies=http.cookiejar.CookieJar()
            client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
            def request(path,data=None,origin=None):
                headers={'Content-Type':'application/json'}
                if origin is not None: headers['Origin']=origin
                req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
                try:
                    with client.open(req,timeout=5) as response:
                        return response.status,response.read()
                except urllib.error.HTTPError as error:
                    return error.code,error.read()
            with open(Path(directory)/'server.log','w',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,str(root/'installer/portable_entry.py'),'--serve'],
                    env=env,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
                try:
                    for _ in range(150):
                        try:
                            urllib.request.urlopen(base+'/healthz',timeout=.2).close(); break
                        except OSError: time.sleep(.03)
                    self.assertEqual(request('/api/settings')[0],401)
                    self.assertEqual(request('/api/auth/setup',{'password':'test-password'},'https://unrelated.invalid')[0],403)
                    self.assertFalse(json.loads(request('/api/auth/status')[1])['configured'])
                    self.assertEqual(request('/api/auth/setup',{'password':'x'},base)[0],400)
                    self.assertEqual(request('/api/auth/setup',{'password':'test-password'},base)[0],200)
                    if os.name != 'nt':
                        self.assertEqual((Path(directory)/'server/data/auth.json').stat().st_mode & 0o777,0o600)
                    self.assertEqual(request('/api/settings')[0],200)
                    self.assertEqual(request('/api/app/licenses')[0],200)
                    self.assertEqual(request('/api/app/license-document/app')[0],200)
                    self.assertEqual(request('/api/app/license-document/notices/../.env')[0],404)
                    self.assertEqual(request('/api/logout',{},base)[0],200)
                    self.assertEqual(request('/api/settings')[0],401)
                    self.assertEqual(request('/api/login',{'password':'wrong-password'},base)[0],401)
                    self.assertEqual(request('/api/login',{'password':'test-password'},base)[0],200)
                    self.assertEqual(request('/api/settings')[0],200)
                finally:
                    process.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
                    process.wait(timeout=10)
