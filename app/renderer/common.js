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
