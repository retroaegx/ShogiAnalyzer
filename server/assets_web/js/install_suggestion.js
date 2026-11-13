import { icon } from "/js/icons.js";

// Chrome / Edge (Android) announce that the app can be installed; keep the event for our own button.
// Registered at load time: the event can fire before the rest of the page is set up.
let installEvent = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvent = e;
});

const LS_INSTALL = "shogi_analyzer_install_prompt"; // "never" or the time (ms) until which it stays hidden

function installHelp() {
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const android = /Android/.test(ua);
  if (ios) {
    if (/CriOS/.test(ua)) return `アドレスバー右の <b>共有ボタン</b> <span data-share-icon></span> →「<b>ホーム画面に追加</b>」で、アイコンからアプリのように開けます。`;
    if (/FxiOS|EdgiOS/.test(ua)) return `メニューの <b>共有</b> <span data-share-icon></span> →「<b>ホーム画面に追加</b>」で、アイコンからアプリのように開けます。`;
    return `<b>共有ボタン</b> <span data-share-icon></span>（「…」の中にある場合も）→「<b>ホーム画面に追加</b>」で、アイコンからアプリのように開けます。`;
  }
  if (android && /Firefox/.test(ua)) return "メニュー <b>⋮</b> →「<b>インストール</b>」（または「ホーム画面に追加」）で、アイコンからアプリのように開けます。";
  return null; // Android Chrome / Edge: handled with the install button
}

export function setupInstallSuggestion({ isDialogOpen, lsGet, lsSet }) {
  const $ = (id) => document.getElementById(id);
  const card = $("installCard");
  const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const phoneLike = window.matchMedia("(pointer: coarse)").matches && /Android|iPhone|iPad|iPod/.test(navigator.userAgent + (navigator.maxTouchPoints > 1 ? " iPad" : ""));
  const saved = lsGet(LS_INSTALL);
  if (standalone || !phoneLike || !window.isSecureContext || saved === "never" || Number(saved) > Date.now()) return;
  const hide = () => (card.hidden = true);
  $("installLater").addEventListener("click", () => {
    lsSet(LS_INSTALL, String(Date.now() + 14 * 24 * 3600 * 1000));
    hide();
  });
  $("installNever").addEventListener("click", () => {
    lsSet(LS_INSTALL, "never");
    hide();
  });
  $("installGo").addEventListener("click", async () => {
    if (!installEvent) return hide();
    installEvent.prompt();
    const choice = await installEvent.userChoice.catch(() => null);
    installEvent = null;
    if (choice?.outcome !== "accepted") lsSet(LS_INSTALL, String(Date.now() + 14 * 24 * 3600 * 1000));
    hide();
  });
  window.addEventListener("appinstalled", hide);
  // a few seconds after opening, so it does not get in the way right away; never on top of a dialog
  const show = () => {
    if (isDialogOpen()) return void setTimeout(show, 3000);
    if (installEvent) {
      $("installBody").textContent = "ホーム画面に追加すると、アイコンからアプリのように開けます。";
      $("installGo").hidden = false;
    } else {
      const help = installHelp();
      if (!help) return; // the browser does not offer installing (yet): say nothing
      const body = $("installBody");
      body.innerHTML = help; // installHelp returns only static messages.
      body.querySelector("[data-share-icon]")?.replaceWith(icon("system-share", "ico share-ico"));
    }
    card.hidden = false;
  };
  setTimeout(show, 6000);
}
