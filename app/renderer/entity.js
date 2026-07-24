// Entity page — one asset or shot, inspected: its metadata, every task
// (click-through to the task page) and the publishes of all its tasks.

const { project: projectName, kind, name: entityName } = queryParams();
let defaultTasks = [];
let entityData = null;

document.title = `FIVEHUB — ${entityName}`;
const backBtn = document.getElementById("back");
setButtonLabel(backBtn, "chevron-left", (projectName || "PROJECT").toUpperCase());
backBtn.addEventListener("click", () => go("project.html", { name: projectName }));
document.getElementById("context-label").textContent = `${projectName} · ${kind}`;

function taskContext(taskName) {
  return { project: projectName, kind, entity: entityName, task: taskName };
}

// Compact card — identical geometry with or without an image (the
// placeholder keeps the layout consistent).
function taskCard(task) {
  const card = el("div", "entity-card");
  if (task.image) {
    const img = el("img", "entity-card-image");
    img.src = window.fivehub.fileUrl(task.image);
    img.alt = task.name;
    img.title = "Inspect image";
    img.addEventListener("click", (event) => {
      event.stopPropagation();
      openLightbox(img.src, task.name);
    });
    card.appendChild(img);
  } else {
    card.appendChild(el("div", "entity-card-empty", "NO PUBLISH YET"));
  }
  const head = el("div", "entity-card-head");
  const name = el("div", "name", task.name);
  name.title = task.name;
  head.appendChild(name);
  if (task.publish_count) {
    const badge = el("span", "pub-badge");
    badge.appendChild(icon("check"));
    badge.title = "PUBLISHED " + shortDate(task.last_publish_at || "");
    head.appendChild(badge);
  }
  card.appendChild(head);
  const bits = [];
  if (task.publish_count) {
    bits.push("PUBLISHED " + shortDate(task.last_publish_at || ""));
  }
  if (task.active_user) bits.push("● " + task.active_user);
  if (bits.length) card.appendChild(el("div", "meta", bits.join(" · ")));
  card.addEventListener("click", () => go("task.html", taskContext(task.name)));
  return card;
}

function publishRow(publish) {
  const row = el("div", "activity-row");
  row.appendChild(
    el(
      "span",
      "activity-type" + (publish.passed ? "" : " blocked"),
      publish.passed ? "PASS" : "FAIL",
    ),
  );
  const version = publish.version
    ? "V" + String(publish.version).padStart(3, "0")
    : "";
  row.appendChild(
    el(
      "span",
      "what",
      `${(publish.format || "").toUpperCase()} ${version} · ${publish.task}` +
        (publish.comment ? ` · ${publish.comment}` : ""),
    ),
  );
  row.appendChild(el("span", "who", publish.user || "—"));
  row.appendChild(el("span", "when", shortDate(publish.created_at)));
  row.style.cursor = "pointer";
  row.addEventListener("click", () => go("task.html", taskContext(publish.task)));
  return row;
}

async function load() {
  const tasksBox = document.getElementById("tasks");
  try {
    const [{ project }, rootInfo] = await Promise.all([
      window.fivehub.browse(projectName),
      window.fivehub.root(),
    ]);
    defaultTasks = rootInfo.default_tasks || [];
    const pool = kind === "asset" ? project.assets || [] : project.shots || [];
    const entity = pool.find((candidate) => candidate.name === entityName);
    if (!entity) {
      throw new Error(`${kind} ${entityName} is no longer in ${projectName}`);
    }
    entityData = entity;

    // Folder-style path — the project segment navigates back.
    pathTitle(document.getElementById("entity-title"), [
      {
        label: projectName,
        go: () => go("project.html", { name: projectName }),
      },
      { label: entity.name },
    ]);
    const heroImage = document.getElementById("entity-image");
    if (entity.image) {
      heroImage.src = window.fivehub.fileUrl(entity.image);
      heroImage.classList.remove("hidden");
    } else {
      heroImage.classList.add("hidden");
    }
    const meta = [kind.toUpperCase()];
    if (entity.sequence) meta.push(entity.sequence);
    if (entity.frame_start) meta.push(`${entity.frame_start}–${entity.frame_end}`);
    if (entity.fps) meta.push(entity.fps + " FPS");
    if (entity.res_x) meta.push(`${entity.res_x}×${entity.res_y}`);
    document.getElementById("entity-meta").textContent = meta.join(" · ");
    document.getElementById("entity-path").textContent = project.root || "";

    clear(tasksBox);
    if (!entity.tasks.length) {
      tasksBox.appendChild(el("div", "label", "NO TASKS YET"));
    } else {
      const grid = el("div", "entity-grid");
      for (const task of entity.tasks) grid.appendChild(taskCard(task));
      tasksBox.appendChild(grid);
    }

    // Publishes across every task of this entity, newest first.
    const infos = await Promise.all(
      entity.tasks.map((task) =>
        window.fivehub.taskInfo(taskContext(task.name)).then(
          (info) => ({ task: task.name, publishes: info.publishes || [] }),
          () => ({ task: task.name, publishes: [] }),
        ),
      ),
    );
    const publishes = infos
      .flatMap((info) => info.publishes.map((p) => ({ ...p, task: info.task })))
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    const publishesBox = document.getElementById("publishes");
    clear(publishesBox);
    if (!publishes.length) {
      publishesBox.appendChild(el("div", "label", "NOTHING PUBLISHED YET"));
      return;
    }
    const list = el("div", "activity-list");
    for (const publish of publishes.slice(0, 30)) {
      list.appendChild(publishRow(publish));
    }
    publishesBox.appendChild(list);
  } catch (error) {
    showError(document.querySelector("main .stack"), error);
  }
}

document.getElementById("add-task").addEventListener("click", () =>
  taskSheetShared(projectName, kind, entityName, defaultTasks, load),
);

document.getElementById("entity-image").addEventListener("click", (event) =>
  openLightbox(event.currentTarget.src, entityName),
);

document.getElementById("entity-menu").addEventListener("click", (event) => {
  event.stopPropagation();
  openMenu(event.currentTarget, [
    {
      label: "New task",
      action: () =>
        taskSheetShared(projectName, kind, entityName, defaultTasks, load),
    },
    {
      label: "Edit metadata",
      action: () =>
        entityData && editEntitySheetShared(projectName, kind, entityData, load),
    },
    "-",
    {
      label: "Delete " + kind,
      danger: true,
      action: async () => {
        const ok = await confirmSheet(
          `Delete ${kind} ${entityName}?`,
          "Its tasks, scenes and publishes move to the project trash.",
          "DELETE " + kind.toUpperCase(),
        );
        if (!ok) return;
        try {
          await window.fivehub.entityDelete(projectName, kind, entityName);
          go("project.html", { name: projectName });
        } catch (error) {
          toast(cliErrorText(error).toUpperCase());
        }
      },
    },
  ]);
});

load();
autoRefresh(load);
