import assert from "node:assert/strict";
import test from "node:test";
import { candidates, layout, renderOverlay } from "./overlay_harness.mjs";

test("different pieces on the same square become one marker and one row per move", () => {
  const grouped = layout.groupDropSpecs(candidates());
  assert.equal(grouped.length, 1);
  assert.deepEqual(grouped[0].rows.map((row) => row.text), ["候補1 歩打", "候補2 銀打", "候補3 金打"]);
  const { svg, boxes } = renderOverlay(candidates());
  assert.equal(svg.querySelectorAll(".mk").length, 1);
  assert.equal(svg.querySelectorAll(".mv-label").length, 3);
  assert.equal(boxes.length, 1);
  assert.match(svg.textContent, /候補1 歩打\+320/);
});

test("one drop that is also the played move retains its existing animation representation", () => {
  const move = candidates("P")[0];
  const specs = [[move[0], "next", 1, "", null, true], [...move.slice(0, 3), "指・候1", move[4], true]];
  assert.equal(layout.groupDropSpecs(specs).length, 2);
  assert.ok(layout.groupDropSpecs(specs).every((unit) => !unit.rows));
});

test("played-move duplicates in a list have one row and keep their combined label", () => {
  const specs = candidates("PSG");
  specs[0][3] = "指・候1";
  specs.unshift(["P*5e", "next", 1, "", null, true]);
  const [group] = layout.groupDropSpecs(specs);
  assert.equal(group.rows.length, 3);
  assert.equal(group.rows[0].text, "指・候1 歩打");
});

test("seven drop types fit at every corner on mobile, desktop and a flipped board", () => {
  for (const square of ["1a", "9a", "1i", "9i", "5e"]) for (const width of [320, 390, 900]) for (const flip of [false, true]) {
    const { svg, boxes } = renderOverlay(candidates("PLNSGBR", square), { width, flip });
    assert.equal(svg.querySelectorAll(".mk").length, 1);
    assert.equal(svg.querySelectorAll(".mv-label").length, 7);
    for (const box of boxes) {
      assert.ok(box.x >= 0 && box.y >= 0 && box.x + box.w <= 900.001 && box.y + box.h <= 900.001);
      const col = 9 - Number(square[0]), row = square.charCodeAt(1) - 97;
      const centerX = ((flip ? 8 - col : col) + .5) * 100;
      const centerY = ((flip ? 8 - row : row) + .5) * 100;
      assert.ok(!layout.boxesOverlap(box, { x: centerX - 34, y: centerY - 34, w: 68, h: 68 }));
    }
    const rows = svg.querySelectorAll(".mv-label").map((g) => g.children[0].attributes);
    for (let i = 1; i < rows.length; i++) assert.ok(Number(rows[i].y) > Number(rows[i - 1].y) + Number(rows[i - 1].height));
  }
});

test("two nearby groups and a normal move never share label space", () => {
  for (const square of ["1a", "5e", "9i"]) for (const flip of [false, true]) {
    const specs = [...candidates("PSG", square), ...candidates("LN", square === "9i" ? "8i" : "2b"),
      ["5f5e", "best sub", .6, "候補5", { text: "+50", cls: "plus" }, false]];
    const { boxes } = renderOverlay(specs, { width: 320, flip });
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) assert.ok(!layout.boxesOverlap(boxes[i], boxes[j]));
  }
});

test("hidden arrow labels still identify each dropped piece", () => {
  const specs = candidates("PSG").map((spec) => { spec[3] = ""; return spec; });
  const { svg } = renderOverlay(specs);
  for (const name of ["歩打", "銀打", "金打"]) assert.ok(svg.textContent.includes(name));
});
