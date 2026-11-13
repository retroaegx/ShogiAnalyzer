const SVG_NS = "http://www.w3.org/2000/svg";
const ICON_SPRITE = "/icons/ui.svg";

export function icon(name, className = "ico") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", className);
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `${ICON_SPRITE}#i-${name}`);
  svg.append(use);
  return svg;
}
