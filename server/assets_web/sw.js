// Service worker for installing ShogiAnalyzer as an app (PWA).
// Nothing is cached: the app always talks to the live server. When the server cannot be
// reached, page loads get a short offline notice instead of the browser's error page.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

const OFFLINE_HTML = `<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ShogiAnalyzer</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0c0f;color:#eceef2;
font-family:system-ui,sans-serif;text-align:center;padding:24px}img{width:96px;height:96px;border-radius:22px}
p{color:#9aa1ad;line-height:1.7}button{margin-top:8px;height:42px;padding:0 20px;border:0;border-radius:10px;
background:#e3b25a;color:#1b1405;font-weight:700;font-size:15px}</style></head><body><div>
<img src="/icons/icon-192.png?v=2" alt=""><h2>サーバーに接続できません</h2>
<p>ShogiAnalyzer が起動しているか、ネットワークを確認してください。</p>
<button onclick="location.reload()">再読み込み</button></div></body></html>`;

self.addEventListener("fetch", (event) => {
  if (event.request.mode !== "navigate") return; // API, scripts, images: straight to the network
  event.respondWith(
    fetch(event.request).catch(
      () => new Response(OFFLINE_HTML, { status: 503, headers: { "Content-Type": "text/html; charset=utf-8" } }),
    ),
  );
});
