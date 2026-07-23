// Projects window — sign in once, browse project cards, create projects
// through a sheet (name, where the project lives, image).

const projectsBox = document.getElementById("projects");
const userPill = document.getElementById("user");

async function ensureLogin() {
  const who = await window.fivehub.whoami();
  let name = who.user;
  if (!name) {
    const values = await openSheet({
      title: "Who is working?",
      submitLabel: "START",
      allowCancel: false,
      build(body) {
        const field = sheetField(body, "YOUR NAME");
        const input = el("input");
        input.type = "text";
        input.placeholder = who.fallback || "Your name";
        field.appendChild(input);
        body.appendChild(
          el("p", "mono", "Every scene save and publish is signed with this name."),
        );
        return () => {
          const value = input.value.trim() || who.fallback;
          return value ? { name: value } : null;
        };
      },
    });
    await window.fivehub.login(values.name);
    name = values.name;
  }
  userPill.textContent = name;
  userPill.classList.remove("hidden");
}

async function newProjectSheet() {
  const values = await openSheet({
    title: "New project",
    submitLabel: "CREATE",
    build(body) {
      const nameField = sheetField(body, "NAME");
      const nameInput = el("input");
      nameInput.type = "text";
      nameInput.placeholder = "e.g. Orbital";
      nameField.appendChild(nameInput);

      // Where the project lives: hub by default, or any folder the user
      // picks (shared drive, synced repo, a spot on their disk).
      const locationField = sheetField(body, "WHERE THE PROJECT LIVES");
      let location = null;
      const locationRow = el("div", "form-row");
      const locationLabel = el("span", "mono", "Hub default (projects/ inside the hub)");
      locationLabel.style.flex = "1";
      const pickFolderBtn = el("button", "btn", "CHOOSE FOLDER");
      pickFolderBtn.addEventListener("click", async () => {
        const picked = await window.fivehub.pickFolder();
        if (picked) {
          location = picked;
          locationLabel.textContent = picked;
        }
      });
      locationRow.appendChild(locationLabel);
      locationRow.appendChild(pickFolderBtn);
      locationField.appendChild(locationRow);

      const imageField = sheetField(body, "IMAGE");
      let image = null;
      const imageRow = el("div", "form-row");
      const imageLabel = el("span", "mono", "Optional — a placeholder is generated");
      imageLabel.style.flex = "1";
      const pickImageBtn = el("button", "btn", "CHOOSE IMAGE");
      pickImageBtn.addEventListener("click", async () => {
        const picked = await window.fivehub.pickImage();
        if (picked) {
          image = picked;
          imageLabel.textContent = picked;
        }
      });
      imageRow.appendChild(imageLabel);
      imageRow.appendChild(pickImageBtn);
      imageField.appendChild(imageRow);

      return () => {
        const name = nameInput.value.trim();
        if (!name) return null;
        return { name, image, location };
      };
    },
  });
  if (!values) return;
  try {
    await window.fivehub.projectCreate(values.name, values.image, values.location);
    toast("PROJECT CREATED");
    await load();
  } catch (error) {
    toast(cliErrorText(error).toUpperCase());
  }
}

document.getElementById("new-project").addEventListener("click", newProjectSheet);

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

  const head = el("div", "card-head");
  head.appendChild(el("div", "name", project.name));
  head.appendChild(
    dotsButton(() => [
      { label: "Open", action: () => window.fivehub.openProject(project.name) },
      { label: "Reveal files", action: () => window.fivehub.reveal(project.path) },
      "-",
      project.external
        ? {
            label: "Unlink from hub",
            danger: true,
            action: async () => {
              const ok = await confirmSheet(
                `Unlink ${project.name}?`,
                "The project disappears from the hub. Its files at " +
                  project.path + " are kept.",
                "UNLINK",
              );
              if (!ok) return;
              await window.fivehub.projectRemove(project.name, false);
              toast("PROJECT UNLINKED");
              load();
            },
          }
        : {
            label: "Delete project",
            danger: true,
            action: async () => {
              const ok = await confirmSheet(
                `Delete project ${project.name}?`,
                "Every asset, shot, scene and publish in it is removed from disk. This cannot be undone.",
                "DELETE PROJECT",
              );
              if (!ok) return;
              await window.fivehub.projectRemove(project.name, true);
              toast("PROJECT DELETED");
              load();
            },
          },
    ]),
  );
  node.appendChild(head);

  const counts = project.counts || {};
  const bits = [
    `${counts.assets || 0} ASSETS`,
    `${counts.shots || 0} SHOTS`,
    `${counts.publishes || 0} PUBLISHES`,
  ];
  if (project.external) bits.push("LINKED");
  node.appendChild(el("div", "meta", bits.join(" · ")));
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
      const blobs = el("div", "blobs");
      for (let i = 0; i < 4; i += 1) blobs.appendChild(el("span"));
      box.appendChild(blobs);
      box.appendChild(el("div", null, "No projects yet"));
      box.appendChild(el("div", null, "Create one — or seed the demo"));
      const buttons = el("div", "row");
      const createBtn = el("button", "btn solid", "NEW PROJECT");
      createBtn.addEventListener("click", newProjectSheet);
      const demoBtn = el("button", "btn", "SEED DEMO PROJECT");
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
      buttons.appendChild(createBtn);
      buttons.appendChild(demoBtn);
      box.appendChild(buttons);
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

ensureLogin().then(load);
