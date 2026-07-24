// Task window — the work scenes and publishes of one entity task.

const context = queryParams(); // {project, kind, entity, task}

const backBtn = document.getElementById("back");
setButtonLabel(backBtn, "chevron-left", (context.entity || "BACK").toUpperCase());
backBtn.addEventListener("click", () =>
  go("entity.html", { project: context.project, kind: context.kind, name: context.entity }),
);

document.getElementById("context-label").textContent =
  `${context.project} · ${context.kind} ${context.entity}`;
// Folder-style path — every parent segment is clickable.
pathTitle(document.getElementById("task-title"), [
  {
    label: context.project,
    go: () => go("project.html", { name: context.project }),
  },
  {
    label: context.entity,
    go: () =>
      go("entity.html", {
        project: context.project,
        kind: context.kind,
        name: context.entity,
      }),
  },
  { label: context.task },
]);
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
        rememberRecentScene({
          project: context.project,
          kind: context.kind,
          entity: context.entity,
          task: context.task,
          version: scene.version,
          file: scene.file,
          root: projectRoot,
          when: new Date().toISOString(),
        });
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

// Everything that would clutter a publish line lives here instead.
function detailsSheet(publish) {
  openSheet({
    title:
      (publish.name || "publish") +
      (publish.version ? " " + padVersion(publish.version) : ""),
    submitLabel: "CLOSE",
    hideCancel: true,
    build(body) {
      const add = (labelText, value) => {
        if (!value) return;
        const field = sheetField(body, labelText);
        field.appendChild(el("span", "mono", String(value)));
      };
      add("FORMAT", (publish.format || "").toUpperCase());
      add("VARIANT", publish.variant);
      add(
        "STATUS",
        (publish.passed ? "PASS" : "FAIL") +
          ` — ${publish.errors || 0} error(s), ${publish.warnings || 0} warning(s)`,
      );
      add("BY", publish.user);
      add("PUBLISHED", shortDate(publish.created_at));
      add("COMMENT", publish.comment);
      add("SOURCE SCENE", publish.source_file);
      add("FILES", publish.path);
      add("REPORT", publish.report_path);
      return () => ({ closed: true });
    },
  });
}

function publishMenu(publish) {
  return [
    { label: "More details", action: () => detailsSheet(publish) },
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
    { label: "Reveal files", action: () => window.fivehub.reveal(publish.path) },
    { label: "Edit comment", action: () => editPublishComment(publish) },
    "-",
    { label: "Delete version", danger: true, action: () => deletePublish(publish) },
  ];
}

// Thumbnail that opens the image inspector on click.
function thumbFor(publish, className) {
  if (!publish.thumbnail) return el("span", className + " empty");
  const img = el("img", className);
  img.src = window.fivehub.fileUrl(publish.thumbnail);
  img.alt = publish.name || "";
  img.title = "Inspect image";
  img.addEventListener("click", (event) => {
    event.stopPropagation();
    openLightbox(img.src, publish.name);
  });
  return img;
}

function publishesTable(publishes, emptyText) {
  if (!publishes.length) {
    return el("div", "label", emptyText || "NOTHING PUBLISHED YET");
  }
  const table = el("table");
  const head = el("thead");
  const headRow = el("tr");
  for (const column of [
    "", "NAME", "FORMAT", "VERSION", "STATUS", "BY", "PUBLISHED", "",
  ]) {
    headRow.appendChild(el("th", null, column));
  }
  head.appendChild(headRow);
  table.appendChild(head);

  const body = el("tbody");
  for (const publish of publishes) {
    const row = el("tr");
    const thumbCell = el("td", "thumb-cell");
    if (publish.thumbnail) thumbCell.appendChild(thumbFor(publish, "table-thumb"));
    row.appendChild(thumbCell);
    row.appendChild(el("td", null, publish.name || "—"));
    row.appendChild(el("td", null, (publish.format || "").toUpperCase()));
    row.appendChild(el("td", null, publish.version ? padVersion(publish.version) : "—"));

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

    const actions = el("td", "row-actions");
    if (publish.report_path) {
      const reportBtn = el("button", "btn small");
    setButtonLabel(reportBtn, "file-text", "REPORT");
      reportBtn.addEventListener("click", () =>
        window.fivehub.openReport(publish.report_path),
      );
      actions.appendChild(reportBtn);
    }
    if (publish.version) {
      actions.appendChild(dotsButton(() => publishMenu(publish)));
    } else {
      actions.appendChild(
        dotsButton(() => [
          { label: "More details", action: () => detailsSheet(publish) },
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
const expandedPublishes = new Set(); // survives autoRefresh re-renders

function versionRow(publish) {
  const row = el("div", "pub-version");
  row.appendChild(thumbFor(publish, "pub-thumb"));
  row.appendChild(el("span", "pub-ver mono", padVersion(publish.version)));
  row.appendChild(
    el(
      "span",
      publish.passed ? "status-pass" : "status-fail",
      publish.passed ? "PASS" : "FAIL",
    ),
  );
  row.appendChild(el("span", "pub-meta", publish.user || "—"));
  row.appendChild(el("span", "pub-meta", shortDate(publish.created_at)));
  row.appendChild(el("span", "spacer"));
  if (publish.report_path) {
    const reportBtn = el("button", "btn small");
    setButtonLabel(reportBtn, "file-text", "REPORT");
    reportBtn.addEventListener("click", () =>
      window.fivehub.openReport(publish.report_path),
    );
    row.appendChild(reportBtn);
  }
  row.appendChild(dotsButton(() => publishMenu(publish)));
  return row;
}

// One collapsed element per publish NAME (an fx task ships many layers —
// the name is what tells them apart). The chevron reveals the versions.
function groupBlock(name, format, versions, showFormat) {
  const key = name + "::" + format;
  const expanded = expandedPublishes.has(key);
  const box = el("div", "pub-group");
  const head = el("div", "pub-group-head");
  const chevron = el("span", "chevron" + (expanded ? " open" : ""));
  chevron.appendChild(icon("chevron-right"));
  head.appendChild(chevron);
  head.appendChild(thumbFor(versions[0], "pub-thumb"));
  head.appendChild(el("span", "pub-name", name));
  if (showFormat) head.appendChild(el("span", "label", format.toUpperCase()));
  head.appendChild(el("span", "spacer"));
  head.appendChild(
    el(
      "span",
      "label",
      padVersion(versions[0].version) + " · " +
        versions.length + (versions.length === 1 ? " VERSION" : " VERSIONS"),
    ),
  );
  head.addEventListener("click", () => {
    if (expandedPublishes.has(key)) expandedPublishes.delete(key);
    else expandedPublishes.add(key);
    renderPublishes();
  });
  box.appendChild(head);
  if (expanded) {
    const list = el("div", "pub-versions");
    for (const publish of versions) list.appendChild(versionRow(publish));
    box.appendChild(list);
  }
  return box;
}

function renderPublishes() {
  const box = document.getElementById("publishes");
  clear(box);
  const all = (lastInfo && lastInfo.publishes) || [];
  if (pubView === "log") {
    box.appendChild(publishesTable(all, "NO PUBLISH ATTEMPTS YET"));
    return;
  }
  const live = all.filter((publish) => publish.passed && publish.version);
  if (!live.length) {
    box.appendChild(el("div", "label", "NOTHING PUBLISHED YET"));
    return;
  }
  const groups = new Map();
  for (const publish of live) {
    const key = (publish.name || "unnamed") + "::" + (publish.format || "");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(publish);
  }
  // A name shared by several formats gets a small format tag to stay unique.
  const nameCounts = new Map();
  for (const key of groups.keys()) {
    const name = key.split("::")[0];
    nameCounts.set(name, (nameCounts.get(name) || 0) + 1);
  }
  const wrap = el("div", "pub-groups");
  for (const [key, versions] of [...groups.entries()].sort((a, b) =>
    a[0].localeCompare(b[0]),
  )) {
    versions.sort((a, b) => b.version - a.version);
    const [name, format] = key.split("::");
    wrap.appendChild(groupBlock(name, format, versions, nameCounts.get(name) > 1));
  }
  box.appendChild(wrap);
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
