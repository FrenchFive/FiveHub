// Library window — the hub grid. Click a card to open its asset window.

const assetsBox = document.getElementById("assets");
const searchInput = document.getElementById("search");
const projectSelect = document.getElementById("project");

let allAssets = [];

function matches(asset) {
  const term = searchInput.value.trim().toLowerCase();
  const project = projectSelect.value;
  if (project && asset.project !== project) return false;
  if (term && !asset.name.toLowerCase().includes(term)) return false;
  return true;
}

function card(asset) {
  const node = el("div", "card");
  if (asset.thumbnail) {
    const img = el("img", "thumb");
    img.src = window.fivehub.fileUrl(asset.thumbnail);
    img.alt = asset.name;
    node.appendChild(img);
  } else {
    node.appendChild(el("div", "thumb empty", "NO CAPTURE"));
  }
  node.appendChild(el("div", "name", asset.name));
  const bits = [];
  if (asset.project) bits.push(asset.project);
  if (asset.latest_version) bits.push("V" + String(asset.latest_version).padStart(3, "0"));
  if (asset.variants?.length > 1) bits.push(asset.variants.length + " VARIANTS");
  node.appendChild(el("div", "meta", bits.join(" · ") || "—"));
  node.addEventListener("click", () => window.fivehub.openAsset(asset.name));
  return node;
}

function render() {
  clear(assetsBox);
  const visible = allAssets.filter(matches);
  document.getElementById("count").textContent =
    visible.length + " / " + allAssets.length + " ASSETS";

  if (!allAssets.length) {
    const box = el("div", "empty-state");
    box.appendChild(el("div", null, "NOTHING PUBLISHED YET"));
    box.appendChild(el("div", null, "PUBLISH FROM HOUDINI — OR SEED THE DEMO"));
    const demoBtn = el("button", "btn solid", "PUBLISH DEMO ASSETS");
    demoBtn.addEventListener("click", async () => {
      demoBtn.textContent = "PUBLISHING…";
      try {
        await window.fivehub.demo();
        await load();
        toast("DEMO PUBLISHED — ONE PASS · ONE FAIL IN THE LOG");
      } catch (error) {
        toast("DEMO FAILED");
        showError(assetsBox, error);
      }
    });
    box.appendChild(demoBtn);
    assetsBox.appendChild(box);
    return;
  }

  const grid = el("div", "grid");
  for (const asset of visible) grid.appendChild(card(asset));
  assetsBox.appendChild(grid);
}

async function load() {
  try {
    const [rootInfo, listing, projects] = await Promise.all([
      window.fivehub.root(),
      window.fivehub.list(),
      window.fivehub.projects(),
    ]);
    document.getElementById("hub-path").textContent = rootInfo.root;
    allAssets = listing.assets;

    const current = projectSelect.value;
    clear(projectSelect);
    projectSelect.appendChild(el("option", null, "ALL PROJECTS")).value = "";
    for (const project of projects.projects) {
      const option = el("option", null, project.toUpperCase());
      option.value = project;
      projectSelect.appendChild(option);
    }
    projectSelect.value = current;
    render();
  } catch (error) {
    showError(assetsBox, error);
  }
}

searchInput.addEventListener("input", render);
projectSelect.addEventListener("change", render);
document.getElementById("refresh").addEventListener("click", load);

load();
