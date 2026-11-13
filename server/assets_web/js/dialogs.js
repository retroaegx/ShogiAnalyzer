export function createDialogs(els, el) {
  let openDialogEl = null;
  let dialogResolve = null;

  function showDialog(dlg) {
    closeDialog(null);
    els.dialogHost.hidden = false;
    dlg.hidden = false;
    openDialogEl = dlg;
    const focusable = dlg.querySelector("input:not([hidden]), textarea, .btn.primary, button");
    if (focusable) setTimeout(() => {
      if (openDialogEl === dlg) focusable.focus();
    }, 30);
  }

  function closeDialog(value) {
    if (openDialogEl) openDialogEl.hidden = true;
    openDialogEl = null;
    els.dialogHost.hidden = true;
    if (dialogResolve) {
      const r = dialogResolve;
      dialogResolve = null;
      r(value);
    }
  }

  /** actions: [{label, value, primary?, img?}] -> resolves with value (null on dismiss). */
  function confirmDialog({ title, message, extra, actions }) {
    els.dlgConfirmTitle.textContent = title || "";
    els.dlgConfirmMsg.textContent = message || "";
    els.dlgConfirmMsg.hidden = !message;
    els.dlgConfirmExtra.replaceChildren(...(extra ? [extra] : []));
    els.dlgConfirmExtra.hidden = !extra;
    els.dlgConfirmActions.innerHTML = "";
    for (const a of actions || [{ label: "OK", value: true, primary: true }]) {
      const b = el("button", `btn${a.primary ? " primary" : ""}${a.danger ? " danger" : ""}${a.img ? " piece-choice" : ""}`);
      b.type = "button";
      if (a.img) {
        const img = el("img");
        img.src = a.img;
        img.alt = "";
        b.appendChild(img);
      }
      b.appendChild(el("span", null, a.label));
      b.addEventListener("click", () => closeDialog(a.value));
      els.dlgConfirmActions.appendChild(b);
    }
    showDialog(els.dlgConfirm);
    return new Promise((resolve) => {
      dialogResolve = resolve;
    });
  }

  els.dialogHost.addEventListener("click", (event) => {
    if (event.target.closest("[data-close]")) closeDialog(null);
  });

  return { showDialog, closeDialog, confirmDialog, isDialogOpen: () => openDialogEl !== null };
}
