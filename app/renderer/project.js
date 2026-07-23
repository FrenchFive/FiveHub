// Project window — assets and shots, their tasks, and creation of both.

const { name: projectName } = queryParams();
let defaultTasks = [];

function cliError(error) {
  toast(String(error.message || error).replace(/^Error[:] ?/i, "").toUpperCase());
}

function entityBlock(kind, entity) {
  const block = el("div", "entity-block");

  const head = el("div", "entity-head");
  head.appendChild(el("div", "name", entity.name));
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

  const addRow = el("div", "form-row");
  const input = el("input");
  input.type = "text";
  input.placeholder = "NEW TASK";
  input.setAttribute("list", "task-suggestions");
  const button = el("button", "btn", "+");
  const create = async () => {
    const task = input.value.trim();
    if (!task) return;
    try {
      await window.fivehub.taskCreate(projectName, kind, entity.name, task);
      toast("TASK CREATED");
      await load();
    } catch (error) {
      cliError(error);
    }
  };
  button.addEventListener("click", create);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") create();
  });
  addRow.appendChild(input);
  addRow.appendChild(button);

  block.appendChild(chips);
  block.appendChild(addRow);
  return block;
}

function fillColumn(containerId, kind, entities) {
  const container = document.getElementById(containerId);
  clear(container);
  if (!entities.length) {
    container.appendChild(el("div", "label", "NONE YET"));
    return;
  }
  for (const entity of entities) container.appendChild(entityBlock(kind, entity));
}

async function createEntity(kind, inputId) {
  const input = document.getElementById(inputId);
  const name = input.value.trim();
  if (!name) return;
  try {
    await window.fivehub.entityCreate(projectName, kind, name);
    input.value = "";
    toast(kind.toUpperCase() + " CREATED");
    await load();
  } catch (error) {
    cliError(error);
  }
}

document.getElementById("add-asset").addEventListener("click", () =>
  createEntity("asset", "new-asset"),
);
document.getElementById("add-shot").addEventListener("click", () =>
  createEntity("shot", "new-shot"),
);
for (const [inputId, kind] of [["new-asset", "asset"], ["new-shot", "shot"]]) {
  document.getElementById(inputId).addEventListener("keydown", (event) => {
    if (event.key === "Enter") createEntity(kind, inputId);
  });
}

async function load() {
  try {
    const [{ project }, rootInfo] = await Promise.all([
      window.fivehub.browse(projectName),
      window.fivehub.root(),
    ]);
    defaultTasks = rootInfo.default_tasks || [];

    let datalist = document.getElementById("task-suggestions");
    if (!datalist) {
      datalist = el("datalist");
      datalist.id = "task-suggestions";
      document.body.appendChild(datalist);
    }
    clear(datalist);
    for (const task of defaultTasks) {
      const option = el("option");
      option.value = task;
      datalist.appendChild(option);
    }

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
  } catch (error) {
    showError(document.querySelector("main .stack"), error);
  }
}

load();
