// Apply incoming data immediately, but paint at most once per animation frame.
export function coalesceFrame(paint, requestFrame = requestAnimationFrame) {
  let scheduled = false;
  return () => {
    if (scheduled) return;
    scheduled = true;
    requestFrame(() => { scheduled = false; paint(); });
  };
}
