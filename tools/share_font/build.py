"""Build the share-image font (server/app/services/share_fonts/ShogiAnalyzerMaru.ttf).

The font is our own: every glyph is a stroke skeleton in glyphs.py / glyphs_ref.py, drawn
with round ends and joins. It holds only the characters of share_image.GLYPHS.

Usage (development only):
  pip install shapely fonttools
  python tools/share_font/build.py

To draw a new character: add its skeleton, add it to GLYPHS, run this again.
"""
import ast
import math
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from glyphs import DIGITS, FRAME, FRAME_EXCEPTIONS, KANJI
from glyphs_ref import ASCII_EXTRA, REF, REF_TF, SYMBOLS

W = 76  # stroke width (font units, 1000/em)
W_DIGIT = W * 1.15
ASC, DESC = 880, 120  # font y = ASC - design y


def bez(p0, c, p1, n=14):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]) for t in (i / n for i in range(1, n + 1))]


def stroke_pts(s):
    pts = [s[0]]
    for it in s[1:]:
        if isinstance(it[0], str):
            pts += bez(pts[-1], it[1], it[2])
        else:
            pts.append(it)
    return pts


def transform(strokes, tf):
    out = []
    for s in strokes:
        if isinstance(s, tuple) and s[0] == "e":  # ellipse: map its centre, scale its radii like the x/y axes
            c, ex, ey = tf((s[1], s[2])), tf((s[1] + s[3], s[2])), tf((s[1], s[2] + s[4]))
            out.append(("e", *c, abs(ex[0] - c[0]), abs(ey[1] - c[1])))
        else:
            out.append([tf(s[0])] + [(it[0], tf(it[1]), tf(it[2])) if isinstance(it[0], str) else tf(it) for it in s[1:]])
    return out


def fit(strokes, w, frame):
    """Scale/move the skeleton so the inked glyph (skeleton + half the stroke) fills frame."""
    pts = [p for s in strokes for p in stroke_pts(s)]
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    x1, y1 = max(p[0] for p in pts), max(p[1] for p in pts)
    h = w / 2
    fx0, fy0, fx1, fy1 = frame[0] + h, frame[1] + h, frame[2] - h, frame[3] - h
    sx, sy = (fx1 - fx0) / (x1 - x0), (fy1 - fy0) / (y1 - y0)
    return transform(strokes, lambda p: (fx0 + (p[0] - x0) * sx, fy0 + (p[1] - y0) * sy))


def shape(strokes, w):
    parts = []
    for s in strokes:
        if isinstance(s, tuple) and s[0] == "poly":
            parts.append(Polygon(s[1]).buffer(-w / 2).buffer(w / 2, quad_segs=8))  # rounded corners, same outer size
        elif isinstance(s, tuple) and s[0] == "dot":
            parts.append(Point(s[1]).buffer(s[2], quad_segs=8))
        elif isinstance(s, tuple) and s[0] == "e":  # closed ellipse (cx, cy, rx, ry)
            _, cx, cy, rx, ry = s
            ring = [(cx + rx * math.cos(a), cy + ry * math.sin(a)) for a in (2 * math.pi * i / 72 for i in range(72))]
            parts.append(LineString(ring + [ring[0]]).buffer(w / 2, quad_segs=8))
        else:
            parts.append(LineString(stroke_pts(s)).buffer(w / 2, cap_style="round", join_style="round", quad_segs=8))
    return unary_union(parts).simplify(1.0) if parts else None


def glyph_table():
    """{char: (advance, geometry)}"""
    out = {}
    for ch, st in KANJI.items():
        out[ch] = (1000, shape(fit(st, W, FRAME_EXCEPTIONS.get(ch, FRAME)), W))
    for ch, st in REF.items():
        out[ch] = (1000, shape(transform(st, REF_TF), W))
    for ch, st in SYMBOLS.items():
        out[ch] = (1000, shape(st, W))
    for ch, st in DIGITS.items():
        out[ch] = (600, shape(st, W_DIGIT))
        if ch.isdigit():  # full-width digits: the same figure centred in a 1000 cell
            big = transform(st, lambda p: (500 + (p[0] - 300) * 1.18, 490 + (p[1] - 530) * 1.18))
            out[chr(ord(ch) + 0xFEE0)] = (1000, shape(big, W_DIGIT))
    for ch, (adv, st) in ASCII_EXTRA.items():
        out[ch] = (adv, shape(st, W_DIGIT))
    return out


def draw(pen, geom):
    if geom is None:
        return
    for p in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
        # font coords (y up): TrueType outer contours clockwise, holes counter-clockwise
        p = orient(Polygon([(x, ASC - y) for x, y in p.exterior.coords], [[(x, ASC - y) for x, y in r.coords] for r in p.interiors]), sign=-1.0)
        for ring in [p.exterior, *p.interiors]:
            c = [(round(x), round(y)) for x, y in list(ring.coords)[:-1]]
            pen.moveTo(c[0])
            for pt in c[1:]:
                pen.lineTo(pt)
            pen.closePath()


def build(path, family="ShogiAnalyzer Maru"):
    order, glyphs, cmap, adv = [".notdef"], {".notdef": TTGlyphPen(None).glyph()}, {}, {".notdef": 500}
    for ch, (a, geom) in sorted(glyph_table().items()):
        name = f"uni{ord(ch):04X}"
        pen = TTGlyphPen(None)
        draw(pen, geom)
        glyphs[name] = pen.glyph()
        order.append(name)
        cmap[ord(ch)] = name
        adv[name] = a
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (a, getattr(glyphs[n], "xMin", 0)) for n, a in adv.items()})
    fb.setupHorizontalHeader(ascent=ASC, descent=-DESC)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=ASC, sTypoDescender=-DESC, usWinAscent=ASC, usWinDescent=DESC)
    fb.setupPost()
    fb.save(path)
    return {chr(c) for c in cmap}


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "server" / "app" / "services" / "share_image.py"
OUT = MODULE.parent / "share_fonts" / "ShogiAnalyzerMaru.ttf"


def needed() -> str:
    # GLYPHS = "..." in share_image.py, read without importing the server
    for node in ast.parse(MODULE.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "GLYPHS":
            return ast.literal_eval(node.value)
    raise SystemExit("GLYPHS not found")


if __name__ == "__main__":
    chars = build(OUT)
    missing = [ch for ch in needed() if ch not in chars]
    print(f"{OUT.name}: {OUT.stat().st_size} bytes, {len(chars)} glyphs")
    if missing:
        raise SystemExit(f"no skeleton for: {''.join(missing)}")
