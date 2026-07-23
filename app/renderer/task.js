// Task window — the work scenes and publishes of one entity task.

const context = queryParams(); // {project, kind, entity, task}

document.getElementById("context-label").textContent =
  `${context.project} · ${context.kind} ${context.entity}`;
document.getElementById("task-title").textContent =
  `${context.entity} / ${context.task}`;
document.title = `FIVEHUB — ${context.entity} / ${context.task}`;

function padVersion(version) {
  return "V" + String(version).padStart(3, "0");
}

function scenesTable(scenes) {
  if (!scenes.length) return el("div", "label", "NO SCENES SAVED YET");
  const table = el("table");
  const head = el("thead");
  const headRow = el("tr");
  for (const column of ["VERSION", "USER", "SAVED", "NOTES", ""]) {
    headRow.appendChild(el("th", null, column));
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = el("tbody");
  for (const scene of scenes) {
    const row = el("tr");
    row.appendChild(el("td", null, padVersion(scene.version)));
    row.appendChild(el("td", null, scene.user || "—"));
    row.appendChild(el("td", null, shortDate(scene.created_at)));
    row.appendChild(el("td", null, scene.notes || "—"));
    const actions = el("td", "row-actions");
    const openBtn = el("button", "btn solid", "OPEN IN HOUDINI");
    openBtn.prepend(houdiniGlyph());
    openBtn.addEventListener("click", async () => {
      try {
        toast("OPENING " + padVersion(scene.version) + " IN HOUDINI…");
        await window.fivehub.openScene(scene.file);
      } catch (error) {
        toast(cliErrorText(error).toUpperCase());
      }
    });
    actions.appendChild(openBtn);
    const copyBtn = el("button", "btn", "COPY PATH");
    copyBtn.addEventListener("click", async () => {
      await window.fivehub.copy(scene.file);
      toast("SCENE PATH COPIED");
    });
    actions.appendChild(copyBtn);
    row.appendChild(actions);
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

function publishesTable(publishes) {
  if (!publishes.length) return el("div", "label", "NOTHING PUBLISHED YET");
  const table = el("table");
  const head = el("thead");
  const headRow = el("tr");
  for (const column of ["FORMAT", "VERSION", "VARIANT", "STATUS", "COMMENT", ""]) {
    headRow.appendChild(el("th", null, column));
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = el("tbody");
  for (const publish of publishes) {
    const row = el("tr");
    row.appendChild(el("td", null, (publish.format || "").toUpperCase()));
    row.appendChild(el("td", null, publish.version ? padVersion(publish.version) : "—"));
    row.appendChild(el("td", null, publish.variant || "—"));

    const statusCell = el("td");
    statusCell.appendChild(
      el(
        "span",
        publish.passed ? "status-pass" : "status-fail",
        publish.passed ? "PASS" : "FAIL",
      ),
    );
    row.appendChild(statusCell);
    row.appendChild(el("td", null, publish.comment || "—"));

    const actions = el("td", "row-actions");
    if (publish.report_path) {
      const reportBtn = el("button", "btn", "REPORT");
      reportBtn.addEventListener("click", () =>
        window.fivehub.openReport(publish.report_path),
      );
      actions.appendChild(reportBtn);
    }
    if (publish.version) {
      const sendBtn = el("button", "btn", "SEND");
      sendBtn.addEventListener("click", async () => {
        try {
          await window.fivehub.send(context, publish.format, publish.version);
          toast(`${padVersion(publish.version)} STAGED — USE IMPORT IN HOUDINI`);
        } catch (error) {
          toast("SEND FAILED");
        }
      });
      actions.appendChild(sendBtn);
      if (publish.path) {
        const copyBtn = el("button", "btn", "COPY");
        copyBtn.addEventListener("click", async () => {
          await window.fivehub.copy(publish.path);
          toast("PUBLISH PATH COPIED");
        });
        actions.appendChild(copyBtn);
      }
    }
    row.appendChild(actions);
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

async function load() {
  const scenesBox = document.getElementById("scenes");
  const publishesBox = document.getElementById("publishes");
  try {
    const info = await window.fivehub.taskInfo(context);
    clear(scenesBox);
    scenesBox.appendChild(scenesTable(info.scenes));
    clear(publishesBox);
    publishesBox.appendChild(publishesTable(info.publishes));
  } catch (error) {
    showError(scenesBox, error);
  }
}

load();
