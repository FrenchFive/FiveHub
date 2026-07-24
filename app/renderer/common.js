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

// Full-screen image inspector — click anywhere or Escape to close.
function openLightbox(src, alt) {
  const overlay = el("div", "overlay lightbox");
  const img = el("img", "lightbox-image");
  img.src = src;
  img.alt = alt || "";
  overlay.appendChild(img);
  const onKey = (event) => {
    if (event.key === "Escape") close();
  };
  const close = () => {
    overlay.classList.remove("show");
    document.removeEventListener("keydown", onKey);
    setTimeout(() => overlay.remove(), 260);
  };
  overlay.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add("show"));
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

// Lucide icons (lucide.dev, ISC license) inlined as constant markup —
// the strict CSP allows no CDN, and hub data never touches innerHTML.
const LUCIDE = {
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  "chevron-left": '<path d="m15 18-6-6 6-6"/>',
  "chevron-right": '<path d="m9 18 6-6-6-6"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  ellipsis:
    '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>' +
    '<circle cx="5" cy="12" r="1"/>',
  box:
    '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>' +
    '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  clapperboard:
    '<path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/>' +
    '<path d="m6.2 5.3 3.1 3.9"/><path d="m12.4 3.4 3.1 4"/>' +
    '<path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  image:
    '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>' +
    '<circle cx="9" cy="9" r="2"/>' +
    '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
  activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  file:
    '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>' +
    '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
  "file-text":
    '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>' +
    '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/>' +
    '<path d="M16 13H8"/><path d="M16 17H8"/>',
  cpu:
    '<rect width="16" height="16" x="4" y="4" rx="2"/>' +
    '<rect width="6" height="6" x="9" y="9" rx="1"/>' +
    '<path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/>' +
    '<path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/>' +
    '<path d="M9 2v2"/><path d="M9 20v2"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  download:
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
    '<polyline points="7 10 12 15 17 10"/>' +
    '<line x1="12" x2="12" y1="15" y2="3"/>',
  upload:
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
    '<polyline points="17 8 12 3 7 8"/>' +
    '<line x1="12" x2="12" y1="3" y2="15"/>',
  "list-checks":
    '<path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/>' +
    '<path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
  folder:
    '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
};

function icon(name) {
  const span = el("span", "ic");
  span.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true">' + (LUCIDE[name] || "") + "</svg>";
  return span;
}

// Prepend the Lucide icon named by data-icon to static markup, once.
function applyIcons(root) {
  for (const node of (root || document).querySelectorAll("[data-icon]")) {
    if (node.dataset.iconApplied) continue;
    node.dataset.iconApplied = "1";
    node.insertBefore(icon(node.dataset.icon), node.firstChild);
  }
}

// Replace a button's content with icon + label (for dynamic labels).
function setButtonLabel(button, iconName, text) {
  clear(button);
  if (iconName) button.appendChild(icon(iconName));
  button.appendChild(el("span", null, text));
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
function openSheet({
  title, submitLabel, build, allowCancel = true, danger = false,
  hideCancel = false,
}) {
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
      if (!hideCancel) {
        const cancelBtn = el("button", "btn", "CANCEL");
        cancelBtn.addEventListener("click", () => close(null));
        footer.appendChild(cancelBtn);
      }
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

// -- shared sheets (project + entity pages) ------------------------------

async function taskSheetShared(projectName, kind, entityName, defaultTasks, reload) {
  const values = await openSheet({
    title: `New task on ${entityName}`,
    submitLabel: "CREATE",
    build(body) {
      const nameField = sheetField(body, "TASK NAME");
      const nameInput = el("input");
      nameInput.type = "text";
      nameInput.placeholder = "e.g. modeling";
      nameField.appendChild(nameInput);

      const suggestField = sheetField(body, "SUGGESTIONS");
      const chips = el("div", "chips");
      for (const task of defaultTasks) {
        const chip = el("button", "chip", task);
        chip.addEventListener("click", () => {
          nameInput.value = task;
          nameInput.focus();
        });
        chips.appendChild(chip);
      }
      suggestField.appendChild(chips);

      return () => {
        const name = nameInput.value.trim();
        return name ? { name } : null;
      };
    },
  });
  if (!values) return;
  try {
    await window.fivehub.taskCreate(projectName, kind, entityName, values.name);
    toast("TASK CREATED");
    await reload();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

async function editEntitySheetShared(projectName, kind, entity, reload) {
  const values = await openSheet({
    title: "Edit " + entity.name,
    submitLabel: "SAVE",
    build(body) {
      const sequenceField = sheetField(body, "SEQUENCE");
      const sequenceInput = el("input");
      sequenceInput.type = "text";
      sequenceInput.value = entity.sequence || "";
      sequenceField.appendChild(sequenceInput);

      const rangeField = sheetField(body, "FRAME RANGE");
      const rangeRow = el("div", "form-row");
      const startInput = el("input");
      startInput.type = "text";
      startInput.value = entity.frame_start ?? "";
      const endInput = el("input");
      endInput.type = "text";
      endInput.value = entity.frame_end ?? "";
      rangeRow.appendChild(startInput);
      rangeRow.appendChild(endInput);
      rangeField.appendChild(rangeRow);

      const formatField = sheetField(body, "FPS / RESOLUTION");
      const formatRow = el("div", "form-row");
      const fpsInput = el("input");
      fpsInput.type = "text";
      fpsInput.value = entity.fps ?? "";
      const resXInput = el("input");
      resXInput.type = "text";
      resXInput.value = entity.res_x ?? "";
      const resYInput = el("input");
      resYInput.type = "text";
      resYInput.value = entity.res_y ?? "";
      formatRow.appendChild(fpsInput);
      formatRow.appendChild(resXInput);
      formatRow.appendChild(resYInput);
      formatField.appendChild(formatRow);

      return () => ({
        sequence: sequenceInput.value.trim(),
        frame_start: startInput.value.trim(),
        frame_end: endInput.value.trim(),
        fps: fpsInput.value.trim(),
        res_x: resXInput.value.trim(),
        res_y: resYInput.value.trim(),
      });
    },
  });
  if (!values) return;
  try {
    await window.fivehub.entityUpdate(projectName, kind, entity.name, values);
    toast("METADATA SAVED");
    await reload();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

// A ⋯ button. `itemsFactory` is called on open so labels/actions stay fresh.
function dotsButton(itemsFactory) {
  const button = el("button", "btn icon dots");
  button.appendChild(icon("ellipsis"));
  button.title = "More";
  button.setAttribute("aria-label", "More options");
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    openMenu(button, itemsFactory());
  });
  return button;
}

// Scripts load at the end of <body>, so static markup is ready.
applyIcons();
