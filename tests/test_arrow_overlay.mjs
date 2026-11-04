import assert from "node:assert/strict";
import test from "node:test";
import { layout, renderOverlay } from "./overlay_harness.mjs";

// The reported position: two knight moves from one square, plus a horizontal rook move.
const specs = [
  ["8d9f", "next", 1, "", null, true],
  ["8d9f", "best", 1, "指・候1", { text: "△詰11", cls: "minus" }, true],
  ["8d7f", "best sub", .6, "候補2", { text: "+7521", cls: "plus" }, false],
  ["5h7h+", "best sub", .6, "候補3", { text: "+35281", cls: "plus", promo: "成" }, false],
];

test("split knight candidates keep labels by their own destinations and have explicit leaders", () => {
  for (const width of [320, 390, 900]) for (const flip of [false, true]) {
    const { svg, boxes } = renderOverlay(specs, { width, flip });
    const labels = svg.querySelectorAll(".mv-label");
    assert.equal(labels.length, 3);
    assert.equal(svg.querySelectorAll(".label-link").length, 3);
    for (let i = 0; i < labels.length; i++) {
      const path = labels[i].querySelector("path").attributes.d;
      const [x, y, ex, ey] = path.match(/-?\d+(?:\.\d+)?/g).map(Number);
      const name = labels[i].querySelector("tspan").textContent;
      const target = specs.find((spec) => spec[3] === name)[0].slice(2, 4);
      const row = target.charCodeAt(1) - 97, col = 9 - Number(target[0]);
      const cx = ((flip ? 8 - col : col) + .5) * 100;
      const cy = ((flip ? 8 - row : row) + .5) * 100;
      assert.ok(Math.hypot(x - cx, y - cy) < 4.01, "leader starts at the arrow tip");
      assert.ok(Math.hypot(ex - x, ey - y) < 75, "label remains close to its own destination");
      assert.ok(boxes[i].x >= 0 && boxes[i].y >= 0 && boxes[i].x + boxes[i].w <= 900 && boxes[i].y + boxes[i].h <= 900);
      for (let j = i + 1; j < boxes.length; j++) assert.ok(!layout.boxesOverlap(boxes[i], boxes[j]));
    }
  }
});

test("crowded edge and shared destinations retain visible, distinct labels", () => {
  for (const flip of [false, true]) for (const width of [320, 900]) {
    const moves = ["2c1a+", "3b1a+", "1c1a+", "1b1a+", "2a1a+"];
    const { svg, boxes } = renderOverlay(moves.map((move, i) =>
      [move, i ? "best sub" : "best", i ? .6 : 1, `候補${i + 1}`, { text: "+35281", promo: "成" }, false]), { width, flip });
    assert.equal(svg.querySelectorAll(".label-link").length, 5);
    for (let i = 0; i < boxes.length; i++) {
      const b = boxes[i];
      assert.ok(b.x >= 0 && b.y >= 0 && b.x + b.w <= 900 && b.y + b.h <= 900);
      for (let j = i + 1; j < boxes.length; j++) assert.ok(!layout.boxesOverlap(b, boxes[j]));
    }
  }
});
