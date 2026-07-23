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

async function editSceneNotes(scene) {
  const values = await openSheet({
    title: "Notes for scene " + padVersion(scene.version),
    submitLabel: "SAVE",
    build(body) {
      const field = sheetField(body, "NOTES");
      const input = el("input");
      input.type = "text";
      input.value = scene.notes || "";
      field.appendChild(input);
      return () => ({ notes: input.value.trim() });
    },
  });
  if (!values) return;
  await window.fivehub.sceneNotes(context, scene.version, values.notes);
  toast("NOTES UPDATED");
  load();
}

async function deleteScene(scene) {
  const ok = await confirmSheet(
    "Delete scene " + padVersion(scene.version) + "?",
    "The version entry and its .hip file are removed. This cannot be undone.",
    "DELETE VERSION",
  );
  if (!ok) return;
  try {
    await window.fivehub.sceneDelete(context, scene.version);
    toast(padVersion(scene.version) + " DELETED");
    load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

async function editPublishComment(publish) {
  const values = await openSheet({
    title: "Comment for " + publish.format.toUpperCase() + " " + padVersion(publish.version),
    submitLabel: "SAVE",
    build(body) {
      const field = sheetField(body, "COMMENT");
      const input = el("input");
      input.type = "text";
      input.value = publish.comment || "";
      field.appendChild(input);
      return () => ({ comment: input.value.trim() });
    },
  });
  if (!values) return;
  await window.fivehub.publishComment(
    context, publish.format, publish.version, values.comment,
  );
  toast("COMMENT UPDATED");
  load();
}

async function deletePublish(publish) {
  const label = publish.format.toUpperCase() + " " + padVersion(publish.version);
  const ok = await confirmSheet(
    "Delete publish " + label + "?",
    "The published files of this version are removed and the USD root interface is re-pointed. This cannot be undone.",
    "DELETE VERSION",
  );
  if (!ok) return;
  try {
    await window.fivehub.publishDelete(context, publish.format, publish.version);
    toast(label + " DELETED");
    load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
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

    // Primary action: just the Houdini mark, nothing more.
    const openBtn = el("button", "btn solid icon");
    openBtn.title = "Open " + padVersion(scene.version) + " in Houdini";
    openBtn.setAttribute("aria-label", openBtn.title);
    openBtn.appendChild(houdiniGlyph());
    openBtn.addEventListener("click", async () => {
      try {
        toast("OPENING " + padVersion(scene.version) + " IN HOUDINI…");
        await window.fivehub.openScene(scene.file);
      } catch (error) {
        toast(cliErrorText(error).toUpperCase());
      }
    });
    actions.appendChild(openBtn);

    // Everything else lives behind the dots.
    actions.appendChild(
      dotsButton(() => [
        {
          label: "Copy path",
          action: async () => {
            await window.fivehub.copy(scene.file);
            toast("SCENE PATH COPIED");
          },
        },
        {
          label: "Reveal file",
          action: () => window.fivehub.reveal(scene.file),
        },
        {
          label: "Edit notes",
          action: () => editSceneNotes(scene),
        },
        "-",
        {
          label: "Delete version",
          danger: true,
          action: () => deleteScene(scene),
        },
      ]),
    );
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
  for (const column of [
    "FORMAT", "VERSION", "VARIANT", "STATUS", "BY", "PUBLISHED", "COMMENT", "",
  ]) {
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
    row.appendChild(el("td", null, publish.user || "—"));
    row.appendChild(el("td", null, shortDate(publish.created_at)));
    row.appendChild(el("td", null, publish.comment || "—"));

    const actions = el("td", "row-actions");
    if (publish.report_path) {
      const reportBtn = el("button", "btn small", "REPORT");
      reportBtn.addEventListener("click", () =>
        window.fivehub.openReport(publish.report_path),
      );
      actions.appendChild(reportBtn);
    }
    if (publish.version) {
      actions.appendChild(
        dotsButton(() => [
          {
            label: "Send to Houdini",
            action: async () => {
              try {
                await window.fivehub.send(context, publish.format, publish.version);
                toast(`${padVersion(publish.version)} STAGED — USE IMPORT IN HOUDINI`);
              } catch (error) {
                toast("SEND FAILED");
              }
            },
          },
          {
            label: "Copy path",
            action: async () => {
              await window.fivehub.copy(publish.path);
              toast("PUBLISH PATH COPIED");
            },
          },
          {
            label: "Reveal files",
            action: () => window.fivehub.reveal(publish.path),
          },
          {
            label: "Edit comment",
            action: () => editPublishComment(publish),
          },
          "-",
          {
            label: "Delete version",
            danger: true,
            action: () => deletePublish(publish),
          },
        ]),
      );
    }
    row.appendChild(actions);
    body.appendChild(row);
  }
  table.appendChild(body);
  return table;
}

document.getElementById("task-menu").addEventListener("click", (event) => {
  event.stopPropagation();
  openMenu(event.currentTarget, [
    {
      label: "Delete this task",
      danger: true,
      action: async () => {
        const ok = await confirmSheet(
          `Delete task ${context.entity} / ${context.task}?`,
          "All scene versions and publishes of this task are removed. This cannot be undone.",
          "DELETE TASK",
        );
        if (!ok) return;
        try {
          await window.fivehub.taskDelete(context);
          window.close();
        } catch (error) {
          toast(cliErrorText(error).toUpperCase());
        }
      },
    },
  ]);
});

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
