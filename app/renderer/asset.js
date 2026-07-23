// Asset window — one per asset. Versions, variants, actions, reports.

const detail = document.getElementById("detail");
const { name } = queryParams();

function actionRow(asset) {
  const row = el("div", "row");

  const send = el("button", "btn solid", "SEND TO HOUDINI");
  send.addEventListener("click", async () => {
    try {
      await window.fivehub.send(asset.name);
      toast("STAGED — USE THE IMPORT SHELF TOOL IN HOUDINI");
    } catch (error) {
      toast("SEND FAILED");
    }
  });
  row.appendChild(send);

  const copy = el("button", "btn", "COPY USD PATH");
  copy.addEventListener("click", async () => {
    await window.fivehub.copy(asset.root_layer);
    toast("PATH COPIED");
  });
  row.appendChild(copy);

  const reveal = el("button", "btn", "REVEAL FILES");
  reveal.addEventListener("click", () => window.fivehub.reveal(asset.root_layer));
  row.appendChild(reveal);

  return row;
}

function versionsTable(asset) {
  const table = el("table");
  const head = el("thead");
  const headRow = el("tr");
  for (const columnName of ["VERSION", "VARIANT", "PUBLISHED", "COMMENT", ""]) {
    headRow.appendChild(el("th", null, columnName));
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = el("tbody");
  for (const version of asset.versions) {
    const row = el("tr");
    row.appendChild(el("td", null, "V" + String(version.version).padStart(3, "0")));
    row.appendChild(el("td", null, version.variant));
    row.appendChild(el("td", null, shortDate(version.created_at)));
    row.appendChild(el("td", null, version.comment || "—"));

    const actions = el("td");
    if (version.report_path) {
      const reportBtn = el("button", "btn", "REPORT");
      reportBtn.addEventListener("click", () =>
        window.fivehub.openReport({ name: asset.name, version: String(version.version) }),
      );
      actions.appendChild(reportBtn);
    }
    const sendBtn = el("button", "btn", "SEND");
    sendBtn.style.marginLeft = "8px";
    sendBtn.addEventListener("click", async () => {
      await window.fivehub.send(asset.name, version.version);
      toast("V" + String(version.version).padStart(3, "0") + " STAGED FOR HOUDINI");
    });
    actions.appendChild(sendBtn);
    row.appendChild(actions);
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

async function load() {
  try {
    const { asset } = await window.fivehub.show(name);
    document.title = "FIVEHUB — " + asset.name;
    document.getElementById("project").textContent = asset.project || "NO PROJECT";
    document.getElementById("root-layer").textContent = asset.root_layer;

    clear(detail);
    detail.appendChild(el("h1", "title", asset.name));

    const variants = Object.keys(asset.variants || {}).sort();
    const meta = el("div", "row");
    meta.appendChild(el("span", "label", asset.versions.length + " VERSION(S)"));
    meta.appendChild(el("span", "label", "VARIANTS: " + (variants.join(" / ") || "—")));
    detail.appendChild(meta);

    detail.appendChild(actionRow(asset));
    detail.appendChild(el("hr", "divider"));
    detail.appendChild(versionsTable(asset));
  } catch (error) {
    showError(detail, error);
  }
}

load();
