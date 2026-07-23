// Shared renderer helpers. All dynamic content goes through element
// creation + textContent — hub data never touches innerHTML.

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function queryParams() {
  return Object.fromEntries(new URLSearchParams(window.location.search));
}

// In-place navigation — browsing happens in ONE window, never a new one.
function go(page, params) {
  const query = new URLSearchParams(params || {}).toString();
  window.location.href = page + (query ? "?" + query : "");
}

function shortDate(iso) {
  return (iso || "").replace("T", " ").replace("Z", "").slice(0, 16);
}

let toastTimer = null;
function toast(message) {
  let node = document.getElementById("toast");
  if (!node) {
    node = el("div");
    node.id = "toast";
    document.body.appendChild(node);
  }
  node.textContent = message;
  requestAnimationFrame(() => node.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), 2600);
}

function showError(container, error) {
  clear(container);
  const box = el("div", "error-state");
  box.appendChild(el("div", "label", "SOMETHING BROKE"));
  box.appendChild(el("p", "mono", String(error?.message || error)));
  container.appendChild(box);
}

function cliErrorText(error) {
  return String(error?.message || error).replace(/^Error[:] ?/i, "");
}

// Monochrome Houdini-style swirl glyph for "open in Houdini" actions.
// Constant markup only — never mixed with hub data.
function houdiniGlyph() {
  const span = el("span", "glyph");
  span.innerHTML =
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path d="M12 3a9 9 0 1 0 9 9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>' +
    '<path d="M12 7.2a4.8 4.8 0 1 0 4.8 4.8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>' +
    '<circle cx="12" cy="12" r="1.7" fill="currentColor"/>' +
    "</svg>";
  return span;
}

// Modal sheet. `build(body)` fills the form and returns a collect function:
// return the values object to submit, or null to block (missing input).
// Resolves with the values, or null when dismissed (unless allowCancel:false).
function openSheet({ title, submitLabel, build, allowCancel = true, danger = false }) {
  return new Promise((resolve) => {
    const overlay = el("div", "overlay");
    const sheet = el("div", "sheet");
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-modal", "true");

    sheet.appendChild(el("div", "sheet-title", title));
    const body = el("div", "sheet-body");
    sheet.appendChild(body);
    const collect = build(body);

    const footer = el("div", "sheet-footer");
    const close = (value) => {
      overlay.classList.remove("show");
      document.removeEventListener("keydown", onKey);
      setTimeout(() => overlay.remove(), 260);
      resolve(value);
    };
    const submit = () => {
      const values = collect();
      if (values) close(values);
    };
    const onKey = (event) => {
      if (event.key === "Escape" && allowCancel) close(null);
      if (event.key === "Enter" && event.target.tagName === "INPUT") submit();
    };

    if (allowCancel) {
      const cancelBtn = el("button", "btn", "CANCEL");
      cancelBtn.addEventListener("click", () => close(null));
      footer.appendChild(cancelBtn);
      overlay.addEventListener("click", (event) => {
        if (event.target === overlay) close(null);
      });
    }
    const submitBtn = el("button", danger ? "btn danger" : "btn solid", submitLabel);
    submitBtn.addEventListener("click", submit);
    footer.appendChild(submitBtn);
    sheet.appendChild(footer);

    document.addEventListener("keydown", onKey);
    overlay.appendChild(sheet);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("show"));
    const first = body.querySelector("input");
    if (first) first.focus();
  });
}

function sheetField(body, labelText) {
  const field = el("div", "sheet-field");
  field.appendChild(el("span", "label", labelText));
  body.appendChild(field);
  return field;
}

// Destructive confirmation: same sheet, red confirm button.
function confirmSheet(title, message, confirmLabel) {
  return openSheet({
    title,
    submitLabel: confirmLabel || "DELETE",
    danger: true,
    build(body) {
      body.appendChild(el("p", "mono", message));
      return () => ({ confirmed: true });
    },
  });
}

// -- overflow (three-dots) menus ----------------------------------------

let activeMenu = null;

function closeMenu() {
  if (!activeMenu) return;
  activeMenu.remove();
  activeMenu = null;
  document.removeEventListener("click", closeMenu, true);
  document.removeEventListener("keydown", menuKey, true);
}

function menuKey(event) {
  if (event.key === "Escape") closeMenu();
}

function openMenu(anchor, items) {
  closeMenu();
  const menu = el("div", "menu");
  menu.setAttribute("role", "menu");
  for (const item of items) {
    if (item === "-") {
      menu.appendChild(el("div", "menu-sep"));
      continue;
    }
    const row = el("button", "menu-item" + (item.danger ? " danger" : ""), item.label);
    row.setAttribute("role", "menuitem");
    row.addEventListener("click", (event) => {
      event.stopPropagation();
      closeMenu();
      item.action();
    });
    menu.appendChild(row);
  }
  document.body.appendChild(menu);
  const rect = anchor.getBoundingClientRect();
  const size = menu.getBoundingClientRect();
  menu.style.top =
    Math.min(rect.bottom + 6, window.innerHeight - size.height - 12) + "px";
  menu.style.left =
    Math.max(12, Math.min(rect.right - size.width, window.innerWidth - size.width - 12)) +
    "px";
  activeMenu = menu;
  setTimeout(() => {
    document.addEventListener("click", closeMenu, true);
    document.addEventListener("keydown", menuKey, true);
  }, 0);
}

// Periodic reload so windows follow other artists' work — paused while a
// sheet or menu is open so it never yanks input away.
function autoRefresh(reload, ms) {
  setInterval(() => {
    if (document.querySelector(".overlay, .menu")) return;
    reload();
  }, ms || 30000);
}

// A ⋯ button. `itemsFactory` is called on open so labels/actions stay fresh.
function dotsButton(itemsFactory) {
  const button = el("button", "btn icon dots", "⋯");
  button.title = "More";
  button.setAttribute("aria-label", "More options");
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    openMenu(button, itemsFactory());
  });
  return button;
}
