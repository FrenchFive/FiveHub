// Projects window — every project as a card; create new ones with an image.

const projectsBox = document.getElementById("projects");
const createForm = document.getElementById("create-form");
const nameInput = document.getElementById("project-name");
const imageName = document.getElementById("image-name");

let pickedImage = null;

document.getElementById("new-project").addEventListener("click", () => {
  createForm.classList.toggle("hidden");
  if (!createForm.classList.contains("hidden")) nameInput.focus();
});

document.getElementById("pick-image").addEventListener("click", async () => {
  pickedImage = await window.fivehub.pickImage();
  imageName.textContent = pickedImage || "";
});

document.getElementById("create-project").addEventListener("click", createProject);
nameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") createProject();
});

async function createProject() {
  const name = nameInput.value.trim();
  if (!name) {
    toast("NAME REQUIRED");
    return;
  }
  try {
    await window.fivehub.projectCreate(name, pickedImage);
    nameInput.value = "";
    pickedImage = null;
    imageName.textContent = "";
    createForm.classList.add("hidden");
    toast("PROJECT CREATED");
    await load();
  } catch (error) {
    toast(String(error.message || error).replace(/^Error[:] ?/i, "").toUpperCase());
  }
}

function card(project) {
  const node = el("div", "card");
  if (project.image_path) {
    const img = el("img", "thumb");
    img.src = window.fivehub.fileUrl(project.image_path);
    img.alt = project.name;
    node.appendChild(img);
  } else {
    node.appendChild(el("div", "thumb empty", "NO IMAGE"));
  }
  node.appendChild(el("div", "name", project.name));
  const counts = project.counts || {};
  node.appendChild(
    el(
      "div",
      "meta",
      `${counts.assets || 0} ASSETS · ${counts.shots || 0} SHOTS · ${counts.publishes || 0} PUBLISHES`,
    ),
  );
  node.addEventListener("click", () => window.fivehub.openProject(project.name));
  return node;
}

async function load() {
  try {
    const [rootInfo, listing] = await Promise.all([
      window.fivehub.root(),
      window.fivehub.projects(),
    ]);
    document.getElementById("hub-path").textContent = rootInfo.root;
    document.getElementById("count").textContent =
      listing.projects.length + " PROJECT(S)";

    clear(projectsBox);
    if (!listing.projects.length) {
      const box = el("div", "empty-state");
      box.appendChild(el("div", null, "NO PROJECTS YET"));
      box.appendChild(el("div", null, "CREATE ONE ABOVE — OR SEED THE DEMO"));
      const demoBtn = el("button", "btn solid", "SEED DEMO PROJECT");
      demoBtn.addEventListener("click", async () => {
        demoBtn.textContent = "PUBLISHING…";
        try {
          await window.fivehub.demo();
          await load();
          toast("DEMO PROJECT SEEDED");
        } catch (error) {
          toast("DEMO FAILED");
          showError(projectsBox, error);
        }
      });
      box.appendChild(demoBtn);
      projectsBox.appendChild(box);
      return;
    }
    const grid = el("div", "grid");
    for (const project of listing.projects) grid.appendChild(card(project));
    projectsBox.appendChild(grid);
  } catch (error) {
    showError(projectsBox, error);
  }
}

load();
