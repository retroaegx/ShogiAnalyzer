import assert from "node:assert/strict";
import test from "node:test";
import { moduleUrl } from "./browser_modules.mjs";

const { createPreferences } = await import(moduleUrl("preferences.js"));

test("a failed save cannot replace a newer preference when reconnecting", async (t) => {
  const data = new Map();
  const originalStorage = globalThis.localStorage;
  const originalFetch = globalThis.fetch;
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) },
  });
  t.after(() => {
    if (originalStorage === undefined) delete globalThis.localStorage;
    else Object.defineProperty(globalThis, "localStorage", { configurable: true, value: originalStorage });
    globalThis.fetch = originalFetch;
  });
  t.mock.timers.enable({ apis: ["setTimeout"] });

  let rejectFirstSave;
  const saved = [];
  globalThis.fetch = async (url, request) => {
    assert.equal(url, "/api/settings");
    assert.equal(request.method, "PUT");
    const { settings } = JSON.parse(request.body);
    saved.push(settings);
    if (saved.length === 1) return new Promise((_, reject) => { rejectFirstSave = reject; });
    return { ok: true, json: async () => ({ settings }) };
  };

  const preferences = createPreferences();
  preferences.options.coords = "outside";
  preferences.saveViewOptions();
  t.mock.timers.tick(250);
  preferences.options.coords = "off";
  preferences.saveViewOptions();
  t.mock.timers.tick(250);
  assert.equal(saved.length, 1);

  rejectFirstSave(new Error("Offline"));
  await new Promise(setImmediate);
  await preferences.fetchServerSettings();
  t.mock.timers.tick(250);
  await new Promise(setImmediate);
  assert.deepEqual(saved.map(({ view }) => view.coords), ["outside", "off"]);
});
