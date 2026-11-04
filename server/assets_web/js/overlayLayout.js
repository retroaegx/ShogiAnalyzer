const DROP_NAMES = { P: "歩", L: "香", N: "桂", S: "銀", G: "金", B: "角", R: "飛" };
const priority = { "best sub": 0, branch: 1, next: 2, best: 3 };

/** Keep one target marker and one list when different pieces can be dropped on a square. */
export function groupDropSpecs(specs) {
  const targets = new Map();
  specs.forEach((spec, owner) => {
    const match = /^([PLNSGBR])\*([1-9][a-i])$/.exec(spec[0]);
    if (!match) return;
    const entries = targets.get(match[2]) || [];
    entries.push({ spec, owner });
    targets.set(match[2], entries);
  });
  const grouped = new Map();
  for (const entries of targets.values()) {
    const moves = new Map();
    for (const entry of entries) {
      const previous = moves.get(entry.spec[0]);
      if (!previous || entry.spec[4]) moves.set(entry.spec[0], entry);
    }
    if (moves.size < 2) continue; // retain the existing 指し手 / candidate animation for one move
    const representative = entries.reduce((a, b) => priority[a.spec[1]] >= priority[b.spec[1]] ? a : b);
    const rows = [...moves.values()]
      .sort((a, b) => Number(Boolean(b.spec[4])) - Number(Boolean(a.spec[4])) || a.owner - b.owner)
      .map(({ spec }) => ({ text: [spec[3] === "候補手" ? "候補1" : spec[3], `${DROP_NAMES[spec[0][0]]}打`].filter(Boolean).join(" "),
        kind: spec[1], score: spec[4], primary: spec[1] === "best" || spec[1] === "next" }));
    const group = { spec: representative.spec, owner: entries[0].owner, rows };
    for (const entry of entries) grouped.set(entry.owner, group);
  }
  return specs.flatMap((spec, owner) => {
    const group = grouped.get(owner);
    return group ? (group.owner === owner ? [group] : []) : [{ spec, owner, rows: null }];
  });
}

export const boxesOverlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Prefer the usual nearby position, then find free space instead of stacking labels. */
export function placeOverlayLabel({ anchor, normal, dist, along, w, h, rw, rh, cell, labels, obstacles, owner }) {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi));
  const base = dist + Math.abs(normal.x) * w / 2 + Math.abs(normal.y) * h / 2;
  const margin = cell * 0.035;
  const padded = (box) => ({ x: box.x - margin, y: box.y - margin, w: w + 2 * margin, h: h + 2 * margin });
  const free = (box) => !labels.some((other) => boxesOverlap(other, padded(box)));
  const clear = (box) => !obstacles.some((other) => other.owner !== owner && boxesOverlap(other, padded(box)));
  let first, nearby;
  let nearbyCost = Infinity;
  for (const slide of along ? [0, .9, -.9, 1.6, -1.6] : [0]) {
    for (const k of [1, -1, 1.9, -1.9, 2.8, -2.8]) {
      const box = { x: clamp(anchor.x + normal.x * base * k + (along?.x || 0) * slide * cell - w / 2, 0, rw - w),
        y: clamp(anchor.y + normal.y * base * k + (along?.y || 0) * slide * cell - h / 2, 0, rh - h), w, h };
      first ??= box;
      if (free(box) && clear(box)) {
        const dx = box.x + w / 2 - anchor.x, dy = box.y + h / 2 - anchor.y;
        const cost = dx * dx + dy * dy + (k < 0 ? cell * cell * .04 : 0);
        if (cost < nearbyCost) { nearby = box; nearbyCost = cost; }
      }
    }
  }
  if (nearby) return nearby;
  let best = null;
  let bestCost = Infinity;
  const xs = new Set([0, rw - w, clamp(anchor.x - w / 2, 0, rw - w)]);
  const ys = new Set([0, rh - h, clamp(anchor.y - h / 2, 0, rh - h)]);
  for (let x = 0; x <= rw - w; x += cell * .35) xs.add(x);
  for (let y = 0; y <= rh - h; y += cell * .35) ys.add(y);
  for (const x of xs) for (const y of ys) {
    const box = { x, y, w, h };
    if (!free(box)) continue;
    const cost = (clear(box) ? 0 : rw * rh) + (x + w / 2 - anchor.x) ** 2 + (y + h / 2 - anchor.y) ** 2;
    if (cost < bestCost) { best = box; bestCost = cost; }
  }
  return best || first;
}
