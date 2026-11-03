import fs from "node:fs";
import vm from "node:vm";

const moduleText = fs.readFileSync(new URL("../server/assets_web/js/overlayLayout.js", import.meta.url), "utf8");
export const layout = await import(`data:text/javascript;base64,${Buffer.from(moduleText).toString("base64")}`);
const app = fs.readFileSync(new URL("../server/assets_web/js/app.js", import.meta.url), "utf8");
const source = app.slice(app.indexOf('const SVG_NS = '), app.indexOf('/** "成" / "不成"'));
const escape = (text) => String(text).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");

class Element {
  constructor(tag) { this.tag = tag; this.attributes = {}; this.children = []; this.style = {}; this.text = ""; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  get classList() { return { add: (name) => this.setAttribute("class", `${this.attributes.class || ""} ${name}`.trim()) }; }
  set innerHTML(value) { this.children = []; this.text = value; }
  set textContent(value) { this.children = []; this.text = String(value); }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); }
  appendChild(child) {
    if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1);
    this.children.push(child); child.parent = this; return child;
  }
  querySelectorAll(selector) {
    const result = [];
    for (const child of this.children) {
      if (selector.startsWith(".") ? (child.attributes.class || "").split(" ").includes(selector.slice(1)) : child.tag === selector) result.push(child);
      result.push(...child.querySelectorAll(selector));
    }
    return result;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  serialize() {
    const attributes = Object.entries(this.attributes).map(([key, value]) => ` ${key}="${escape(value)}"`).join("");
    return `<${this.tag}${attributes}>${escape(this.text)}${this.children.map((child) => child.serialize()).join("")}</${this.tag}>`;
  }
}

export function renderOverlay(specs, { width = 360, flip = false } = {}) {
  const svg = new Element("svg");
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("viewBox", "0 0 900 900");
  svg.setAttribute("class", "board-overlay");
  svg.getBoundingClientRect = () => ({ width });
  const context = vm.createContext({
    ...layout, suppliedSpecs: specs, svg,
    document: { createElementNS: (_, tag) => new Element(tag) },
    state: { geom: { rw: 900, rh: 900, xs: Array.from({ length: 10 }, (_, i) => i * 100), ys: Array.from({ length: 10 }, (_, i) => i * 100) }, game: {}, flip, parsed: { currentPlayer: "sente" } },
    els: { boardOverlay: svg },
    toView: (row, col) => ({ vr: flip ? 8 - row : row, vc: flip ? 8 - col : col }),
    upsideDown: (owner) => (owner === "gote") !== flip,
    moveTarget: (usi) => {
      const drop = usi.includes("*"); const dest = usi.slice(2, 4);
      return { row: dest.charCodeAt(1) - 97, col: 9 - Number(dest[0]),
        fromRow: drop ? null : usi.charCodeAt(1) - 97, fromCol: drop ? null : 9 - Number(usi[0]) };
    },
    clamp: (value, lo, hi) => Math.max(lo, Math.min(value, hi)),
    performance: { now: () => 0 }, window: { matchMedia: () => ({ matches: true }) },
    requestAnimationFrame: () => 0, cancelAnimationFrame: () => {},
  });
  vm.runInContext(source, context);
  vm.runInContext("overlaySpecs = () => suppliedSpecs; renderOverlay(); globalThis.boxes = overlayLabels;", context);
  return { svg, boxes: context.boxes };
}

export function candidates(pieces = "PSG", square = "5e") {
  return [...pieces].map((piece, i) => [`${piece}*${square}`, i ? "best sub" : "best", i ? .6 : 1,
    i ? `候補${i + 1}` : "候補手", { text: `+${320 - i * 90}`, cls: "plus", promo: "" }, false]);
}
