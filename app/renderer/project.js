// Project window — everything here is scoped to one project: its assets,
// shots (grouped by sequence), reference gallery, jobs and activity.
// Creation happens in sheets opened by the + buttons, never inline.

const { name: projectName } = queryParams();
let defaultTasks = [];
let projectSettings = {};

const searchInput = document.getElementById("search");
let lastTree = null;

function matches(entity) {
  const term = searchInput.value.trim().toLowerCase();
  if (!term) return true;
  if (entity.name.toLowerCase().includes(term)) return true;
  if ((entity.sequence || "").toLowerCase().includes(term)) return true;
  return entity.tasks.some((task) => task.name.toLowerCase().includes(term));
}

async function entitySheet(kind) {
  const values = await openSheet({
    title: kind === "asset" ? "New asset" : "New shot",
    submitLabel: "CREATE",
    build(body) {
      const nameField = sheetField(body, "NAME");
      const nameInput = el("input");
      nameInput.type = "text";
      nameInput.placeholder = kind === "asset" ? "e.g. WoodenCrate" : "e.g. SH010";
      nameField.appendChild(nameInput);

      let sequenceInput = null;
      let startInput = null;
      let endInput = null;
      if (kind === "shot") {
        const sequenceField = sheetField(body, "SEQUENCE (GROUPING)");
        sequenceInput = el("input");
        sequenceInput.type = "text";
        sequenceInput.placeholder = "e.g. SEQ010";
        sequenceField.appendChild(sequenceInput);

        const rangeField = sheetField(body, "FRAME RANGE");
        const rangeRow = el("div", "form-row");
        startInput = el("input");
        startInput.type = "text";
        startInput.value = projectSettings.frame_start ?? 1001;
        endInput = el("input");
        endInput.type = "text";
        endInput.value = projectSettings.frame_end ?? 1100;
        rangeRow.appendChild(startInput);
        rangeRow.appendChild(endInput);
        rangeField.appendChild(rangeRow);
      }

      const tasksField = sheetField(body, "TASKS TO CREATE");
      const chips = el("div", "chips");
      const selected = new Set();
      const taskChips = new Map();
      const allChip = el("button", "chip toggle all", "ALL");
      const syncAll = () => {
        allChip.classList.toggle(
          "on",
          defaultTasks.length > 0 && selected.size === defaultTasks.length,
        );
      };
      allChip.addEventListener("click", () => {
        const everything = selected.size === defaultTasks.length;
        selected.clear();
        if (!everything) for (const task of defaultTasks) selected.add(task);
        for (const [task, chip] of taskChips) {
          chip.classList.toggle("on", selected.has(task));
        }
        syncAll();
      });
      chips.appendChild(allChip);
      for (const task of defaultTasks) {
        const chip = el("button", "chip toggle", task);
        chip.addEventListener("click", () => {
          if (selected.has(task)) {
            selected.delete(task);
            chip.classList.remove("on");
          } else {
            selected.add(task);
            chip.classList.add("on");
          }
          syncAll();
        });
        taskChips.set(task, chip);
        chips.appendChild(chip);
      }
      tasksField.appendChild(chips);

      const extraField = sheetField(body, "EXTRA TASK (OPTIONAL)");
      const extraInput = el("input");
      extraInput.type = "text";
      extraInput.placeholder = "e.g. groom";
      extraField.appendChild(extraInput);

      return () => {
        const name = nameInput.value.trim();
        if (!name) return null;
        const tasks = [...selected];
        const extra = extraInput.value.trim();
        if (extra) tasks.push(extra);
        return {
          name,
          tasks,
          sequence: sequenceInput ? sequenceInput.value.trim() : "",
          frame_start: startInput ? startInput.value.trim() : "",
          frame_end: endInput ? endInput.value.trim() : "",
        };
      };
    },
  });
  if (!values) return;
  try {
    await window.fivehub.entityCreate(projectName, kind, values.name);
    if (kind === "shot" && (values.sequence || values.frame_start)) {
      await window.fivehub.entityUpdate(projectName, kind, values.name, {
        sequence: values.sequence,
        frame_start: values.frame_start,
        frame_end: values.frame_end,
      });
    }
    for (const task of values.tasks) {
      await window.fivehub.taskCreate(projectName, kind, values.name, task);
    }
    toast(kind.toUpperCase() + " CREATED");
    await load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

const editEntitySheet = (kind, entity) =>
  editEntitySheetShared(projectName, kind, entity, load);

const taskSheet = (kind, entityName) =>
  taskSheetShared(projectName, kind, entityName, defaultTasks, load);

function entityBlock(kind, entity) {
  const block = el("div", "entity-block");
  const head = el("div", "entity-head");
  if (entity.image) {
    // Latest publish thumbnail, picked by production order (lookdev
    // beats modeling) — the closest look at the current state.
    const img = el("img", "entity-thumb");
    img.src = window.fivehub.fileUrl(entity.image);
    img.alt = "";
    head.appendChild(img);
  }
  const title = el("div", "name", entity.name);
  head.appendChild(title);
  if (kind === "shot" && entity.frame_start) {
    head.appendChild(
      el("span", "meta", `${entity.frame_start}–${entity.frame_end}`),
    );
  }
  head.appendChild(
    dotsButton(() => [
      { label: "New task", action: () => taskSheet(kind, entity.name) },
      { label: "Edit metadata", action: () => editEntitySheet(kind, entity) },
      "-",
      {
        label: "Delete " + kind,
        danger: true,
        action: async () => {
          const ok = await confirmSheet(
            `Delete ${kind} ${entity.name}?`,
            "Its tasks, scenes and publishes move to the project trash.",
            "DELETE " + kind.toUpperCase(),
          );
          if (!ok) return;
          try {
            await window.fivehub.entityDelete(projectName, kind, entity.name);
            toast(kind.toUpperCase() + " MOVED TO TRASH");
            load();
          } catch (error) {
            toast(cliErrorText(error).toUpperCase());
          }
        },
      },
    ]),
  );
  block.appendChild(head);

  const chips = el("div", "chips");
  for (const task of entity.tasks) {
    const chip = el(
      "button",
      "chip",
      `${task.name} · ${task.scene_count}S/${task.publish_count}P` +
        (task.active_user ? ` · ● ${task.active_user}` : ""),
    );
    if (task.active_user) chip.title = "In use by " + task.active_user;
    chip.addEventListener("click", (event) => {
      event.stopPropagation();
      go("task.html", {
        project: projectName,
        kind,
        entity: entity.name,
        task: task.name,
      });
    });
    chips.appendChild(chip);
  }
  const addChip = el("button", "chip add", "+ TASK");
  addChip.addEventListener("click", (event) => {
    event.stopPropagation();
    taskSheet(kind, entity.name);
  });
  chips.appendChild(addChip);
  block.appendChild(chips);
  // The block itself opens the asset/shot page — chips go straight to a task.
  block.addEventListener("click", () =>
    go("entity.html", { project: projectName, kind, name: entity.name }),
  );
  return block;
}

function fillAssets(entities) {
  const container = document.getElementById("assets");
  document.getElementById("assets-count").textContent = String(entities.length);
  clear(container);
  const visible = entities.filter(matches);
  if (!visible.length) {
    container.appendChild(
      el("div", "label", entities.length ? "NO MATCH" : "NO ASSETS YET"),
    );
    return;
  }
  for (const entity of visible) container.appendChild(entityBlock("asset", entity));
}

function fillShots(entities) {
  const container = document.getElementById("shots");
  document.getElementById("shots-count").textContent = String(entities.length);
  clear(container);
  const visible = entities.filter(matches);
  if (!visible.length) {
    container.appendChild(
      el("div", "label", entities.length ? "NO MATCH" : "NO SHOTS YET"),
    );
    return;
  }
  // Group by sequence — movies get SEQ headers, loose shots go last.
  const groups = new Map();
  for (const entity of visible) {
    const key = entity.sequence || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(entity);
  }
  const keys = [...groups.keys()].sort((a, b) => (a || "zz").localeCompare(b || "zz"));
  for (const key of keys) {
    if (key) container.appendChild(el("div", "label seq-head", key));
    for (const entity of groups.get(key)) {
      container.appendChild(entityBlock("shot", entity));
    }
  }
}

function renderRefs(refs) {
  const container = document.getElementById("refs");
  clear(container);
  if (!refs.length) {
    container.appendChild(el("div", "label", "NO REFERENCES YET — BOARDS, BRIEFS, STILLS"));
    return;
  }
  const grid = el("div", "refs-grid");
  for (const ref of refs) {
    const cell = el("div", "ref-cell");
    if (ref.is_image) {
      const img = el("img", "ref-image");
      img.src = window.fivehub.fileUrl(ref.path);
      img.alt = ref.name;
      cell.appendChild(img);
    } else {
      cell.appendChild(el("div", "ref-file", ref.name.split(".").pop().toUpperCase()));
    }
    const meta = el("div", "ref-meta");
    meta.appendChild(el("span", "mono", ref.name));
    meta.appendChild(
      dotsButton(() => [
        { label: "Reveal file", action: () => window.fivehub.reveal(ref.path) },
        { label: "Copy path", action: async () => {
            await window.fivehub.copy(ref.path);
            toast("PATH COPIED");
          } },
        "-",
        {
          label: "Delete reference",
          danger: true,
          action: async () => {
            await window.fivehub.refsDelete(projectName, ref.name);
            toast("REFERENCE MOVED TO TRASH");
            load();
          },
        },
      ]),
    );
    cell.appendChild(meta);
    grid.appendChild(cell);
  }
  container.appendChild(grid);
}

document.getElementById("add-refs").addEventListener("click", async () => {
  const files = await window.fivehub.pickFiles("Add reference files");
  if (!files.length) return;
  await window.fivehub.refsAdd(projectName, files);
  toast(files.length + " REFERENCE(S) ADDED");
  load();
});

function renderJobs(jobs) {
  const container = document.getElementById("jobs");
  clear(container);
  if (!jobs.length) {
    container.appendChild(
      el("div", "label", "NO JOBS YET — SUBMIT RENDERS FROM THE FIVE HUB MENU IN HOUDINI"),
    );
    return;
  }
  const list = el("div", "activity-list");
  for (const job of jobs.slice(0, 10)) {
    const row = el("div", "activity-row");
    row.appendChild(
      el(
        "span",
        "activity-type" + (job.status === "failed" ? " blocked" : ""),
        job.status.toUpperCase(),
      ),
    );
    const what = job.type === "render"
      ? `render · ${job.payload.entity || "?"} / ${job.payload.task || "?"} · ${job.payload.rop || ""}`
      : `${job.type} · ${(job.payload.render_dir || "").split("/").slice(-3).join("/")}`;
    row.appendChild(el("span", "what", what));
    row.appendChild(el("span", "who", job.user || "—"));
    row.appendChild(el("span", "when", shortDate(job.created_at)));
    if (job.status === "queued") {
      const cancelBtn = el("button", "btn small", "CANCEL");
      cancelBtn.addEventListener("click", async () => {
        await window.fivehub.jobCancel(projectName, job.id);
        toast("JOB CANCELLED");
        load();
      });
      row.appendChild(cancelBtn);
    }
    list.appendChild(row);
  }
  container.appendChild(list);
}

function activityRow(entry) {
  const row = el("div", "activity-row");
  const isPublish = entry.type === "publish";
  const blocked = isPublish && !entry.passed;
  row.appendChild(
    el(
      "span",
      "activity-type" + (blocked ? " blocked" : ""),
      blocked ? "BLOCKED" : isPublish ? "PUBLISH" : "SAVE",
    ),
  );
  const what = isPublish
    ? `${(entry.format || "").toUpperCase()} ${
        entry.version ? "v" + String(entry.version).padStart(3, "0") : ""
      } · ${entry.entity} / ${entry.task}`.replace("  ", " ")
    : `scene v${String(entry.version).padStart(3, "0")} · ${entry.entity} / ${entry.task}`;
  row.appendChild(el("span", "what", what));
  row.appendChild(el("span", "who", entry.user || "—"));
  row.appendChild(el("span", "when", shortDate(entry.created_at)));
  return row;
}

function renderActivity(activity) {
  const container = document.getElementById("activity");
  clear(container);
  const entries = [
    ...activity.publishes.map((p) => ({ ...p, type: "publish" })),
    ...activity.scenes.map((s) => ({ ...s, type: "scene" })),
  ]
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 12);
  if (!entries.length) {
    container.appendChild(el("div", "label", "NO ACTIVITY YET"));
    return;
  }
  const list = el("div", "activity-list");
  for (const entry of entries) list.appendChild(activityRow(entry));
  container.appendChild(list);
}

document.getElementById("back").addEventListener("click", () => go("projects.html"));
document.getElementById("add-asset").addEventListener("click", () => entitySheet("asset"));
document.getElementById("add-shot").addEventListener("click", () => entitySheet("shot"));
searchInput.addEventListener("input", () => {
  if (lastTree) {
    fillAssets(lastTree.assets || []);
    fillShots(lastTree.shots || []);
  }
});

async function load() {
  try {
    const [{ project }, rootInfo, activity, refs, jobs] = await Promise.all([
      window.fivehub.browse(projectName),
      window.fivehub.root(),
      window.fivehub.activity(projectName),
      window.fivehub.refs(projectName),
      window.fivehub.jobs(projectName),
    ]);
    defaultTasks = rootInfo.default_tasks || [];
    projectSettings = project.settings || {};
    lastTree = project;

    document.title = "FIVEHUB — " + project.name;
    const counts = project.counts || {};
    document.getElementById("counts").textContent =
      `${counts.assets || 0} ASSETS · ${counts.shots || 0} SHOTS · ${counts.publishes || 0} PUBLISHES`;
    document.getElementById("project-path").textContent = project.root || "";

    const titleRow = document.getElementById("title-row");
    clear(titleRow);
    if (project.image_path) {
      const img = el("img", "project-image");
      img.src = window.fivehub.fileUrl(project.image_path);
      img.alt = project.name;
      titleRow.appendChild(img);
    }
    titleRow.appendChild(el("h1", "title", project.name));

    const git = project.git_status || {};
    if (git.git) {
      titleRow.appendChild(el("span", "spacer"));
      const parts = [git.branch || "?"];
      if (git.remote) parts.push(`↑${git.ahead} ↓${git.behind}`);
      if (git.dirty) parts.push(`${git.dirty} changed`);
      titleRow.appendChild(el("span", "label", "GIT · " + parts.join(" · ")));
      const syncBtn = el("button", "btn", "SYNC");
      syncBtn.addEventListener("click", async () => {
        syncBtn.textContent = "SYNCING…";
        try {
          const { sync } = await window.fivehub.gitSync(projectName);
          toast(sync.ok ? "SYNCED" : "SYNC NEEDS ATTENTION — SEE GIT");
        } catch (error) {
          toast(cliErrorText(error).toUpperCase());
        }
        syncBtn.textContent = "SYNC";
        load();
      });
      titleRow.appendChild(syncBtn);
    }

    fillAssets(project.assets || []);
    fillShots(project.shots || []);
    renderRefs(refs.refs || []);
    renderJobs(jobs.jobs || []);
    renderActivity(activity);
  } catch (error) {
    showError(document.querySelector("main .stack"), error);
  }
}

load();
autoRefresh(load);
