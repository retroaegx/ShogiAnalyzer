import json
from pathlib import Path
import subprocess
import unittest

from server.app.core.gametree import GameTree
from server.app.core.import_kif import import_kif_game
from server.app.core.reconnect import check_step,ReconnectConflict

class StepReplayTests(unittest.TestCase):
    def setUp(self):
        self.game=GameTree.new()
        self.base=self.game.current_node_id
        self.payload={'operation_id':'op','expected_game_id':self.game.game_id,
            'expected_node_id':self.base,'expected_sfen':self.game.initial_sfen,
            'from_node_id':self.base,'move_usi':'7g7f'}
    def test_first_move_and_duplicate_after_lost_reply(self):
        check_step(self.game,'node:play_move',self.payload)
        first=self.game.play_move(self.base,'7g7f')
        check_step(self.game,'node:play_move',self.payload)
        second=self.game.play_move(self.base,'7g7f')
        self.assertEqual(first.node_id,second.node_id)
        self.assertEqual(len(self.game.nodes),2)
    def test_rejects_changed_game_or_position(self):
        with self.assertRaises(ReconnectConflict): check_step(GameTree.new(),'node:play_move',self.payload)
        self.game.play_move(self.base,'2g2f')
        with self.assertRaises(ReconnectConflict): check_step(self.game,'node:play_move',self.payload)
    def test_rejects_wrong_base_position(self):
        with self.assertRaises(ReconnectConflict): check_step(self.game,'node:play_move',{**self.payload,'expected_sfen':'bad'})
    def test_jump_replay_and_one_ply_limit(self):
        first=self.game.play_move(self.base,'7g7f')
        second=self.game.play_move(first.node_id,'3c3d')
        self.game.jump(self.base)
        p={**self.payload,'node_id':first.node_id,'step_limited':True}
        check_step(self.game,'node:jump',p)
        self.game.jump(first.node_id)
        check_step(self.game,'node:jump',p)
        with self.assertRaises(ReconnectConflict): check_step(self.game,'node:jump',{**p,'node_id':second.node_id})
    def test_browser_preview_matches_all_103_server_positions(self):
        root=Path(__file__).resolve().parents[1]
        game=import_kif_game((root/'tests/fixtures/promoted_silver.kif').read_text(encoding='utf-8'))
        path=game.path_to_node()
        inputs=[[a.position_sfen,b.move_usi] for a,b in zip(path,path[1:])]
        result=subprocess.run(['node',str(root/'tests/preview_vectors.mjs')],input=json.dumps(inputs),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),[n.position_sfen for n in path[1:]])

if __name__=='__main__': unittest.main()
