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
function openSheet({ title, submitLabel, build, allowCancel = true }) {
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
    const submitBtn = el("button", "btn solid", submitLabel);
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
