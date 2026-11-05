"""Run using ONLY the application's embedded interpreter inside a fresh OS image."""
from __future__ import annotations
import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import platform
import signal
import socket
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.error


class WebSocket:
    def __init__(self, port, tab='cleanroom'):
        self.sock=socket.create_connection(('127.0.0.1',port),timeout=12)
        key=base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET /ws?tab={tab} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        header=b''
        while not header.endswith(b'\r\n\r\n'):
            header+=self.read(1)
        assert header.startswith(b'HTTP/1.1 101'),header
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        assert expected.lower() in header.lower()
        self.session=self.until('session:granted')
    def read(self,count):
        value=b''
        while len(value)<count:
            part=self.sock.recv(count-len(value))
            if not part: raise EOFError('WebSocket closed')
            value+=part
        return value
    def frame(self,opcode,payload):
        mask=os.urandom(4)
        length=len(payload)
        header=bytes([0x80|opcode,0x80|min(length,126)]) if length<=65535 else bytes([0x80|opcode,0x80|127])
        if length>=126: header+=struct.pack('!H' if length<=65535 else '!Q',length)
        self.sock.sendall(header+mask+bytes(b^mask[i%4] for i,b in enumerate(payload)))
    def send(self,kind,payload=None):
        message={'type':kind,'payload':payload or {},'session_id':self.session['session_id'],'owner_token':self.session['owner_token']}
        self.frame(1,json.dumps(message).encode())
    def receive(self):
        fragments=[]
        while True:
            a,b=self.read(2)
            length=b&127
            if length==126: length=struct.unpack('!H',self.read(2))[0]
            elif length==127: length=struct.unpack('!Q',self.read(8))[0]
            mask=self.read(4) if b&128 else None
            payload=self.read(length)
            if mask: payload=bytes(x^mask[i%4] for i,x in enumerate(payload))
            opcode=a&15
            if opcode==9: self.frame(10,payload); continue
            if opcode==8: raise EOFError('Server closed WebSocket')
            if opcode in (0,1):
                fragments.append(payload)
                if a&128: return json.loads(b''.join(fragments))
    def until(self,kind):
        for _ in range(80):
            message=self.receive()
            if message['type']==kind: return message['payload']
        raise AssertionError('Missing '+kind)
    def close(self):
        try: self.frame(8,struct.pack('!H',1000))
        finally: self.sock.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--peer',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    exe=args.exe.resolve()
    output=args.output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    home=output.parent/'application-data'
    home.mkdir(exist_ok=True)
    env={key:value for key,value in os.environ.items() if not key.startswith(('SHOGI_ANALYZER_','PYTHON'))}
    env.update(SHOGI_ANALYZER_HOME=str(home),SHOGI_ANALYZER_PASSWORD='FALSE',SHOGI_ANALYZER_TUNNEL='FALSE',SHOGI_ANALYZER_UPDATE_CHECK='FALSE')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port=sock.getsockname()[1]
    env['SHOGI_ANALYZER_PORT']=str(port)
    peer=[str(exe),'--engine-python',str(args.peer.resolve())]
    if os.name=='nt': env['SHOGI_ANALYZER_ENGINE_CMD']=subprocess.list2cmdline(peer)
    else:
        import shlex
        env['SHOGI_ANALYZER_ENGINE_CMD']=shlex.join(peer)
    report={'os':platform.platform(),'embedded_python':sys.version,'exe':str(exe),'checks':{},'engine':'controlled USI test peer, not a playing-strength engine'}
    checks=report['checks']
    proc=None
    log=(output.parent/'application.log').open('w+',encoding='utf-8')
    def start():
        nonlocal proc
        proc=subprocess.Popen([str(exe)],cwd=home,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0,
            start_new_session=os.name!='nt')
        for attempt in range(200):
            if proc.poll() is not None:
                log.flush(); log.seek(0); raise RuntimeError(log.read())
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',timeout=.3).close()
                return
            except OSError: time.sleep(.05)
        raise TimeoutError('Application startup')
    def stop():
        nonlocal proc
        if not proc: return
        import psutil
        children=psutil.Process(proc.pid).children(recursive=True) if proc.poll() is None else []
        if proc.poll() is None:
            proc.send_signal(signal.CTRL_BREAK_EVENT if os.name=='nt' else signal.SIGINT)
            proc.wait(timeout=15)
        _,alive=psutil.wait_procs(children,timeout=8)
        if alive:
            for child in alive: child.kill()
            raise RuntimeError('Leftover application subprocess')
        proc=None
        try:
            connection=socket.create_connection(('127.0.0.1',port),timeout=.2)
        except OSError: return
        connection.close(); raise AssertionError('Server port stayed open')
    try:
        result=subprocess.run([str(exe),'--self-check'],env=env,capture_output=True,text=True,encoding='utf-8',timeout=60,check=True)
        checks['self_check']=json.loads(result.stdout)['ok']
        start(); checks['normal_launcher']=True
        assets={}
        for path in ('/','/js/app.js','/js/reconnect.js','/app.css','/manifest.webmanifest','/board-theme/images/pieces/mokume/pawn.webp'):
            with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=5) as response:
                content=response.read()
                assert response.status==200 and content,path
                assets[path]={'bytes':len(content),'type':response.headers.get('Content-Type')}
        checks['http_assets']=assets
        ws=WebSocket(port)
        try:
            ws.send('game:new')
            game=ws.until('game:state')['game']
            operation={'operation_id':'clean-first','expected_game_id':game['game_id'],'expected_node_id':game['current_node_id'],
                'expected_sfen':game['current_position_sfen'],'from_node_id':game['current_node_id'],'move_usi':'7g7f'}
            ws.send('node:play_move',operation)
            game=ws.until('game:state')['game']
            assert game['current_path_moves']==['7g7f']
            ws.send('node:play_move',operation)
            game=ws.until('game:state')['game']
            assert len(game['nodes'])==2
            checks['move_and_duplicate_replay']=True
            ws.send('game:new'); ws.until('game:state')
            ws.send('analysis:set_enabled',{'enabled':True})
            info=ws.until('analysis:update')
            assert info['bestline']['score_value']==150
            checks['external_usi_analysis']=True
            ws.send('analysis:set_enabled',{'enabled':False}); ws.until('game:state')
            ws.send('game:import_text',{'text':args.fixture.read_text(encoding='utf-8'),'title':'Clean-room fixture'})
            game=ws.until('game:state')['game']
            path=game['current_path_node_ids']
            assert len(path)==104
            ws.send('node:jump',{'node_id':path[87]})
            game=ws.until('game:state')['game']
            pending={'operation_id':'clean-reconnect','expected_game_id':game['game_id'],
                'expected_node_id':game['current_node_id'],'expected_sfen':game['current_position_sfen'],
                'node_id':path[88],'step_limited':True}
            ws.close(); ws=WebSocket(port)
            ws.send('node:jump',pending)
            game=ws.until('game:state')['game']
            assert len(game['current_path_moves'])==88 and game['current_path_moves'][-1]=='7f6g'
            checks['fixture_103_moves_and_reconnect_at_88']=True
            ws.send('game:save',{'title':'Clean-room fixture'})
            saved=ws.until('game:state')['game']
            ws.send('game:new'); ws.until('game:state')
            ws.send('node:jump',pending)
            rejected=ws.until('game:state')
            assert rejected['operation_error'] and len(rejected['game']['nodes'])==1
            checks['stale_operation_rejected']=True
            ws.send('game:load',{'game_id':saved['game_id']})
            loaded=ws.until('game:state')['game']
            assert loaded['game_id']==saved['game_id']
        finally: ws.close()
        stop(); checks['shutdown_without_leftovers']=True
        start()
        ws=WebSocket(port)
        try:
            restored=ws.session['game']
            assert restored['game_id']==saved['game_id'] and len(restored['current_path_moves'])==88
            assert len(restored['nodes'])==104
        finally: ws.close()
        checks['restart_and_database_persistence']=True
        assert (home/'server/data/app.db').is_file()
        assert not (home/'.venv').exists() and not (home/'engines').exists()
        checks['no_venv_or_engine_download']=True
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/app/licenses') as response:
            assert '同梱ソフトウェア' in response.read().decode('utf-8')
        checks['bundled_license_page']=True
        stop()
        env['SHOGI_ANALYZER_PASSWORD']='TRUE'
        start()
        client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        base=f'http://127.0.0.1:{port}'
        def auth_request(path, data=None, origin=base):
            req=urllib.request.Request(base+path, data=None if data is None else json.dumps(data).encode(),
                headers={'Content-Type':'application/json','Origin':origin})
            try:
                with client.open(req,timeout=5) as response: return response.status,response.read()
            except urllib.error.HTTPError as error: return error.code,error.read()
        assert auth_request('/api/settings')[0]==401
        assert auth_request('/api/auth/setup',{'password':'cleanroom-test-only'},'https://unrelated.invalid')[0]==403
        assert not json.loads(auth_request('/api/auth/status')[1])['configured']
        assert auth_request('/api/auth/setup',{'password':'cleanroom-test-only'})[0]==200
        assert auth_request('/api/settings')[0]==200
        assert auth_request('/api/logout',{})[0]==200
        assert auth_request('/api/settings')[0]==401
        assert auth_request('/api/login',{'password':'wrong-test-only'})[0]==401
        assert auth_request('/api/login',{'password':'cleanroom-test-only'})[0]==200
        stop(); start()
        assert auth_request('/api/settings')[0]==200
        assert json.loads(auth_request('/api/auth/status')[1])['configured']
        checks['native_password_setup_login_logout_restart']=True
        checks['cross_site_setup_rejected']=True
        report['ok']=True
    except Exception as error:
        report['ok']=False
        report['error']=repr(error)
        raise
    finally:
        try: stop()
        finally:
            log.close()
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__': main()
