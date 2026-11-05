"""Exercise real native WebSocket transport, ownership and replay against an isolated server."""
import asyncio
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

import websockets


class WebSocketReconnectTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='shogi_ws_test_')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            cls.port=sock.getsockname()[1]
        env={k:v for k,v in os.environ.items() if not k.startswith('SHOGI_ANALYZER_')}
        env.update(SHOGI_ANALYZER_HOME=cls.temp.name,SHOGI_ANALYZER_PASSWORD='FALSE',SHOGI_ANALYZER_UPDATE_CHECK='FALSE',SHOGI_ANALYZER_PORT=str(cls.port))
        root=Path(__file__).resolve().parents[1]
        cls.log=open(Path(cls.temp.name)/'server.log','w+',encoding='utf-8')
        cls.proc=subprocess.Popen([sys.executable,str(root/'installer/portable_entry.py'),'--serve'],env=env,stdout=cls.log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        for attempt in range(150):
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{cls.port}/healthz',timeout=.3).close()
                return
            except OSError:
                if cls.proc.poll() is not None: break
                time.sleep(.03)
        cls.log.seek(0)
        raise RuntimeError(cls.log.read())

    @classmethod
    def tearDownClass(cls):
        cls.proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
        cls.proc.wait(timeout=10)
        cls.log.close()
        cls.temp.cleanup()

    async def receive(self,ws,kind):
        async with asyncio.timeout(5) if sys.version_info>=(3,11) else _Timeout():
            for attempt in range(30):
                message=json.loads(await asyncio.wait_for(ws.recv(),5))
                if message['type']==kind: return message['payload']
        raise AssertionError(f'No {kind} response')

    def connect(self,tab):
        return websockets.connect(f'ws://127.0.0.1:{self.port}/ws?tab={tab}')

    async def send(self,ws,session,kind,payload):
        await ws.send(json.dumps({'type':kind,'payload':payload,'session_id':session['session_id'],'owner_token':session['owner_token']}))

    async def test_already_applied_move_retries_once_without_duplicate(self):
        async with self.connect('retry') as first:
            session=await self.receive(first,'session:granted')
            await self.send(first,session,'game:new',{})
            game=(await self.receive(first,'game:state'))['game']
            op={'operation_id':'retry-op','expected_game_id':game['game_id'],'expected_node_id':game['current_node_id'],
                'expected_sfen':game['current_position_sfen'],'from_node_id':game['current_node_id'],'move_usi':'7g7f','step_limited':True}
            await self.send(first,session,'node:play_move',op)
            accepted=await self.receive(first,'game:state')
            self.assertEqual(accepted['operation_id'],'retry-op')
            # Reconnect the same tab while the old socket is still present.
            async with self.connect('retry') as second:
                new_session=await self.receive(second,'session:granted')
                self.assertEqual(new_session['game']['current_path_moves'],['7g7f'])
                await self.send(second,new_session,'node:play_move',op)
                reply=await self.receive(second,'game:state')
                self.assertEqual(reply['game']['current_path_moves'],['7g7f'])
                self.assertEqual(len(reply['game']['nodes']),2)
                await self.send(second,new_session,'game:new',{})
                await self.receive(second,'game:state')
                await self.send(second,new_session,'node:play_move',op)
                rejected=await self.receive(second,'game:state')
                self.assertEqual(rejected['operation_id'],'retry-op')
                self.assertTrue(rejected['operation_error'])
                self.assertEqual(len(rejected['game']['nodes']),1)

    async def test_explicit_takeover_retains_tab_on_reconnect(self):
        async with self.connect('owner') as first:
            await self.receive(first,'session:granted')
            async with self.connect('takeover') as second:
                await self.receive(second,'session:busy')
                await second.send(json.dumps({'type':'session:takeover'}))
                session=await self.receive(second,'session:granted')
                self.assertTrue(session['owner_token'])
                async with self.connect('takeover') as third:
                    recovered=await self.receive(third,'session:granted')
                    self.assertTrue(recovered['owner_token'])


class _Timeout:
    async def __aenter__(self): pass
    async def __aexit__(self,*args): pass


if __name__=='__main__':
    unittest.main()
