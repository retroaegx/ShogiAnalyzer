"""Share image: the shown position drawn on the server from data (not a screenshot).

The page sends what it shows (position, arrows with their labels, evaluation, theme names, the
UI colors, the UI theme's background image and the computed CSS of both piece stands); this
module draws the background, the board image of the selected theme, the pieces, both stands
(sized like the page's: app.css .stand / .stand-pieces / .hand-piece), the arrows / drop markers
and their pills, and a header line, and returns a PNG.

Arrow geometry, label placement and colors follow the page's board overlay (app.js
overlayShape / moveLabel, app.css .board-overlay), measured in board-image pixels.
"""

from __future__ import annotations

import html
import io
import json
import math
import re
import secrets
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..core.sfen_ops import parse_sfen
from ..paths import data_dir

ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets_web"
FONT_DIR = Path(__file__).resolve().parent / "share_fonts"
# our own font (tools/share_font builds it from stroke skeletons)
FONT = FONT_DIR / "ShogiAnalyzerMaru.ttf"

# the characters the font has: everything the app sends (move text, evaluation, arrow labels)
# and the picture's own words; any other character is dropped from the image text
GLYPHS = (
    " 0123456789+-()"
    "　一二三四五六七八九１２３４５６７８９同歩香桂銀金角飛玉成馬龍打と"
    "投了勝ち宣言開始局面手目評価値詰先後やや有利優勢互角"
    "指し手分岐候補・不成なし▲△☗☖—"
)
_GLYPH_SET = set(GLYPHS)

SS = 2  # drawn at twice the size, then reduced (smooth edges)
BOARD_PX = 760  # board image width in the final picture
PAD = 28
HEADER_H = 56

PIECE_NAMES = {
    "P": "pawn", "L": "lance", "N": "knight", "S": "silver", "G": "gold", "B": "bishop", "R": "rook", "K": "king",
    "+P": "promoted_pawn", "+L": "promoted_lance", "+N": "promoted_knight", "+S": "promoted_silver",
    "+B": "horse", "+R": "dragon",
}
HAND_ORDER = ["R", "B", "G", "S", "N", "L", "P"]
RANK_KANJI = "一二三四五六七八九"
DROP_CHAR = {"P": "歩", "L": "香", "N": "桂", "S": "銀", "G": "金", "B": "角", "R": "飛"}

# app.css .board-overlay
ARROW_STYLE = {
    "best": {"fill": (40, 215, 200, 0.5), "stroke": (220, 255, 252, 0.75), "glow": (60, 225, 215, 0.6)},
    "best sub": {"fill": (40, 215, 200, 0.28), "stroke": (220, 255, 252, 0.4), "glow": (60, 225, 215, 0.35)},
    "next": {"fill": (245, 158, 11, 0.5), "stroke": (255, 236, 200, 0.75), "glow": (245, 170, 40, 0.55)},
    "branch": {"fill": (245, 158, 11, 0.5), "stroke": (245, 158, 11, 0.95), "glow": (0, 0, 0, 0.35)},
}
MARK_FILL = {"best": (40, 205, 195, 0.72), "best sub": (40, 205, 195, 0.72), "next": (245, 158, 11, 0.72), "branch": (245, 158, 11, 0.72)}
LABEL_STYLE = {  # pill border, name color, opacity
    "best": ((90, 235, 220, 0.95), "#d2fbf6", 1.0),
    "sub": ((90, 235, 220, 0.6), "#d2fbf6", 0.85),
    "next": ((245, 158, 11, 0.95), "#ffe3b3", 1.0),
    "branch": ((245, 158, 11, 0.6), "#f5d9a8", 0.8),
}
PILL_FILL = (12, 14, 18, 0.86)
LABEL_SCALE = 1.3  # pills a little larger than on the page: a posted picture is usually seen small
SCORE_COLOR = {"plus": "#f3ede2", "minus": "#b9c8ff", "": "#f3ede2"}
PROMO_COLOR = "#f5d9a8"
LAST_MOVE = (239, 68, 68)


class ShareImageError(ValueError):
    pass


# ---------- input ----------
def _text(value: Any, limit: int = 40) -> str:
    return "".join(ch for ch in str(value or "")[:limit] if ch in _GLYPH_SET)


def _rgba(value: Any, default: tuple[int, int, int, float]) -> tuple[int, int, int, float]:
    s = str(value or "").strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", s)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 1.0
    m = re.fullmatch(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)", s)
    if m:
        a = m.group(4)
        alpha = 1.0 if a is None else (float(a[:-1]) / 100 if a.endswith("%") else float(a))
        return int(float(m.group(1))), int(float(m.group(2))), int(float(m.group(3))), max(0.0, min(alpha, 1.0))
    return default


def _c(color: tuple[int, int, int, float], mul: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b, a = color
    return int(r), int(g), int(b), int(round(255 * max(0.0, min(a * mul, 1.0))))


def _hex(s: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    return _c(_rgba(s, (255, 255, 255, 1.0)), alpha)


def _css_colors(value: str) -> list[str]:
    return re.findall(r"rgba?\([^)]*\)|#[0-9a-fA-F]{6}\b", value or "")


def _split_top(value: str) -> list[str]:
    """Split a CSS list at commas outside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in value or "":
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _gradients(value: str) -> list[dict[str, Any]]:
    """linear-gradient()s of a computed background-image, top-to-bottom or left-to-right:
    [{"h": bool, "stops": [(color, 0..1), ...]}, ...] (other directions and url() layers are skipped)."""
    out = []
    for layer in _split_top(value):
        m = re.fullmatch(r"linear-gradient\((.*)\)", layer.strip())
        if not m:
            continue
        parts = _split_top(m.group(1))
        horizontal = bool(parts) and parts[0].strip() in {"90deg", "to right"}
        if parts and not _css_colors(parts[0]) and parts[0].strip() not in {"180deg", "to bottom", "90deg", "to right"}:
            continue  # another direction: not drawn
        stops: list[tuple[tuple[int, int, int, float], float | None]] = []
        for part in parts:
            cols = _css_colors(part)
            if not cols:
                continue
            pos = re.search(r"([\d.]+)%\s*$", part)
            stops.append((_rgba(cols[0], (0, 0, 0, 0.0)), float(pos.group(1)) / 100 if pos else None))
        if len(stops) < 2:
            continue
        if stops[0][1] is None:
            stops[0] = (stops[0][0], 0.0)
        if stops[-1][1] is None:
            stops[-1] = (stops[-1][0], 1.0)
        for i, (c, p) in enumerate(stops):  # unpositioned stops: evenly between their neighbours
            if p is None:
                j = next(j for j in range(i + 1, len(stops)) if stops[j][1] is not None)
                stops[i] = (c, stops[i - 1][1] + (stops[j][1] - stops[i - 1][1]) / (j - i + 1))
        out.append({"h": horizontal, "stops": stops})
    return out


def _gradient_image(g: dict[str, Any], w: int, h: int) -> Image.Image:
    n = w if g["h"] else h
    strip = Image.new("RGBA", (n, 1) if g["h"] else (1, n))
    stops = g["stops"]
    for k in range(n):
        t = k / max(1, n - 1)
        j = next((j for j in range(1, len(stops)) if stops[j][1] >= t), len(stops) - 1)
        (c0, p0), (c1, p1) = stops[j - 1], stops[j]
        f = 0.0 if p1 <= p0 else max(0.0, min((t - p0) / (p1 - p0), 1.0))
        strip.putpixel((k, 0) if g["h"] else (0, k), _c(tuple(c0[i] + (c1[i] - c0[i]) * f for i in range(4))))
    return strip.resize((w, h))


def _shadows(value: str) -> list[dict[str, Any]]:
    """Computed box-shadow -> [{inset, x, y, blur, spread, color}] (lengths in CSS px)."""
    out = []
    for part in _split_top("" if value in {None, "none"} else value):
        cols = _css_colors(part)
        nums = [float(n) for n in re.findall(r"(-?[\d.]+)px", re.sub(r"rgba?\([^)]*\)", "", part))]
        if not cols or len(nums) < 2:
            continue
        nums += [0.0] * (4 - len(nums))
        out.append({"inset": "inset" in part, "x": nums[0], "y": nums[1], "blur": nums[2], "spread": nums[3],
                    "color": _rgba(cols[0], (0, 0, 0, 0.0))})
    return out


def _px(value: Any, default: float) -> float:
    m = re.match(r"\s*([\d.]+)px", str(value or ""))
    return float(m.group(1)) if m else default


def _move_target(usi: str) -> dict[str, int | str | None] | None:
    """(row, col) are SFEN board indexes: row 0 = rank 一, col 0 = file 9."""
    m = re.fullmatch(r"([1-9])([a-i])([1-9])([a-i])(\+?)", usi or "")
    if m:
        return {"fromRow": ord(m.group(2)) - 97, "fromCol": 9 - int(m.group(1)), "row": ord(m.group(4)) - 97, "col": 9 - int(m.group(3)), "drop": None}
    m = re.fullmatch(r"([PLNSGBR])\*([1-9])([a-i])", usi or "")
    if m:
        return {"fromRow": None, "fromCol": None, "row": ord(m.group(3)) - 97, "col": 9 - int(m.group(2)), "drop": m.group(1)}
    return None


# ---------- theme ----------
@lru_cache(maxsize=1)
def _theme_config() -> dict[str, Any]:
    return json.loads((ASSETS_DIR / "board-theme" / "config.json").read_text(encoding="utf-8"))


def _asset_path(url: str) -> Path:
    path = (ASSETS_DIR / str(url).lstrip("/")).resolve()
    if ASSETS_DIR.resolve() not in path.parents:
        raise ShareImageError("asset outside the web folder")
    return path


@lru_cache(maxsize=64)
def _image(url: str) -> Image.Image:
    with Image.open(_asset_path(url)) as im:
        return im.convert("RGBA")


@lru_cache(maxsize=256)
def _scaled(url: str, w: int, h: int, rotate: bool) -> Image.Image:
    im = _image(url).resize((w, h), Image.LANCZOS)
    return im.rotate(180) if rotate else im


@lru_cache(maxsize=32)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(1, size))


def _pick(sets: list[dict[str, Any]], name: Any) -> dict[str, Any]:
    for s in sets:
        if s.get("name") == name:
            return s
    return sets[0]


# ---------- drawing helpers ----------
def _layer(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _alpha(layer: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 1.0:
        return layer
    a = layer.getchannel("A").point(lambda v: int(v * opacity))
    layer.putalpha(a)
    return layer


def _text_outline(draw: ImageDraw.ImageDraw, xy, text, font, fill, outline, width, anchor="mm") -> None:
    draw.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=width, stroke_fill=outline)


class _Renderer:
    def __init__(self, data: dict[str, Any]) -> None:
        cfg = _theme_config()
        self.bg_set = _pick(cfg.get("background_sets") or [], data.get("background"))
        self.piece_set = _pick(cfg.get("piece_sets") or [], data.get("pieces"))
        try:
            self.pos = parse_sfen(str(data.get("sfen") or ""))
        except Exception as exc:
            raise ShareImageError(f"invalid position: {exc}") from exc
        self.flip = bool(data.get("flip"))
        self.handicap = bool(data.get("handicap"))
        self.coords = data.get("coords") if data.get("coords") in {"overlay", "outside", "off"} else "overlay"
        self.last_move = _move_target(str(data.get("last_move") or "")) if data.get("last_move") else None
        colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
        self.bg = _rgba(colors.get("bg"), (11, 12, 15, 1.0))
        self.ink = _rgba(colors.get("ink"), (236, 238, 242, 1.0))
        self.muted = _rgba(colors.get("muted"), (170, 176, 188, 1.0))
        self.accent = _rgba(colors.get("accent"), (212, 175, 90, 1.0))
        self.accent_ink = _rgba(colors.get("accent_ink"), (20, 16, 8, 1.0))
        self.header_left = _text(data.get("title"), 40)
        self.header_right = _text(data.get("eval"), 40)
        self.arrows = self._arrows(data.get("arrows"))
        theme = data.get("theme") if isinstance(data.get("theme"), dict) else {}
        self.page_bg = self._page_bg(theme.get("background"))
        self.faint = _rgba(theme.get("faint"), self.muted)
        self.stand_css = {"top": self._stand_css(theme.get("stand_top")), "bottom": self._stand_css(theme.get("stand_bottom"))}
        bar = theme.get("topbar") if isinstance(theme.get("topbar"), dict) else {}
        self.topbar = {"bg": _rgba(bar.get("bg"), (0, 0, 0, 0.0)), "grads": _gradients(str(bar.get("bg_image") or "")),
                       "border": _rgba(bar.get("border"), (0, 0, 0, 0.0))}

        bg_url = self.bg_set.get("background") or ""
        board = _image(bg_url)
        self.nat_w, self.nat_h = board.size
        xs, ys = self._grid_lines()
        self.xs, self.ys = xs, ys
        self.rx, self.ry = xs[0], ys[0]
        self.rw, self.rh = xs[9] - xs[0], ys[9] - ys[0]
        self.k = BOARD_PX * SS / self.nat_w  # canvas px per board-image px
        self.board_w = round(self.nat_w * self.k)
        self.board_h = round(self.nat_h * self.k)
        out = SS * (20 if self.coords == "outside" else 0)
        self.coord_band = out
        # stands sized like the page's (--stand-w: 1.9 cells); CSS px scale with the cell (80 px cell = 1:1)
        self.cell = (xs[1] - xs[0]) * self.k
        self.u = self.cell / 80
        stand_w = round(self.cell * 1.9)
        self.gap = round(self.cell * 0.3)
        self.W = 2 * PAD * SS + 2 * stand_w + 2 * self.gap + self.board_w + out
        self.H = 2 * PAD * SS + HEADER_H * SS + self.board_h + out
        self.bx = PAD * SS + stand_w + self.gap
        self.by = PAD * SS + HEADER_H * SS + out
        self.stand_w = stand_w
        self.labels: list[tuple[float, float, float, float]] = []
        self.obstacles: list[tuple[float, float, float, float, int]] = []

    # ----- data -----
    @staticmethod
    def _arrows(raw: Any) -> list[dict[str, Any]]:
        out = []
        for i, a in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(a, dict) or a.get("kind") not in ARROW_STYLE:
                continue
            t = _move_target(str(a.get("usi") or ""))
            if not t:
                continue
            score = a.get("score") if isinstance(a.get("score"), dict) else None
            out.append({
                "usi": str(a.get("usi")), "t": t, "kind": a["kind"], "owner": i,
                "weight": max(0.3, min(float(a.get("weight") or 1), 1.2)),
                "name": _text(a.get("name"), 12),
                "score": None if not score else {
                    "text": _text(score.get("text"), 12),
                    "cls": score.get("cls") if score.get("cls") in {"plus", "minus"} else "",
                    "promo": _text(score.get("promo"), 4),
                },
            })
            if len(out) >= 24:
                break
        return out

    @staticmethod
    def _page_bg(url: Any) -> str | None:
        """The UI theme's background image (body background, app.css --app-bg), if it is one of ours."""
        path = str(url or "").split("?")[0]
        if not re.fullmatch(r"/img/[\w/.-]+\.(?:webp|png|jpe?g)", path):
            return None
        try:
            _image(path)
        except Exception:
            return None
        return path

    def _stand_css(self, raw: Any) -> dict[str, Any]:
        """Computed CSS of one stand as the page draws it now (to move or not); defaults: a plain panel."""
        r = raw if isinstance(raw, dict) else {}
        ink = self.ink
        return {
            "bg": _rgba(r.get("bg"), (ink[0], ink[1], ink[2], 0.06)),
            "bg_grad": _gradients(str(r.get("bg_image") or "")),
            "border": _rgba(r.get("border"), (ink[0], ink[1], ink[2], 0.18)),
            "radius": _px(r.get("radius"), 6),
            "shadow": _shadows(str(r.get("shadow") or "none")),
            "label": _rgba(r.get("label"), self.muted),
            "mark": _rgba(r.get("mark"), self.ink),
            "pieces_bg": _rgba(r.get("pieces_bg"), (0, 0, 0, 0.18)),
            "pieces_grad": _gradients(str(r.get("pieces_bg_image") or "")),
            "pieces_border": _rgba(r.get("pieces_border"), (ink[0], ink[1], ink[2], 0.12)),
            "pieces_radius": _px(r.get("pieces_radius"), 4),
            "pieces_shadow": _shadows(str(r.get("pieces_shadow") or "none")),
        }

    def _grid_lines(self) -> tuple[list[float], list[float]]:
        g = self.bg_set.get("grid_lines") or {}
        ok = lambda v: isinstance(v, list) and len(v) == 10 and all(isinstance(n, (int, float)) for n in v)  # noqa: E731
        if ok(g.get("x")) and ok(g.get("y")):
            return [float(n) for n in g["x"]], [float(n) for n in g["y"]]
        reg = self.bg_set.get("board_region") or {}
        even = lambda a, b: [a + (b - a) * i / 9 for i in range(10)]  # noqa: E731
        if reg.get("start") and reg.get("end"):
            return even(float(reg["start"]["x"]), float(reg["end"]["x"])), even(float(reg["start"]["y"]), float(reg["end"]["y"]))
        return even(0, self.nat_w), even(0, self.nat_h)

    def _view(self, r: int, c: int) -> tuple[int, int]:
        return (8 - r, 8 - c) if self.flip else (r, c)

    def _upside_down(self, owner: str) -> bool:
        return (owner == "w") != self.flip

    def _piece_url(self, name: str, owner: str) -> str | None:
        p = self.piece_set.get("pieces") or {}
        if "sente" in p or "gote" in p:
            side = "sente" if owner == "b" else "gote"
            return (p.get(side) or {}).get(name) or (p.get("sente") or {}).get(name)
        return p.get(name)

    # overlay space (board-image px from the first grid line) -> canvas px
    def _o(self, x: float, y: float) -> tuple[float, float]:
        return self.bx + (x + self.rx) * self.k, self.by + (y + self.ry) * self.k

    def _cell_center(self, vr: int, vc: int) -> tuple[float, float]:
        xs, ys = self.xs, self.ys
        return (xs[vc] + xs[vc + 1]) / 2 - xs[0], (ys[vr] + ys[vr + 1]) / 2 - ys[0]

    def _side_name(self, owner: str) -> tuple[str, str]:
        shown = owner if not self.handicap else ("w" if owner == "b" else "b")
        return ("☗", "先手") if shown == "b" else ("☖", "後手")

    # ----- picture -----
    def render(self) -> Image.Image:
        img = Image.new("RGBA", (self.W, self.H), _c(self.bg))
        if self.page_bg:  # body { background: var(--bg) var(--app-bg) center / cover }
            src = _image(self.page_bg)
            sc = max(self.W / src.width, self.H / src.height)
            cover = src.resize((math.ceil(src.width * sc), math.ceil(src.height * sc)), Image.LANCZOS)
            img.alpha_composite(cover, (round((self.W - cover.width) / 2), round((self.H - cover.height) / 2)))
        self.img = img
        self._header()
        img.alpha_composite(_image(self.bg_set.get("background") or "").resize((self.board_w, self.board_h), Image.LANCZOS), (self.bx, self.by))
        self._last_move_squares()
        self._pieces()
        self._coords()
        self._stands()
        self._overlay()
        return img.resize((self.W // SS, self.H // SS), Image.LANCZOS).convert("RGB")

    def _header(self) -> None:
        band_h = (PAD + HEADER_H - 14) * SS
        self._topbar(band_h)
        d = ImageDraw.Draw(self.img)
        y = band_h // 2
        f = _font(str(FONT), 30 * SS)
        if self.header_left:
            d.text((PAD * SS, y), self.header_left, font=f, fill=_c(self.ink), anchor="lm")
        if self.header_right:
            d.text((self.W - PAD * SS, y), self.header_right, font=_font(str(FONT), 26 * SS), fill=_c(self.ink), anchor="rm")

    def _square_box(self, vr: int, vc: int) -> tuple[float, float, float, float]:
        x0, y0 = self._o(self.xs[vc] - self.rx, self.ys[vr] - self.ry)
        x1, y1 = self._o(self.xs[vc + 1] - self.rx, self.ys[vr + 1] - self.ry)
        return x0, y0, x1, y1

    def _last_move_squares(self) -> None:
        t = self.last_move
        if not t:
            return
        layer = _layer(self.img.size)
        d = ImageDraw.Draw(layer)
        vr, vc = self._view(int(t["row"]), int(t["col"]))
        d.rectangle(self._square_box(vr, vc), fill=(*LAST_MOVE, int(255 * 0.14)))
        if t["fromRow"] is not None:
            fr, fc = self._view(int(t["fromRow"]), int(t["fromCol"]))
            x0, y0, x1, y1 = self._square_box(fr, fc)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            r = min(x1 - x0, y1 - y0) * 0.17
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*LAST_MOVE, int(255 * 0.14)), outline=(*LAST_MOVE, int(255 * 0.85)), width=2 * SS)
        self.img.alpha_composite(layer)

    def _pieces(self) -> None:
        board = self.pos["board"]
        last = self.last_move
        for r in range(9):
            for c in range(9):
                tok = board[r][c]
                if not tok:
                    continue
                owner = "b" if tok[-1].isupper() else "w"
                name = PIECE_NAMES.get(("+" if tok.startswith("+") else "") + tok[-1].upper())
                url = self._piece_url(name, owner) if name else None
                vr, vc = self._view(r, c)
                x0, y0, x1, y1 = self._square_box(vr, vc)
                w, h = x1 - x0, y1 - y0
                pw, ph = round(w * 0.94), round(h * 0.94)
                px, py = round(x0 + (w - pw) / 2), round(y0 + (h - ph) / 2)
                if not url:
                    continue
                piece = _scaled(url, pw, ph, self._upside_down(owner))
                if last and last["row"] == r and last["col"] == c:
                    # the last moved piece: thin red outline (app.css .piece-wrap .outline)
                    a = piece.getchannel("A").filter(ImageFilter.MaxFilter(3 if SS < 2 else 5))
                    ring = Image.new("RGBA", piece.size, (*LAST_MOVE, 0))
                    ring.putalpha(a.point(lambda v: int(v * 0.92)))
                    self.img.alpha_composite(ring, (px, py))
                self.img.alpha_composite(piece, (px, py))

    def _coords(self) -> None:
        if self.coords == "off":
            return
        d = ImageDraw.Draw(self.img)
        for i in range(9):
            file_ = i + 1 if self.flip else 9 - i
            rank = 9 - i if self.flip else i + 1
            cx = (self.xs[i] + self.xs[i + 1]) / 2 - self.rx
            cy = (self.ys[i] + self.ys[i + 1]) / 2 - self.ry
            if self.coords == "overlay":
                f = _font(str(FONT), 13 * SS)
                x, _ = self._o(cx, 0)
                d.text((x, self.by + self.ry * self.k / 2), str(file_), font=f, fill=(255, 255, 255, 242), anchor="mm", stroke_width=2 * SS, stroke_fill=(0, 0, 0, 220))
                _, y = self._o(0, cy)
                right = self.bx + self.board_w - (self.nat_w - self.xs[9]) * self.k / 2
                d.text((right, y), RANK_KANJI[rank - 1], font=f, fill=(255, 255, 255, 242), anchor="mm", stroke_width=2 * SS, stroke_fill=(0, 0, 0, 220))
            else:
                f = _font(str(FONT), 13 * SS)
                x, _ = self._o(cx, 0)
                d.text((x, self.by - self.coord_band / 2), str(file_), font=f, fill=_c(self.muted), anchor="mm")
                _, y = self._o(0, cy)
                d.text((self.bx + self.board_w + self.coord_band / 2, y), RANK_KANJI[rank - 1], font=_font(str(FONT), 13 * SS), fill=_c(self.muted), anchor="mm")

    def _stands(self) -> None:
        top = "b" if self.flip else "w"
        bottom = "w" if self.flip else "b"
        grid_top = self.by + self.ry * self.k
        grid_bottom = self.by + (self.ry + self.rh) * self.k
        self._stand(top, PAD * SS, grid_top, "top")
        self._stand(bottom, self.bx + self.board_w + self.coord_band + self.gap, grid_bottom, "bottom")

    def _topbar(self, band_h: int) -> None:
        """app.css .topbar behind the header line: the theme's bar color and gradients, full width."""
        css = self.topbar
        layer = Image.new("RGBA", (self.W, band_h), _c(css["bg"]))
        for g in reversed(css["grads"]):
            layer.alpha_composite(_gradient_image(g, self.W, band_h))
        if css["border"][3] > 0:
            ImageDraw.Draw(layer).line((0, band_h - 1, self.W, band_h - 1), fill=_c(css["border"]), width=SS)
        self.img.alpha_composite(layer, (0, 0))

    def _panel(self, box: tuple[float, float, float, float], radius: float, fill, grads, border, shadows) -> None:
        """A CSS box: outer shadows, background color + top-to-bottom gradients, 1px border, inset shadows."""
        u = self.u
        x0, y0, x1, y1 = box
        for sh in shadows:
            if sh["inset"]:
                continue
            layer = _layer(self.img.size)
            sp, dx, dy = sh["spread"] * u, sh["x"] * u, sh["y"] * u
            ImageDraw.Draw(layer).rounded_rectangle((x0 - sp + dx, y0 - sp + dy, x1 + sp + dx, y1 + sp + dy), radius=max(0, radius + sp), fill=_c(sh["color"]))
            layer = layer.filter(ImageFilter.GaussianBlur(max(0.1, sh["blur"] * u / 2)))
            # an outer box-shadow is only drawn outside the box (it does not darken a see-through panel)
            hole = Image.new("L", layer.size, 255)
            ImageDraw.Draw(hole).rounded_rectangle(box, radius=radius, fill=0)
            layer.putalpha(Image.composite(layer.getchannel("A"), hole, hole))
            self.img.alpha_composite(layer)
        w, h = max(1, round(x1 - x0)), max(1, round(y1 - y0))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
        body = Image.new("RGBA", (w, h), _c(fill))
        for g in reversed(grads):  # the first CSS layer is on top
            body.alpha_composite(_gradient_image(g, w, h))
        for sh in shadows:  # inset 0 1px 0: a light line along the top edge
            if sh["inset"] and sh["blur"] == 0 and sh["y"] > 0:
                ImageDraw.Draw(body).line((radius, sh["y"] * u, w - radius, sh["y"] * u), fill=_c(sh["color"]), width=max(1, round(sh["y"] * u)))
        layer = _layer(body.size)
        layer.paste(body, (0, 0), mask)
        ImageDraw.Draw(layer).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, outline=_c(border), width=max(1, round(u)))
        self.img.alpha_composite(layer, (round(x0), round(y0)))

    def _stand(self, owner: str, x: float, y_edge: float, where: str) -> None:
        """app.css .stand: label row + .stand-pieces (2 columns, rows of 0.86 cell); the bottom one upside down."""
        css, u, cell = self.stand_css[where], self.u, self.cell
        label_h, gap = 20 * u, 6 * u
        pieces_h = cell * 3.44 + 18 * u
        h = label_h + gap + pieces_h + 2 * u
        y = y_edge if where == "top" else y_edge - h
        x1 = x + self.stand_w
        self._panel((x, y, x1, y + h), css["radius"] * u, css["bg"], css["bg_grad"], css["border"], css["shadow"])
        # label: mark + name, centred
        label_y = y + u + label_h / 2 if where == "top" else y + h - u - label_h / 2
        mark, name = self._side_name(owner)
        fm, fn = _font(str(FONT), round(14 * u)), _font(str(FONT), round(12 * u))
        lw = fm.getlength(mark) + 4 * u + fn.getlength(name)
        d = ImageDraw.Draw(self.img)
        d.text((x + self.stand_w / 2 - lw / 2, label_y), mark, font=fm, fill=_c(css["mark"]), anchor="lm")
        d.text((x + self.stand_w / 2 + lw / 2, label_y), name, font=fn, fill=_c(css["label"]), anchor="rm")
        # pieces box (inside the stand border)
        py0 = y + u + label_h + gap if where == "top" else y + u
        box = (x + u, py0, x1 - u, py0 + pieces_h)
        self._panel(box, css["pieces_radius"] * u, css["pieces_bg"], css["pieces_grad"], css["pieces_border"], css["pieces_shadow"])
        hands = self.pos["hands"][owner]
        items = [(p, hands.get(p, 0)) for p in HAND_ORDER if hands.get(p, 0)]
        inner_x0, inner_x1 = box[0] + u + 4 * u, box[2] - u - 4 * u
        inner_y0, inner_y1 = box[1] + u + 6 * u, box[3] - u - 6 * u
        d = ImageDraw.Draw(self.img)
        if not items:
            fe = _font(str(FONT), round(11 * u))
            ty = inner_y0 + 4 * u + 8 * u if where == "top" else inner_y1 - 4 * u - 8 * u
            d.text(((box[0] + box[2]) / 2, ty), "なし", font=fe, fill=_c(self.faint), anchor="mm")
            return
        col_w = (inner_x1 - inner_x0 - 2 * u) / 2
        row_h = cell * 0.86
        rows = (len(items) + 1) // 2
        top0 = inner_y0 if where == "top" else inner_y1 - rows * row_h - (rows - 1) * 2 * u
        for i, (p, n) in enumerate(items):
            cx0 = inner_x0 + (i % 2) * (col_w + 2 * u)
            cy0 = top0 + (i // 2) * (row_h + 2 * u)
            url = self._piece_url(PIECE_NAMES[p], owner)
            if url:
                src = _image(url)
                ph = row_h * 0.92
                pw = min(ph * src.width / src.height, col_w * 0.92)
                ph = pw * src.height / src.width
                pw_i, ph_i = max(1, round(pw)), max(1, round(ph))
                self.img.alpha_composite(_scaled(url, pw_i, ph_i, self._upside_down(owner)),
                                         (round(cx0 + (col_w - pw_i) / 2), round(cy0 + (row_h - ph_i) / 2)))
            if n > 1:  # .hand-piece .cnt
                bf = _font(str(FONT), round(11 * u))
                bh = 18 * u
                bw = max(18 * u, bf.getlength(str(n)) + 10 * u)
                bx1, by1 = cx0 + col_w - 2 * u, cy0 + row_h - 2 * u
                d.rounded_rectangle((bx1 - bw, by1 - bh, bx1, by1), radius=bh / 2, fill=_c(self.accent))
                d.text((bx1 - bw / 2, by1 - bh / 2), str(n), font=bf, fill=_c(self.accent_ink), anchor="mm")

    # ----- arrows (app.js renderOverlay / overlayShape / moveLabel) -----
    def _arrow_size(self, weight: float) -> tuple[float, float, float]:
        cell = self.rw / 9
        s = max(weight, 0.7)
        return cell * 0.085 * s, cell * 0.32 * s, cell * 0.32 * s

    def _add_obstacles(self, a: dict[str, Any]) -> None:
        t, weight, owner = a["t"], a["weight"], a["owner"]
        cell = self.rw / 9
        p1 = self._cell_center(*self._view(int(t["row"]), int(t["col"])))
        if t["fromRow"] is None:
            r = cell * 0.34 * max(weight, 0.8)
            self.obstacles.append((p1[0] - r, p1[1] - r, 2 * r, 2 * r, owner))
            return
        p0 = self._cell_center(*self._view(int(t["fromRow"]), int(t["fromCol"])))
        shaft_w, head_w, _ = self._arrow_size(weight)
        dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        steps = max(2, math.ceil(dist / (cell * 0.25)))
        for k in range(steps + 1):
            f = k / steps
            half = (head_w if f > 0.75 else shaft_w * 1.6) / 2
            x = p0[0] + (p1[0] - p0[0]) * f
            y = p0[1] + (p1[1] - p0[1]) * f
            self.obstacles.append((x - half, y - half, 2 * half, 2 * half, owner))

    def _overlay(self) -> None:
        for a in self.arrows:
            self._add_obstacles(a)
        # weaker shapes first so the best move / main line stay on top
        order = {"best sub": 0, "branch": 1, "next": 2, "best": 3}
        for a in sorted(self.arrows, key=lambda a: order[a["kind"]]):
            self._shape(a)
        # labels are placed in the arrows' original order (like the page), drawn on top of every arrow
        for a in self.arrows:
            if a["name"] or a["score"]:
                self._label(a)

    def _shape(self, a: dict[str, Any]) -> bool:
        t, kind, weight = a["t"], a["kind"], a["weight"]
        cell = self.rw / 9
        p1 = self._cell_center(*self._view(int(t["row"]), int(t["col"])))
        layer = _layer(self.img.size)
        d = ImageDraw.Draw(layer)
        if t["fromRow"] is None:
            r = cell * 0.34 * max(weight, 0.8)
            cx, cy = self._o(*p1)
            rr = r * self.k
            fade = 0.45 if kind in {"best sub", "branch"} else 1.0
            mark = _layer(self.img.size)
            md = ImageDraw.Draw(mark)
            md.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=_c(MARK_FILL[kind]), outline=(255, 255, 255, 230), width=max(1, round(cell * 0.05 * self.k)))
            ch = DROP_CHAR.get(str(t["drop"]), "打")
            f = _font(str(FONT), round(r * 1.2 * self.k))
            text = _layer((round(rr * 2.4), round(rr * 2.4)))
            ImageDraw.Draw(text).text((text.width / 2, text.height / 2), ch, font=f, fill=(255, 255, 255, 255), anchor="mm",
                                      stroke_width=max(1, round(cell * 0.045 * self.k)), stroke_fill=(0, 0, 0, 199))
            if self._upside_down(self.pos["side"]):
                text = text.rotate(180)
            mark.alpha_composite(text, (round(cx - text.width / 2), round(cy - text.height / 2)))
            self._put(mark, (0, 0, 0, 0.38), 6, dy=2, opacity=fade)
            a["anchor"], a["normal"], a["dist"], a["along"] = p1, (0.0, -1.0), r + cell * 0.04, None
            return True

        p0 = self._cell_center(*self._view(int(t["fromRow"]), int(t["fromCol"])))
        dist = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if dist < 1:
            return False
        u = ((p1[0] - p0[0]) / dist, (p1[1] - p0[1]) / dist)
        n = (-u[1], u[0])
        shaft_w, head_w, head_l = self._arrow_size(weight)
        start = (p0[0] + u[0] * cell * 0.22, p0[1] + u[1] * cell * 0.22)
        tip = (p1[0] + u[0] * cell * 0.04, p1[1] + u[1] * cell * 0.04)
        length = math.hypot(tip[0] - start[0], tip[1] - start[1])
        head_l = min(head_l, length * 0.6)
        base = (tip[0] - u[0] * head_l, tip[1] - u[1] * head_l)
        P = lambda p, k: self._o(p[0] + n[0] * k, p[1] + n[1] * k)  # noqa: E731
        poly = [P(start, shaft_w / 2), P(base, shaft_w / 2), P(base, head_w / 2), self._o(*tip),
                P(base, -head_w / 2), P(base, -shaft_w / 2), P(start, -shaft_w / 2)]
        st = ARROW_STYLE[kind]
        d.polygon(poly, fill=_c(st["fill"]), outline=_c(st["stroke"]), width=max(1, round(cell * 0.03 * self.k)))
        self._put(layer, st["glow"], 5, dy=0 if kind != "branch" else 2)
        # beside the middle of the shaft, on the upper side (right side for vertical moves)
        ln = n
        if ln[1] > 0.2 or (abs(ln[1]) <= 0.2 and ln[0] < 0):
            ln = (-n[0], -n[1])
        mid = ((start[0] + base[0]) / 2, (start[1] + base[1]) / 2)
        a["anchor"], a["normal"], a["dist"], a["along"] = mid, ln, shaft_w / 2 + cell * 0.08, u
        return True

    def _put(self, layer: Image.Image, glow: tuple[int, int, int, float] | None = None, blur_px: float = 0, dy: float = 0, opacity: float = 1.0) -> None:
        """Composite a full-size layer onto the picture, with a glow / drop shadow (CSS drop-shadow)
        under its shapes; only the area around the shapes is processed."""
        bbox = layer.getbbox()
        if not bbox:
            return
        m = int(blur_px * SS * 3 + abs(dy) * SS + 2)
        box = (max(0, bbox[0] - m), max(0, bbox[1] - m), min(layer.width, bbox[2] + m), min(layer.height, bbox[3] + m))
        part = layer.crop(box)
        if glow:
            shade = Image.new("RGBA", part.size, _c(glow)[:3] + (0,))
            shade.putalpha(part.getchannel("A").point(lambda v: int(v * glow[3])))
            shade = shade.filter(ImageFilter.GaussianBlur(blur_px * SS))
            if dy:
                shade = shade.transform(shade.size, Image.AFFINE, (1, 0, 0, 0, 1, -dy * SS))
            part = Image.alpha_composite(shade, part)
        self.img.alpha_composite(_alpha(part, opacity), (box[0], box[1]))

    def _label(self, a: dict[str, Any]) -> None:
        if "anchor" not in a:
            return
        kind = a["kind"]
        cls = "sub" if kind == "best sub" else kind.split(" ")[0]
        primary = kind in {"best", "next"}
        cell = self.rw / 9
        fs = cell * (0.17 if primary else 0.15) * LABEL_SCALE
        sfs, gap, pfs = fs * 1.12, fs * 0.35, fs * 0.78
        name, score = a["name"], a["score"]
        f_name = _font(str(FONT), max(1, round(fs * self.k)))
        f_score = _font(str(FONT), max(1, round(sfs * self.k)))
        f_promo = _font(str(FONT), max(1, round(pfs * self.k)))
        wl = lambda text, f: f.getlength(text) / self.k  # noqa: E731  (overlay units)
        promo_w = gap * 0.6 + wl(score["promo"], f_promo) if score and score["promo"] else 0
        w = wl(name, f_name) + ((gap if name else 0) + wl(score["text"], f_score) * 0.92 + promo_w if score else 0) + fs * 0.9
        h = fs * 1.5
        anchor, normal, dist, along = a["anchor"], a["normal"], a["dist"], a["along"]
        base = dist + abs(normal[0]) * (w / 2) + abs(normal[1]) * (h / 2)
        slides = [v * cell for v in (0, 0.9, -0.9, 1.6, -1.6)] if along else [0]
        clamp = lambda v, lo, hi: max(lo, min(v, hi))  # noqa: E731
        overlap = lambda p, q: p[0] < q[0] + q[2] and q[0] < p[0] + p[2] and p[1] < q[1] + q[3] and q[1] < p[1] + p[3]  # noqa: E731
        box = first = None
        for sl in slides:
            for k in (1, -1, 1.9, -1.9, 2.8, -2.8):
                cx = clamp(anchor[0] + normal[0] * base * k + (along[0] if along else 0) * sl, w / 2, self.rw - w / 2)
                cy = clamp(anchor[1] + normal[1] * base * k + (along[1] if along else 0) * sl, h / 2, self.rh - h / 2)
                cand = (cx - w / 2, cy - h / 2, w, h)
                first = first or cand
                m = h * 0.2
                padded = (cand[0] - m, cand[1] - m, w + 2 * m, h + 2 * m)
                if not any(overlap(b, padded) for b in self.labels) and not any(o[4] != a["owner"] and overlap(o, padded) for o in self.obstacles):
                    box = cand
                    break
            if box:
                break
        box = box or first
        self.labels.append(box)

        border, name_color, opacity = LABEL_STYLE[cls]
        layer = _layer(self.img.size)
        d = ImageDraw.Draw(layer)
        x0, y0 = self._o(box[0], box[1])
        x1, y1 = self._o(box[0] + w, box[1] + h)
        d.rounded_rectangle((x0, y0, x1, y1), radius=h * 0.35 * self.k, fill=_c(PILL_FILL), outline=_c(border), width=max(1, round(cell * 0.016 * self.k)))
        # text run centred in the pill: name, score, 成/不成
        parts = [(name, f_name, _hex(name_color))] if name else []
        if score:
            if name:
                parts.append((None, gap * self.k, None))
            parts.append((score["text"], f_score, _hex(SCORE_COLOR[score["cls"]])))
            if score["promo"]:
                parts.append((None, gap * 0.6 * self.k, None))
                parts.append((score["promo"], f_promo, _hex(PROMO_COLOR)))
        total = sum(p[1] if p[0] is None else p[1].getlength(p[0]) for p in parts)
        x = (x0 + x1) / 2 - total / 2
        cy = (y0 + y1) / 2
        for text, f, color in parts:
            if text is None:
                x += f
                continue
            d.text((x, cy), text, font=f, fill=color, anchor="lm")
            x += f.getlength(text)
        self._put(layer, opacity=opacity)


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_share_image(data: dict[str, Any]) -> bytes:
    return _png(_Renderer(data).render())


# ---------- share links (link card on X / Bluesky) ----------
# A post screen opened by a link (X / Bluesky intent) takes text and a URL only; the picture shows
# up as the URL's link card (og:image). The card page and its pictures open without logging in for
# anyone with the (unguessable) link; nothing else of the app does.
CARD_W, CARD_H = 1200, 628  # 1.91:1, the large link card: the whole picture fits without cropping
KEEP_SHARES = 300
SHARE_ID = re.compile(r"[A-Za-z0-9_-]{16}")


def share_dir() -> Path:
    return data_dir() / "share"


def _card(im: Image.Image, bg: tuple[int, int, int, float]) -> Image.Image:
    card = Image.new("RGB", (CARD_W, CARD_H), _c(bg)[:3])
    scale = min(CARD_W / im.width, CARD_H / im.height)
    fit = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    card.paste(fit, ((CARD_W - fit.width) // 2, (CARD_H - fit.height) // 2))
    return card


def create_share(data: dict[str, Any]) -> dict[str, Any]:
    """Draw the picture and keep it (with its link card and page text) under server/data/share."""
    r = _Renderer(data)
    im = r.render()
    sid = secrets.token_urlsafe(12)
    folder = share_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{sid}.png").write_bytes(_png(im))
    (folder / f"{sid}.card.png").write_bytes(_png(_card(im, r.bg)))
    meta = {"title": r.header_left, "description": r.header_right, "created": int(time.time())}
    (folder / f"{sid}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    _prune(folder)
    return {"id": sid}


def _prune(folder: Path) -> None:
    """Keep the newest KEEP_SHARES links (older posts lose their card picture)."""
    metas = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in metas[KEEP_SHARES:]:
        sid = old.stem
        for p in (old, folder / f"{sid}.png", folder / f"{sid}.card.png"):
            p.unlink(missing_ok=True)


def share_file(sid: str, card: bool = False) -> Path | None:
    if not SHARE_ID.fullmatch(sid or ""):
        return None
    p = share_dir() / f"{sid}{'.card' if card else ''}.png"
    return p if p.is_file() else None


def share_page(sid: str, base_url: str) -> str | None:
    """HTML of a share link: the card tags for X / Bluesky, and the picture for people who open it."""
    if not share_file(sid):
        return None
    try:
        meta = json.loads((share_dir() / f"{sid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    e = lambda v: html.escape(str(v or ""), quote=True)  # noqa: E731
    title = meta.get("title") or "局面"
    desc = meta.get("description") or ""
    page = f"{base_url}/s/{sid}"
    card = f"{base_url}/s/{sid}/card.png"
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta property="og:type" content="website"><meta property="og:url" content="{e(page)}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:image" content="{e(card)}"><meta property="og:image:width" content="{CARD_W}"><meta property="og:image:height" content="{CARD_H}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(card)}">
<style>body{{margin:0;background:#0b0c0f;display:grid;place-items:center;min-height:100vh}}img{{max-width:100%;height:auto;display:block}}</style>
</head><body><img src="/s/{e(sid)}.png" alt="{e(title)} {e(desc)}"></body></html>
"""
