// Task window — the work scenes and publishes of one entity task.

const context = queryParams(); // {project, kind, entity, task}

const backBtn = document.getElementById("back");
backBtn.textContent = "‹ " + (context.entity || "BACK").toUpperCase();
backBtn.addEventListener("click", () =>
  go("entity.html", { project: context.project, kind: context.kind, name: context.entity }),
);

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
        await window.fivehub.openScene(scene.file, projectRoot);
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

function publishesTable(publishes, emptyText) {
  if (!publishes.length) {
    return el("div", "label", emptyText || "NOTHING PUBLISHED YET");
  }
  const table = el("table");
  const head = el("thead");
  const headRow = el("tr");
  for (const column of [
    "", "FORMAT", "VERSION", "VARIANT", "STATUS", "BY", "PUBLISHED", "COMMENT", "",
  ]) {
    headRow.appendChild(el("th", null, column));
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = el("tbody");
  for (const publish of publishes) {
    const row = el("tr");
    const thumbCell = el("td", "thumb-cell");
    if (publish.thumbnail) {
      const img = el("img", "table-thumb");
      img.src = window.fivehub.fileUrl(publish.thumbnail);
      img.alt = "";
      thumbCell.appendChild(img);
    }
    row.appendChild(thumbCell);
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

async function ingestSheet() {
  const files = await window.fivehub.pickFiles("Files to ingest into this task");
  if (!files.length) return;
  const values = await openSheet({
    title: "Ingest " + files.length + " file(s)",
    submitLabel: "VALIDATE + INGEST",
    build(body) {
      const listField = sheetField(body, "FILES");
      for (const file of files.slice(0, 6)) {
        listField.appendChild(el("span", "mono", file));
      }
      if (files.length > 6) {
        listField.appendChild(el("span", "mono", "… and " + (files.length - 6) + " more"));
      }
      const nameField = sheetField(body, "PUBLISH NAME");
      const nameInput = el("input");
      nameInput.type = "text";
      nameInput.value = context.entity;
      nameField.appendChild(nameInput);
      const commentField = sheetField(body, "COMMENT");
      const commentInput = el("input");
      commentInput.type = "text";
      commentInput.placeholder = "e.g. vendor delivery 07-23";
      commentField.appendChild(commentInput);
      return () => ({
        name: nameInput.value.trim() || context.entity,
        comment: commentInput.value.trim(),
      });
    },
  });
  if (!values) return;
  try {
    const { result } = await window.fivehub.ingest(
      context, files, values.name, values.comment,
    );
    toast(
      result.passed
        ? "INGESTED AS " + result.format.toUpperCase() + " " + result.version_label
        : "INGEST BLOCKED — SEE REPORT",
    );
    if (!result.passed && result.report_path) {
      window.fivehub.openReport(result.report_path);
    }
    load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

document.getElementById("ingest").addEventListener("click", ingestSheet);

// Fresh start on this task: launch Houdini bound to it (JOB + FH_* env) —
// the FIVE HUB Save Scene As dialog opens prefilled and creates v001.
document.getElementById("new-scene").addEventListener("click", async () => {
  try {
    await window.fivehub.launchHoudini(context, projectRoot);
    toast("HOUDINI LAUNCHED — SAVE SCENE AS CREATES THE FIRST VERSION");
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
});

function depsList(uses, usedBy) {
  const box = el("div", "activity-list");
  for (const dep of uses) {
    const row = el("div", "activity-row");
    row.appendChild(el("span", "activity-type", "USES"));
    const pin = dep.src_version
      ? "pinned v" + String(dep.src_version).padStart(3, "0")
      : "follows latest";
    row.appendChild(
      el(
        "span",
        "what",
        `${dep.src_entity} / ${dep.src_task} · ${dep.src_name} (${dep.src_format}) · ${pin}`,
      ),
    );
    if (dep.outdated) {
      row.appendChild(
        el(
          "span",
          "status-pass",
          "V" + String(dep.latest_version).padStart(3, "0") + " AVAILABLE",
        ),
      );
    }
    row.appendChild(el("span", "when", shortDate(dep.created_at)));
    box.appendChild(row);
  }
  for (const dep of usedBy) {
    const row = el("div", "activity-row");
    row.appendChild(el("span", "activity-type", "USED BY"));
    row.appendChild(
      el("span", "what", `${dep.consumer_entity} / ${dep.consumer_task}`),
    );
    row.appendChild(el("span", "who", dep.user || "—"));
    row.appendChild(el("span", "when", shortDate(dep.created_at)));
    box.appendChild(row);
  }
  return box;
}

let projectRoot = "";
let lastInfo = null;
let pubView = "publishes"; // "publishes" = passed versions, "log" = every attempt

function renderPublishes() {
  const box = document.getElementById("publishes");
  clear(box);
  const all = (lastInfo && lastInfo.publishes) || [];
  if (pubView === "log") {
    box.appendChild(publishesTable(all, "NO PUBLISH ATTEMPTS YET"));
  } else {
    box.appendChild(
      publishesTable(
        all.filter((publish) => publish.passed && publish.version),
        "NOTHING PUBLISHED YET",
      ),
    );
  }
}

for (const button of document.querySelectorAll("#pub-view .seg-item")) {
  button.addEventListener("click", () => {
    pubView = button.dataset.view;
    for (const other of document.querySelectorAll("#pub-view .seg-item")) {
      other.classList.toggle("on", other === button);
    }
    renderPublishes();
  });
}

async function load() {
  const scenesBox = document.getElementById("scenes");
  try {
    const info = await window.fivehub.taskInfo(context);
    projectRoot = info.root || "";

    const others = (info.presence || []).filter(Boolean);
    document.getElementById("presence").textContent = others.length
      ? "IN USE — " + others.map((p) => p.user).join(", ")
      : "";

    clear(scenesBox);
    scenesBox.appendChild(scenesTable(info.scenes));
    lastInfo = info;
    renderPublishes();

    const depsSection = document.getElementById("deps-section");
    const depsBox = document.getElementById("deps");
    const uses = info.uses || [];
    const usedBy = info.used_by || [];
    if (uses.length || usedBy.length) {
      depsSection.classList.remove("hidden");
      clear(depsBox);
      depsBox.appendChild(depsList(uses, usedBy));
    } else {
      depsSection.classList.add("hidden");
    }
  } catch (error) {
    showError(scenesBox, error);
  }
}

load();
autoRefresh(load);
