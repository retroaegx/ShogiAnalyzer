"""Drop grouping and label placement shared by the server-rendered picture's overlays."""
import math


DROP_NAMES = {"P": "歩", "L": "香", "N": "桂", "S": "銀", "G": "金", "B": "角", "R": "飛"}
PRIORITY = {"best sub": 0, "branch": 1, "next": 2, "best": 3}


def group_drop_arrows(arrows):
    targets = {}
    for arrow in arrows:
        t = arrow["t"]
        if t["fromRow"] is None:
            targets.setdefault((t["row"], t["col"]), []).append(arrow)
    grouped = {}
    for entries in targets.values():
        moves = {}
        for arrow in entries:
            if arrow["usi"] not in moves or arrow["score"]:
                moves[arrow["usi"]] = arrow
        if len(moves) < 2:
            continue
        representative = max(entries, key=lambda a: PRIORITY[a["kind"]])
        rows = []
        for arrow in sorted(moves.values(), key=lambda a: (not bool(a["score"]), a["owner"])):
            row = dict(arrow)
            name = "候補1" if arrow["name"] == "候補手" else arrow["name"]
            row["name"] = " ".join(filter(None, [name, DROP_NAMES[arrow["t"]["drop"]] + "打"]))
            rows.append(row)
        group = {**representative, "owner": entries[0]["owner"], "rows": rows}
        for arrow in entries:
            grouped[arrow["owner"]] = group
    return [grouped.get(a["owner"], a) for a in arrows
            if a["owner"] not in grouped or grouped[a["owner"]]["owner"] == a["owner"]]


def place_label_box(anchor, normal, dist, along, w, h, rw, rh, cell, labels, obstacles, owner):
    def overlap(a, b):
        return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]

    clamp = lambda v, lo, hi: max(lo, min(v, hi))
    margin = cell * 0.035

    def padded(box):
        return box[0] - margin, box[1] - margin, w + 2 * margin, h + 2 * margin

    def free(box):
        return not any(overlap(other, padded(box)) for other in labels)

    def clear(box):
        return not any(other[4] != owner and overlap(other, padded(box)) for other in obstacles)

    base = dist + abs(normal[0]) * w / 2 + abs(normal[1]) * h / 2
    first = None
    for slide in (0, .9, -.9, 1.6, -1.6) if along else (0,):
        for k in (1, -1, 1.9, -1.9, 2.8, -2.8):
            box = (clamp(anchor[0] + normal[0] * base * k + (along[0] if along else 0) * slide * cell - w / 2, 0, rw - w),
                   clamp(anchor[1] + normal[1] * base * k + (along[1] if along else 0) * slide * cell - h / 2, 0, rh - h), w, h)
            first = first or box
            if free(box) and clear(box):
                return box
    xs = {0, rw - w, clamp(anchor[0] - w / 2, 0, rw - w)}
    ys = {0, rh - h, clamp(anchor[1] - h / 2, 0, rh - h)}
    xs.update(i * cell * .35 for i in range(math.floor((rw - w) / (cell * .35)) + 1))
    ys.update(i * cell * .35 for i in range(math.floor((rh - h) / (cell * .35)) + 1))
    best, best_cost = None, math.inf
    for x in sorted(xs):
        for y in sorted(ys):
            box = x, y, w, h
            if not free(box):
                continue
            cost = (0 if clear(box) else rw * rh) + (x + w / 2 - anchor[0]) ** 2 + (y + h / 2 - anchor[1]) ** 2
            if cost < best_cost:
                best, best_cost = box, cost
    return best or first
