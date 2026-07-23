# FiveHub

**A project-based USD publishing pipeline for Houdini** — projects, assets & shots with tasks, versioned work scenes, validated multi-format publishes, and a standalone hub app in a mainly-white black & white design with a rare red accent.

## SUMMARY :
- [THE PIPELINE](#the-pipeline-) — projects → entities → tasks → scenes → publishes
- [INSIDE HOUDINI](#inside-houdini-) — the FIVE HUB menu
- [VALIDATION](#validation-) — what gates a publish
- [USD STRUCTURE](#usd-structure-) — what a publish looks like on disk
- [THE APP](#the-app-) — the standalone Electron UI
- [SETUP](#setup-) — install script
- [CLI](#cli-) — scripting surface
- [DEVELOPMENT](#development-) — tests, demo data

------

## THE PIPELINE :

```
hub/
└── projects/
    └── <Project>/                      ← created in the hub app (name + image)
        ├── project.json                ← identity card
        ├── project.db                  ← per-project database
        ├── image.png                   ← project image
        ├── reports/                    ← reports of blocked publishes
        ├── assets/                     ← entities of kind "asset"
        │   └── <Asset>/
        │       └── <task>/             ← modeling / rig / lookdev / fx / ...
        │           ├── scenes/         ← versioned work scenes
        │           │   ├── <Asset>_<task>_v001.hip
        │           │   └── <Asset>_<task>_v002.hip
        │           └── publish/
        │               ├── usd/        ← USD component publishes (default)
        │               │   ├── <Asset>.usda      ← root interface, tracks latest
        │               │   └── v001/ v002/ ...
        │               └── vdb/ bgeo/ obj/       ← file-format publishes
        └── shots/                      ← entities of kind "shot", same layout
```

- **Projects** are created in the hub app with a name and an image; every project gets **its own SQLite database** (`project.db`) holding its assets, shots, tasks, scenes and publish history.
- **Assets and shots** are created per project; **tasks** (any identifier — modeling, rig, lookdev, fx, animation, environment, ... are suggested) are created per entity.
- **Scenes** are versioned `.hip` files owned by a task. Every save records version, notes and user; the current scene's context is recovered from its path, so increment-save and publish know where they are.
- **Publishes** are versioned per task *and per format*. USD is the default and produces a full component asset; `vdb` / `bgeo` / `obj` publish the selection's geometry as validated file drops.

## INSIDE HOUDINI :

After install, a **FIVE HUB** menu sits in Houdini's main menu bar:

| Menu item | What it does |
|---|---|
| **Save Scene As...** | FiveHub window: pick project → asset/shot → task (new entities/tasks can be typed in place), add notes → saves `<Entity>_<task>_v###.hip` and records it |
| **Increment Save** | Detects the current scene's context, asks for notes, saves the next version |
| **Load Scene...** | Browse projects → entities → tasks → versions with notes, opens the picked scene |
| **Publish Selection...** | FiveHub window: context (prefilled from the scene), publish name, **format (USD default / VDB / BGEO / OBJ)**, variant, comment → runs validation → pass/fail report window. Errors block the publish |
| **Load Published Asset...** | Browse publishes of any task and import: USD → Solaris `/stage` reference (SOP fallback), file formats → File SOPs |
| **Import Staged From Hub** | Imports whatever the hub app staged via SEND TO HOUDINI |
| **Open Hub App** | Launches the standalone Electron app |
| **Reload Pipeline** | Developer helper |

All FiveHub windows inside Houdini are Qt (PySide2/PySide6), parented to the main window and styled in the same mainly-white, rounded language as the app — the accent red appears only on a blocked validation. A shelf with SAVE + / PUBLISH / IMPORT / HUB mirrors the most-used actions.

## VALIDATION :

Publishing runs a rule chain against a DCC-neutral geometry model. **Errors block the publish**; warnings are recorded. The report (JSON + rendered) is stored inside the publish version — blocked attempts land in the project's `reports/` and in its publish log instead.

| Rule | Checks | Severity |
|---|---|---|
| `naming.asset` | publish name is a valid USD identifier, not reserved | ERROR |
| `naming.style` | UpperCamelCase name style | WARNING |
| `naming.variant` / `naming.meshes` / `naming.materials` | identifiers valid & unique | ERROR |
| `geo.empty` | meshes exist and have faces | ERROR |
| `scale.units` | `metersPerUnit` / `upAxis` sane | ERROR |
| `scale.bounds` | bounding box not degenerate | ERROR |
| `scale.size` | asset between 1 mm and 100 m | WARNING |
| `scale.origin` | asset sits near the world origin | WARNING |
| `geo.unwelded` | no coincident (unfused) points | ERROR |
| `geo.unused` | no points detached from faces | WARNING |
| `geo.degenerate` | no <3-vertex / zero-area / self-indexed faces | ERROR |
| `mtl.missing` | every face has a material assigned | ERROR |
| `mtl.unknown` | every bound material ships with the publish | ERROR |
| `asset.thumbnail` | a viewport capture was taken | WARNING |

File-format publishes (vdb/bgeo/obj) run the light chain: naming, `files.exist` (ERROR), `files.format` extension match (WARNING), thumbnail. Severities and tolerances are overridable per publish.

## USD STRUCTURE :

Every USD publish is a proper component asset, authored as dependency-free `usda`:

- entry layer: `kind = "component"`, `assetInfo`, `extentsHint`, **thumbnail baked in** via `AssetPreviewsAPI`
- **payload arc inside a `geo` variantSet** — geometry stays out of composition until loaded; publishing variant `damaged` composes older variants from their own versions (nothing copied)
- **geo / mtl layer split** — materials (UsdPreviewSurface, sampled from principled shaders) composed *over* geometry; per-face assignments become `materialBind` GeomSubsets
- a root interface (`publish/usd/<Name>.usda`) regenerated on each publish so downstream references always track the latest version of every variant — pin by referencing a `v###` entry directly

## THE APP :

Standalone Electron app, separate windows. Mainly white, black ink, easy on artists' eyes: white cards on a soft `#F5F5F7` wash, rounded corners and pill controls, Apple-spring motion with metaball ambience — and **red (`#FF3B30`) reserved for critical states only** (blocked publishes, error-level rule failures). The full design contract lives in [STYLEGUIDE.md](STYLEGUIDE.md).

- **LOGIN** — first launch asks for a name (that's the whole login); every scene save and publish is **signed with that name and timestamped** for traceability. Change it any time with `fivehub.cli login`.
- **PROJECTS** — project cards with image and counts. **NEW PROJECT opens a sheet**: name, **where the project lives** (hub default, or any folder — shared drive, synced repo, a spot on your disk; external projects are tracked in the hub registry and marked LINKED), and an image.
- **PROJECT** — one window per project, and **everything in it is scoped to that project**: ASSETS and SHOTS columns with round `+` buttons (each opens a creation sheet — entity name plus the tasks to set up as toggles), task chips with scene/publish counts, and a project-only ACTIVITY feed (recent publishes and scene saves, blocked ones in red).
- **TASK** — one window per task: work scene versions with notes/user/date and an **OPEN IN HOUDINI** button per version (launches Houdini with that exact scene — set `FIVEHUB_HOUDINI` if the binary isn't on PATH); publishes with format/version/variant, PASS/FAIL status, report, SEND TO HOUDINI, copy paths.
- **VALIDATION** — one window per report: verdict plus the full rule breakdown.

All creation flows live in modal sheets (never inline inputs); `+` always opens a sheet. The app owns no pipeline logic — every action shells out to `python -m fivehub.cli` (JSON), so disk and databases have a single implementation.

```
cd app
npm install
npm start
```

Set `FIVEHUB_PYTHON` if your python binary isn't `python3` / `python`.

## SETUP :

1. Clone wherever the pipeline should live:
   ```
   git clone https://github.com/FrenchFive/FiveHub.git
   ```
2. Run the install script:
   ```
   python houdini/install.py
   ```
   It finds your Houdini preference folders and writes a single package file (`packages/fivehub.json`) — no `houdini.env` editing. The package adds `$FIVEHUB/houdini` to `HOUDINI_PATH`, which brings in the **FIVE HUB menu**, the shelf and the python modules. Delete the JSON to uninstall.
3. (For the app) `cd app && npm install`
4. Launch Houdini — FIVE HUB appears in the main menu bar.

The hub root defaults to `<repo>/hub`; point `FIVEHUB_ROOT` at a shared location for team use (Houdini and the app both respect it).

## CLI :

Every command prints JSON:

```
python -m fivehub.cli login "Ana"                 # signs your saves + publishes
python -m fivehub.cli whoami
python -m fivehub.cli projects
python -m fivehub.cli project-create Mars --image poster.png
python -m fivehub.cli project-create Orbital --location /mnt/shared   # external project
python -m fivehub.cli entity-create Mars asset Rover
python -m fivehub.cli task-create Mars asset Rover modeling
python -m fivehub.cli browse Mars
python -m fivehub.cli task-info Mars asset Rover modeling
python -m fivehub.cli send Mars asset Rover modeling --format usd
python -m fivehub.cli activity Mars               # project-scoped recent activity
python -m fivehub.cli log Mars
python -m fivehub.cli report --path <report.json>
python -m fivehub.cli demo
python -m fivehub.cli --hub /mnt/pipeline projects
```

## DEVELOPMENT :

```
python -m unittest discover -s tests -v    # 33 tests, no external deps
python -m fivehub.cli demo                 # demo project for the app
```

Publishing from scripts = build a `PublishRequest` (USD) or `FilePublishRequest` (files) and call `fivehub.publish_usd()` / `fivehub.publish_files()` on a `Project` — validation and USD authoring are DCC-free.

## UPCOMING :
- [ ] UV / texture export into the mtl layer
- [ ] Proxy purpose geometry (viewport LODs)
- [ ] Scene thumbnails in the task window
