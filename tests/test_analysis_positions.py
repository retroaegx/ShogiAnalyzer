import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import shogi

from server.app.core.export_kif import export_game_to_kif
from server.app.core.export_kif2 import export_game_to_kif2
from server.app.core.gametree import GameTree
from server.app.core.import_kif import import_kif_game
from server.app.core.import_kif2 import import_kif2_game
from server.app.core.notation import parse_kif_move_text
from server.app.services.analysis_service import AnalysisService
from server.app.services.state_store import StateStore, content_signature


HERE = Path(__file__).resolve().parent


def example_game():
    return import_kif_game((HERE / "fixtures" / "promoted_silver.kif").read_text(encoding="utf-8"))


def legacy_game():
    game = example_game()
    path = game.path_to_node()
    for ply in (88, 100):
        path[ply].move_usi += "+"
        path[ply].move_label += "成"
    path[88].comment = "keep this comment"
    return game, path


class PromotionTests(unittest.TestCase):
    def test_promoted_piece_names_are_not_promotion_suffixes(self):
        for name in ("成銀", "成桂", "成香"):
            for suffix in ("", "成"):
                with self.subTest(name=name, suffix=suffix):
                    move, _ = parse_kif_move_text(f"６七{name}{suffix}(76)")
                    self.assertEqual(move.to_usi(), "7f6g")
        self.assertEqual(parse_kif_move_text("６七銀成(76)")[0].to_usi(), "7f6g+")
        self.assertEqual(parse_kif_move_text("６七銀不成(76)")[0].to_usi(), "7f6g")
        self.assertEqual(parse_kif_move_text("６七銀打")[0].to_usi(), "S*6g")

    def assert_legal_game(self, game):
        board = shogi.Board(game.initial_sfen)
        moves = game.path_to_node()[1:]
        self.assertEqual(len(moves), 103)
        for ply, node in enumerate(moves, 1):
            move = shogi.Move.from_usi(node.move_usi)
            self.assertIn(move, board.legal_moves, (ply, node.move_usi))
            board.push(move)
            self.assertEqual(board.sfen(), node.position_sfen)

    def test_reported_record_and_roundtrips_are_legal(self):
        game = example_game()
        self.assert_legal_game(game)
        self.assertEqual(game.path_to_node()[88].move_usi, "7f6g")
        self.assertEqual(game.path_to_node()[100].move_usi, "6g7g")
        kif = export_game_to_kif(game)
        self.assertNotIn("成銀成", kif)
        self.assert_legal_game(import_kif_game(kif))
        self.assert_legal_game(import_kif2_game(export_game_to_kif2(game)))


class StoredGameTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="shogi-test-")
        self.store = StateStore(Path(self.folder.name) / "app.db")

    def tearDown(self):
        self.store.close()
        self.folder.cleanup()

    def test_saved_moves_repaired_and_only_affected_scores_invalidated(self):
        game, path = legacy_game()
        # A branch before the broken move must keep its analysis too.
        alternative = game.play_move(path[86].node_id, "9f9e")
        game.jump(path[-1].node_id)
        self.store.save_game(game)
        for node in path + [alternative]:
            self.store.save_analysis_snapshot(node_id=node.node_id, elapsed_ms=500,
                                             multipv=1, lines=[{"score_type": "cp", "score_value": 6000, "depth": 20}])
        loaded = self.store.load_game(game.game_id)
        self.assertEqual(loaded.nodes[path[88].node_id].move_usi, "7f6g")
        self.assertEqual(loaded.nodes[path[100].node_id].move_usi, "6g7g")
        self.assertEqual(loaded.nodes[path[88].node_id].comment, "keep this comment")
        self.assertEqual(loaded.nodes[path[88].node_id].position_sfen, path[88].position_sfen)
        remaining = self.store.latest_evals(game.game_id)
        self.assertIn(path[87].node_id, remaining)
        self.assertIn(alternative.node_id, remaining)
        for node in path[88:]:
            self.assertNotIn(node.node_id, remaining)
        # Correction is persisted, so later valid reanalysis is not discarded again.
        self.store.save_analysis_snapshot(node_id=path[88].node_id, elapsed_ms=500,
                                         multipv=1, lines=[{"score_type": "cp", "score_value": -500, "depth": 10}])
        self.store.load_game(game.game_id)
        self.assertIn(path[88].node_id, self.store.latest_evals(game.game_id))

    def test_working_copy_repair_keeps_saved_status(self):
        for dirty in (False, True):
            with self.subTest(dirty=dirty):
                game, path = legacy_game()
                signature = content_signature(game)
                if dirty:
                    game.title += " edited"
                self.store.save_working(game, signature)
                loaded, saved = self.store.load_working()
                self.assertEqual(loaded.nodes[path[88].node_id].move_usi, "7f6g")
                self.assertEqual(content_signature(loaded) != saved, dirty)
                # The working JSON itself was repaired, not only this instance.
                again, _ = self.store.load_working()
                self.assertEqual(again.nodes[path[100].node_id].move_usi, "6g7g")


class EnginePositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="shogi-engine-test-")
        self.store = StateStore(Path(self.folder.name) / "app.db")
        with patch.dict(os.environ, {"SHOGI_ANALYZER_ENGINE_CMD": "", "SHOGI_ANALYZER_ENGINE_PATH": ""}):
            self.service = AnalysisService(self.store)
        self.service._cmd = [sys.executable, "-B", str(HERE / "fake_usi.py")]
        self.service._configured = True
        self.events = []

        async def sender(type_, payload=None):
            self.events.append((type_, payload))

        await self.service.attach_owner_sender(sender)

    async def asyncTearDown(self):
        await self.service.shutdown()
        self.store.close()
        self.folder.cleanup()

    async def test_rejected_position_never_searches_or_stores_previous_position(self):
        valid = GameTree.new()
        ok, reason = await self.service.start_for_game(valid)
        self.assertTrue(ok, reason)
        await asyncio.sleep(0.2)
        await self.service.stop()
        before = sum(line == "> go infinite" for line in self.service._io_log)
        invalid = GameTree.new()
        invalid.play_move(invalid.root_node_id, "7g7e")
        ok, reason = await self.service.start_for_game(invalid)
        self.assertFalse(ok)
        self.assertIn("invalid position", reason)
        self.assertFalse(self.service.status_wire()["analysis_running"])
        self.assertEqual(sum(line == "> go infinite" for line in self.service._io_log), before)
        self.assertEqual(self.store.latest_evals(invalid.game_id, list(invalid.nodes)), {})
        ok, reason = await self.service.start_for_game(valid)
        self.assertTrue(ok, reason)

    async def test_unexpected_engine_rejection_cannot_be_saved_as_new_analysis(self):
        game = GameTree.new()
        game.play_move(game.root_node_id, "2g2f")
        ok, reason = await self.service.start_for_game(game)
        self.assertTrue(ok, reason)
        for _ in range(50):
            await asyncio.sleep(0.02)
            if self.service.status_wire()["status"] == "error":
                break
        self.assertFalse(self.service.status_wire()["analysis_running"])
        self.assertEqual(self.service._latest_pv_by_index, {})
        self.assertFalse(any(type_ == "analysis:update" for type_, _ in self.events))
        self.assertEqual(self.store.latest_evals(game.game_id, list(game.nodes)), {})
        self.assertTrue(any(type_ == "analysis:stopped" and "Illegal Input Move" in payload.get("reason", "")
                            for type_, payload in self.events))

    async def test_legacy_history_is_normalized_before_sending(self):
        game, _ = legacy_game()
        ok, reason = await self.service.start_for_game(game)
        self.assertTrue(ok, reason)
        command = next(line for line in self.service._io_log if line.startswith("> position "))
        self.assertNotIn("7f6g+", command)
        self.assertNotIn("6g7g+", command)


if __name__ == "__main__":
    unittest.main()
