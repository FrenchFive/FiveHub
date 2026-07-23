// Entity page — one asset or shot, inspected: its metadata, every task
// (click-through to the task page) and the publishes of all its tasks.

const { project: projectName, kind, name: entityName } = queryParams();
let defaultTasks = [];
let entityData = null;

document.title = `FIVEHUB — ${entityName}`;
const backBtn = document.getElementById("back");
backBtn.textContent = "‹ " + (projectName || "PROJECT").toUpperCase();
backBtn.addEventListener("click", () => go("project.html", { name: projectName }));
document.getElementById("context-label").textContent = `${projectName} · ${kind}`;

function taskContext(taskName) {
  return { project: projectName, kind, entity: entityName, task: taskName };
}

function taskRow(task) {
  const block = el("div", "entity-block");
  const head = el("div", "entity-head");
  head.appendChild(el("div", "name", task.name));
  head.appendChild(
    el(
      "span",
      "meta",
      `${task.scene_count} SCENES · ${task.publish_count} PUBLISHES` +
        (task.active_user ? ` · ● ${task.active_user}` : ""),
    ),
  );
  block.appendChild(head);
  block.addEventListener("click", () => go("task.html", taskContext(task.name)));
  return block;
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

    document.getElementById("entity-title").textContent = entity.name;
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
    }
    for (const task of entity.tasks) tasksBox.appendChild(taskRow(task));

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
