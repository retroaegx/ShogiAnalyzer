import unittest
import math
from unittest.mock import patch

from server.app.services.overlay_layout import group_drop_arrows, place_label_box
from server.app.services.share_image import _Renderer


def arrows(pieces="PSG", square="5e"):
    return [{"usi": f"{piece}*{square}", "kind": "best" if i == 0 else "best sub", "weight": 1 if i == 0 else .6,
             "name": "候補手" if i == 0 else f"候補{i + 1}",
             "score": {"text": f"+{320 - i * 90}", "cls": "plus"}}
            for i, piece in enumerate(pieces)]


def overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


class SharedDropOverlayTests(unittest.TestCase):
    def test_knight_candidates_anchor_shared_image_labels_to_their_destinations(self):
        raw = [{"usi": usi, "kind": "best" if i == 0 else "best sub", "weight": 1 if i == 0 else .6,
                "name": f"候補{i + 1}", "score": {"text": "+35281", "cls": "plus"}}
               for i, usi in enumerate(["8d9f", "8d7f", "5h7h+"])]
        for flip in (False, True):
            renderer = _Renderer({"flip": flip, "arrows": raw})
            renderer.render()
            for arrow, box in zip(renderer.arrows, renderer.labels):
                target = arrow["t"]
                center = renderer._cell_center(*renderer._view(target["row"], target["col"]))
                self.assertTrue(arrow["linked"])
                self.assertAlmostEqual(math.dist(arrow["anchor"], center), renderer.rw / 9 * .04)
                end = (max(box[0], min(arrow["anchor"][0], box[0] + box[2])),
                       max(box[1], min(arrow["anchor"][1], box[1] + box[3])))
                self.assertLess(math.dist(arrow["anchor"], end), renderer.rw / 9 * .75)
            for i, box in enumerate(renderer.labels):
                self.assertFalse(any(overlap(box, other) for other in renderer.labels[i + 1:]))

    def test_shared_picture_groups_piece_names_and_preserves_evaluations(self):
        renderer = _Renderer({"arrows": arrows()})
        grouped = group_drop_arrows(renderer.arrows)
        self.assertEqual(len(grouped), 1)
        self.assertEqual([a["name"] for a in grouped[0]["rows"]], ["候補1 歩打", "候補2 銀打", "候補3 金打"])
        self.assertEqual([a["score"]["text"] for a in grouped[0]["rows"]], ["+320", "+230", "+140"])

    def test_same_drop_is_not_duplicated_in_group(self):
        raw = arrows()
        raw[0]["name"] = "指・候1"
        raw.insert(0, {"usi": "P*5e", "kind": "next", "name": "", "weight": 1})
        grouped = group_drop_arrows(_Renderer({"arrows": raw}).arrows)
        self.assertEqual(len(grouped[0]["rows"]), 3)
        self.assertEqual(grouped[0]["rows"][0]["name"], "指・候1 歩打")

    def test_group_placement_stays_inside_board_and_avoids_other_labels(self):
        for anchor in [(50, 50), (850, 50), (50, 850), (850, 850), (450, 450)]:
            labels = []
            for owner in range(3):
                box = place_label_box(anchor, (0, -1), 44, (1, 0), 240, 190,
                                      900, 900, 100, labels, [], owner)
                self.assertGreaterEqual(box[0], 0)
                self.assertGreaterEqual(box[1], 0)
                self.assertLessEqual(box[0] + box[2], 900)
                self.assertLessEqual(box[1] + box[3], 900)
                self.assertFalse(any(overlap(box, previous) for previous in labels))
                labels.append(box)

    def test_actual_share_render_separates_rows_and_other_move_labels(self):
        for flip, square in [(False, "5e"), (True, "1a")]:
            renderer = _Renderer({"flip": flip, "arrows": arrows("PLNSGBR", square) + arrows("SG", "2b")})
            with patch.object(renderer, "_label", wraps=renderer._label) as label:
                image = renderer.render()
                self.assertGreater(image.width, 500)
                boxes = [call.kwargs["fixed_box"] for call in label.call_args_list if "fixed_box" in call.kwargs]
            self.assertEqual(len(boxes), 9)
            for i, box in enumerate(boxes):
                self.assertFalse(any(overlap(box, other) for other in boxes[i + 1:]))


if __name__ == "__main__":
    unittest.main()
