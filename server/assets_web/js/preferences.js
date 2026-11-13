import { UI_THEMES } from "/js/theme_catalog.js";
import { lsGet, lsSet } from "/js/storage.js";
import { THEME_LS_KEYS } from "/js/vendor/themeLoader.js";

const LS_OPTS = "shogi_analyzer_view_opts";
export const LS_BATCH_SECONDS = "shogi_analyzer_batch_seconds";

export function createPreferences() {
  const options = {
    theme: UI_THEMES[0].id,
    coords: "overlay",
    legal: true,
    lastMove: true,
    bestMove: true,
    nextMove: true,
    arrowLabels: true,
  };

  function batchSeconds() {
    const v = Number(lsGet(LS_BATCH_SECONDS));
    return Number.isFinite(v) && v >= 0.5 ? Math.min(v, 120) : 3;
  }

  function loadViewOptions() {
    try {
      const raw = JSON.parse(lsGet(LS_OPTS) || "{}");
      Object.assign(options, raw || {});
    } catch {
      // ignore
    }
    normalizeOpts();
  }

  function normalizeOpts() {
    // The board-side evaluation bar has been removed; discard older saved preferences.
    delete options.evalBar;
    // coordinates used to be on/off: on -> the new default (on the board frame), off -> hidden
    if (options.coords === true) options.coords = "overlay";
    if (options.coords === false) options.coords = "off";
    if (!["overlay", "outside", "off"].includes(options.coords)) options.coords = "overlay";
    // a theme that no longer exists: the default one
    if (!UI_THEMES.some((t) => t.id === options.theme)) options.theme = UI_THEMES[0].id;
  }

  function saveViewOptions() {
    lsSet(LS_OPTS, JSON.stringify(options));
    pushSettings({ view: { ...options } });
  }

  // ---------- settings kept on the server ----------
  // Display options, board / piece set and the 全解析 time live on the server, so every browser and
  // device shows the same. localStorage keeps a copy only for the first paint before the fetch.
  let serverSettingsJson = "";
  let settingsPending = {};
  let settingsTimer = null;
  let sending = false;
  let localRevision = 0;

  function currentSettings() {
    const out = { view: { ...options }, batch_seconds: batchSeconds() };
    const board = lsGet(THEME_LS_KEYS.backgroundSet);
    const pieces = lsGet(THEME_LS_KEYS.pieceSet);
    if (board) out.board_set = board;
    if (pieces) out.piece_set = pieces;
    return out;
  }

  /** This browser has settings of its own (not just the defaults). */
  function hasLocalSettings() {
    return [LS_OPTS, LS_BATCH_SECONDS, THEME_LS_KEYS.backgroundSet, THEME_LS_KEYS.pieceSet].some((k) => lsGet(k));
  }

  function pushSettings(patch) {
    localRevision++;
    Object.assign(settingsPending, patch);
    scheduleSave();
  }

  function scheduleSave() {
    clearTimeout(settingsTimer);
    settingsTimer = setTimeout(savePending, 250);
  }

  async function savePending() {
    if (sending || !Object.keys(settingsPending).length) return;
    const body = settingsPending;
    settingsPending = {};
    sending = true;
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: body }),
      });
      if (!res.ok) throw new Error(`Settings save failed (${res.status})`);
      serverSettingsJson = JSON.stringify((await res.json()).settings || {});
      if (Object.keys(settingsPending).length) scheduleSave();
    } catch {
      // Retry with the next change or reconnect. Newer local changes take precedence.
      settingsPending = { ...body, ...settingsPending };
    } finally {
      sending = false;
    }
  }

  /** Take the server's settings into this page. Returns true when something changed. */
  function applySettings(s) {
    const before = JSON.stringify(currentSettings());
    if (s.view && typeof s.view === "object") {
      Object.assign(options, s.view);
      normalizeOpts();
      lsSet(LS_OPTS, JSON.stringify(options));
    }
    if (Number(s.batch_seconds) >= 0.5) lsSet(LS_BATCH_SECONDS, String(s.batch_seconds));
    if (s.board_set) lsSet(THEME_LS_KEYS.backgroundSet, s.board_set);
    if (s.piece_set) lsSet(THEME_LS_KEYS.pieceSet, s.piece_set);
    return JSON.stringify(currentSettings()) !== before;
  }

  /** Read the shared settings. The very first time (nothing stored yet) this browser's become the shared ones. */
  async function fetchServerSettings() {
    if (sending || Object.keys(settingsPending).length) {
      scheduleSave();
      return false;
    }
    const revisionAtRead = localRevision;
    try {
      const res = await fetch("/api/settings", { cache: "no-store" });
      if (!res.ok) return false;
      const json = await res.json();
      if (revisionAtRead !== localRevision) return false;
      if (!json.exists) {
        // nothing shared yet: a browser with its own settings (e.g. the one used so far) provides them
        if (hasLocalSettings()) pushSettings(currentSettings());
        return false;
      }
      const text = JSON.stringify(json.settings || {});
      if (text === serverSettingsJson) return false;
      serverSettingsJson = text;
      return applySettings(json.settings || {});
    } catch {
      return false; // server unreachable: keep this browser's copy
    }
  }

  return { options, loadViewOptions, saveViewOptions, batchSeconds, currentSettings, pushSettings, fetchServerSettings };
}
