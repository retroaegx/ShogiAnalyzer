export function wireShareDialog({ els, getPayload, showDialog, toast }) {
  let shareBlob = null;
  let shareUrl = ""; // the link X / Bluesky show as a card with the picture ("" = no public address)
  let shareSeq = 0;

  const canShareFiles = () => {
    try {
      return Boolean(navigator.canShare?.({ files: [new File([""], "a.webp", { type: "image/webp" })] }));
    } catch {
      return false;
    }
  };

  async function openShare() {
    const payload = getPayload();
    if (!payload) return;
    const seq = ++shareSeq;
    shareBlob = null;
    shareUrl = "";
    els.shareImg.hidden = true;
    els.shareStatus.hidden = false;
    els.shareStatus.textContent = "画像を作成しています…";
    els.shareText.value = [payload.title, payload.eval].filter(Boolean).join("　");
    els.shareNative.hidden = !canShareFiles();
    els.shareCopy.hidden = !canCopyImage();
    els.shareNote.hidden = true;
    for (const b of [els.shareSave, els.shareCopy, els.shareNative, els.shareX, els.shareBsky]) b.disabled = true;
    showDialog(els.dlgShare);
    try {
      const res = await fetch("/api/share", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const made = await res.json();
      const img = await fetch(made.image, { cache: "no-store" });
      if (!img.ok) throw new Error(`HTTP ${img.status}`);
      const blob = await img.blob();
      if (seq !== shareSeq) return;
      shareBlob = blob;
      // X / Bluesky read the card from the address they are given: the https address this page was
      // opened at, else the fixed public address (.env); from http://localhost or the LAN there is none
      const base = location.protocol === "https:" ? location.origin : made.public_url || "";
      shareUrl = base ? `${base}${made.path}` : "";
      const old = els.shareImg.src;
      els.shareImg.src = URL.createObjectURL(blob);
      if (old.startsWith("blob:")) URL.revokeObjectURL(old);
      els.shareImg.hidden = false;
      els.shareStatus.hidden = true;
      // without password protection the picture can only be saved, not posted
      els.shareSave.disabled = false;
      els.shareCopy.disabled = false;
      for (const b of [els.shareNative, els.shareX, els.shareBsky]) b.disabled = !made.protected;
      els.shareNote.classList.toggle("off", !made.protected);
      els.shareNote.textContent = made.protected
        ? "URL を公開したくない場合は、X・Bluesky に投稿するときに URL リンクを消してください。画像は「画像をコピー」後に貼り付けられます。"
        : `パスワード保護が無効のため共有できません（画像の${canCopyImage() ? "保存・コピー" : "保存"}のみ）。`;
      els.shareNote.hidden = false;
    } catch (e) {
      if (seq === shareSeq) els.shareStatus.textContent = `画像を作成できませんでした（${e.message || e}）`;
    }
  }

  function shareFileName() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `shogi_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.webp`;
  }

  function saveShareImage() {
    if (!shareBlob) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(shareBlob);
    a.download = shareFileName();
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  }

  async function pngOf(blob) {
    const bmp = await createImageBitmap(blob);
    const canvas = document.createElement("canvas");
    canvas.width = bmp.width;
    canvas.height = bmp.height;
    canvas.getContext("2d").drawImage(bmp, 0, 0);
    bmp.close();
    return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("png"))), "image/png"));
  }

  // writing a picture to the clipboard: https or localhost only
  const canCopyImage = () => window.isSecureContext && Boolean(navigator.clipboard?.write) && typeof ClipboardItem !== "undefined";

  async function copyShareImage() {
    if (!canCopyImage()) return false;
    try {
      // the clipboard takes PNG only: the WebP is converted in the browser (given as a promise, so
      // Safari still sees the write inside the click)
      await navigator.clipboard.write([new ClipboardItem({ "image/png": pngOf(shareBlob) })]);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Open the site's post screen with the text and the share link; the site shows the picture as the
   * link's card. Without a public address the picture goes in through the clipboard (or a saved file).
   */
  async function postShare(site) {
    if (!shareBlob) return;
    const text = els.shareText.value.trim();
    if (shareUrl) {
      const url = site === "x"
        ? `https://x.com/intent/post?text=${encodeURIComponent(text)}&url=${encodeURIComponent(shareUrl)}`
        : `https://bsky.app/intent/compose?text=${encodeURIComponent(`${text}\n${shareUrl}`)}`;
      window.open(url, "_blank", "noopener");
      return;
    }
    const copied = await copyShareImage();
    if (!copied) saveShareImage();
    const url = site === "x" ? `https://x.com/intent/post?text=${encodeURIComponent(text)}` : `https://bsky.app/intent/compose?text=${encodeURIComponent(text)}`;
    window.open(url, "_blank", "noopener");
    toast("info", `公開アドレスがないため画像をリンクにできません。${copied ? "画像をコピーしました。投稿画面に貼り付けてください" : "画像を保存しました。投稿画面で添付してください"}`, 7000);
  }

  /** Phone / tablet: the system share sheet, with the picture attached (X / Bluesky apps). */
  async function shareNatively() {
    if (!shareBlob) return;
    try {
      await navigator.share({ files: [new File([shareBlob], shareFileName(), { type: "image/webp" })], text: els.shareText.value.trim() });
    } catch (e) {
      if (e?.name !== "AbortError") toast("error", "共有できませんでした");
    }
  }

    els.shareBtn.addEventListener("click", openShare);
    els.shareSave.addEventListener("click", saveShareImage);
    els.shareCopy.addEventListener("click", async () => {
      if (!shareBlob) return;
      if (await copyShareImage()) toast("info", "画像をコピーしました");
      else toast("error", "画像をコピーできませんでした");
    });
    els.shareNative.addEventListener("click", shareNatively);
    els.shareX.addEventListener("click", () => postShare("x"));
    els.shareBsky.addEventListener("click", () => postShare("bsky"));
}
