// Project window — everything here is scoped to one project: its assets,
// shots, tasks and a project-only activity feed. Creation happens in
// sheets opened by the + buttons, never inline.

const { name: projectName } = queryParams();
let defaultTasks = [];

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

      // Pick the tasks to set up right away — toggles, not free inputs.
      const tasksField = sheetField(body, "TASKS TO CREATE");
      const chips = el("div", "chips");
      const selected = new Set();
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
        });
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
        return { name, tasks };
      };
    },
  });
  if (!values) return;
  try {
    await window.fivehub.entityCreate(projectName, kind, values.name);
    for (const task of values.tasks) {
      await window.fivehub.taskCreate(projectName, kind, values.name, task);
    }
    toast(kind.toUpperCase() + " CREATED");
    await load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

async function taskSheet(kind, entityName) {
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
    await load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

function entityBlock(kind, entity) {
  const block = el("div", "entity-block");
  const head = el("div", "entity-head");
  head.appendChild(el("div", "name", entity.name));
  head.appendChild(
    dotsButton(() => [
      { label: "New task", action: () => taskSheet(kind, entity.name) },
      "-",
      {
        label: "Delete " + kind,
        danger: true,
        action: async () => {
          const ok = await confirmSheet(
            `Delete ${kind} ${entity.name}?`,
            "All of its tasks, scene versions and publishes are removed. This cannot be undone.",
            "DELETE " + kind.toUpperCase(),
          );
          if (!ok) return;
          try {
            await window.fivehub.entityDelete(projectName, kind, entity.name);
            toast(kind.toUpperCase() + " DELETED");
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
      `${task.name} · ${task.scene_count}S/${task.publish_count}P`,
    );
    chip.addEventListener("click", () =>
      window.fivehub.openTask({
        project: projectName,
        kind,
        entity: entity.name,
        task: task.name,
      }),
    );
    chips.appendChild(chip);
  }
  const addChip = el("button", "chip add", "+ TASK");
  addChip.addEventListener("click", () => taskSheet(kind, entity.name));
  chips.appendChild(addChip);
  block.appendChild(chips);
  return block;
}

function fillColumn(containerId, kind, entities) {
  const container = document.getElementById(containerId);
  clear(container);
  if (!entities.length) {
    container.appendChild(el("div", "label", "NONE YET — USE +"));
    return;
  }
  for (const entity of entities) container.appendChild(entityBlock(kind, entity));
}

document.getElementById("add-asset").addEventListener("click", () => entitySheet("asset"));
document.getElementById("add-shot").addEventListener("click", () => entitySheet("shot"));

function activityRow(entry) {
  const row = el("div", "activity-row");
  const isPublish = entry.type === "publish";
  const blocked = isPublish && !entry.passed;
  const typeChip = el(
    "span",
    "activity-type" + (blocked ? " blocked" : ""),
    blocked ? "BLOCKED" : isPublish ? "PUBLISH" : "SAVE",
  );
  row.appendChild(typeChip);

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

async function load() {
  try {
    const [{ project }, rootInfo, activity] = await Promise.all([
      window.fivehub.browse(projectName),
      window.fivehub.root(),
      window.fivehub.activity(projectName),
    ]);
    defaultTasks = rootInfo.default_tasks || [];

    document.title = "FIVEHUB — " + project.name;
    const counts = project.counts || {};
    document.getElementById("counts").textContent =
      `${counts.assets || 0} ASSETS · ${counts.shots || 0} SHOTS · ${counts.publishes || 0} PUBLISHES`;
    document.getElementById("project-path").textContent = project.image_path
      ? project.image_path.replace(/[/\\][^/\\]*$/, "")
      : "";

    const titleRow = document.getElementById("title-row");
    clear(titleRow);
    if (project.image_path) {
      const img = el("img", "project-image");
      img.src = window.fivehub.fileUrl(project.image_path);
      img.alt = project.name;
      titleRow.appendChild(img);
    }
    titleRow.appendChild(el("h1", "title", project.name));

    fillColumn("assets", "asset", project.assets || []);
    fillColumn("shots", "shot", project.shots || []);
    renderActivity(activity);
  } catch (error) {
    showError(document.querySelector("main .stack"), error);
  }
}

load();
