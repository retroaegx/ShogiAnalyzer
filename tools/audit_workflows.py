"""Exercise a disposable localhost server with a real USI engine.

Run with the bundle's --engine-python; no development libraries are required.
Never point this at a user's running instance: it creates and deletes test games.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

from PIL import Image
from server.app.core.gametree import GameTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cleanroom_probe import WebSocket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--disposable-server', action='store_true', required=True)
    args = parser.parse_args()
    if args.port == 31145:
        parser.error('Refusing the normal application port')
    base = f'http://127.0.0.1:{args.port}'
    checks = {}
    report = {'checks': checks, 'embedded_python': sys.version, 'ok': False}
    ws = None

    def request(path, data=None, method=None):
        req = urllib.request.Request(base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', 'Origin': base}, method=method)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()

    def api(path, data=None, method=None):
        return json.loads(request(path, data, method))

    def state(kind, payload=None):
        ws.send(kind, payload)
        return ws.until('game:state')['game']

    try:
        options = api('/api/engine/options')
        checks['real_engine_options'] = bool(options)
        api('/api/engine/options', {'values': {'Threads': 1, 'USI_Hash': 64},
            'auto_stop_sec': 10}, 'PUT')
        applied = api('/api/engine/options')
        values = {row['name']: row['value'] for row in applied['options']}
        assert values['Threads'] == 1 and values['USI_Hash'] == 64, values
        checks['engine_options_applied'] = True
        settings = {'batch_seconds': .5, 'view': {'coords': 'overlay'}, 'board_set': 'sansu'}
        api('/api/settings', {'settings': settings}, 'PUT')
        assert api('/api/settings')['settings']['batch_seconds'] == .5
        checks['display_settings_roundtrip'] = True

        game = api('/api/import', {'text': args.fixture.read_text(encoding='utf-8')})['game']
        assert len(game['nodes']) == 104
        for fmt in ('usi', 'kif', 'ki2'):
            exported = request(f"/api/export/{game['game_id']}?format={fmt}").decode('utf-8')
            imported = api('/api/import', {'text': exported})['game']
            assert len(imported['nodes']) == 104, fmt
            assert imported['current_position_sfen'] == game['current_position_sfen'], fmt
            game = imported
        checks['103_ply_kif_ki2_usi_roundtrips'] = True
        for invalid, expected in [('', 400), ('this is not a kifu', 415)]:
            try:
                api('/api/import', {'text': invalid})
            except urllib.error.HTTPError as error:
                assert error.code == expected
            else:
                raise AssertionError('Invalid import was accepted')
        checks['invalid_import_rejected'] = True

        ws = WebSocket(args.port, 'workflow-audit')
        game = state('game:new')
        root = game['current_node_id']
        game = state('node:play_move', {'from_node_id': root, 'move_usi': '7g7f'})
        first = game['current_node_id']
        game = state('node:set_comment', {'node_id': first, 'comment': '総点検コメント'})
        assert next(n for n in game['nodes'] if n['node_id'] == first)['comment'] == '総点検コメント'
        game = state('node:jump', {'node_id': root})
        game = state('node:play_move', {'from_node_id': root, 'move_usi': '2g2f'})
        second = game['current_node_id']
        assert len(game['children_index'][root]) == 2
        game = state('node:delete', {'node_id': second})
        assert game['children_index'][root] == [first]
        game = state('game:save', {'title': 'Disposable workflow audit'})
        saved_id = game['game_id']
        assert not game['dirty']
        state('game:new')
        loaded = state('game:load', {'game_id': saved_id})
        assert len(loaded['nodes']) == 2
        assert any(n['comment'] == '総点検コメント' for n in loaded['nodes'])
        checks['branches_comments_save_load'] = True

        position = state('game:import_text', {'text': 'position startpos moves 7g7f 3c3d 2g2f'})
        state('analysis:set_multipv', {'multipv': 5})
        state('analysis:set_enabled', {'enabled': True})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            info = ws.until('analysis:update')
            lines = info.get('lines') or []
            if len(lines) >= 5 and all(line.get('pv_usi') for line in lines):
                break
        else:
            raise AssertionError('Real engine did not produce five variations')
        checks['real_engine_five_variations'] = {'lines': len(lines), 'best': info['bestline']}
        for line in lines:
            variation = GameTree.new(initial_sfen=position['current_position_sfen'])
            for move in line['pv_usi']:
                variation.play_move(variation.current_node_id, move)
        checks['real_engine_variations_are_legal'] = True
        state('analysis:set_enabled', {'enabled': False})
        state('analysis:set_multipv', {'multipv': 1})
        game = state('analysis:analyze_all', {'seconds': .5})
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            result = api(f"/api/games/{game['game_id']}/evals")['items']
            if len(result) == 4:
                break
            time.sleep(.2)
        else:
            raise AssertionError(f'Batch did not evaluate all four positions: {len(result)}')
        checks['real_engine_batch_four_positions'] = len(result)
        current = api('/api/current')['game']
        share = api('/api/share', {'sfen': current['current_position_sfen'],
            'title': '総点検', 'eval': '+100', 'arrows': []})
        picture = Image.open(io.BytesIO(request(share['image'])))
        picture.load()
        assert picture.format == 'WEBP' and picture.width > 700
        assert b'og:image' in request(share['path'])
        checks['webp_and_share_page'] = {'size': picture.size, 'format': picture.format}
        page = request('/api/app/licenses').decode('utf-8')
        assert '同梱ソフトウェア' in page and '/api/app/license-document/app' in page
        assert b'MIT License' in request('/api/app/license-document/app')
        checks['license_page_and_original'] = True
        ws.close()
        ws = None
        api(f'/api/games/{saved_id}', method='DELETE')
        try:
            api(f'/api/games/{saved_id}')
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError('Deleted test game was still readable')
        checks['delete_saved_game'] = True
        report['ok'] = True
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        if ws:
            ws.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
