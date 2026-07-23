# FiveHub

**A project-based USD pipeline for Houdini teams** — projects, assets & shots with tasks, versioned work scenes, validated multi-format publishes, ingest, references, dependency-tracked shot assembly, and a render worker. Built for 1–10 artists on a shared server, for commercials and small films.

## SUMMARY :
- [THE PIPELINE](#the-pipeline-) — projects → entities → tasks → scenes → publishes
- [MULTI-USER & SERVER](#multi-user--server-) — what makes it safe on a share
- [INSIDE HOUDINI](#inside-houdini-) — the FIVE HUB menu
- [VALIDATION](#validation-) — what gates a publish
- [USD STRUCTURE](#usd-structure-) — component assets, animation, assemblies
- [INGEST & REFERENCES](#ingest--references-)
- [RENDERING](#rendering-) — jobs, worker, dailies
- [THE APP](#the-app-) — the standalone UI
- [SETUP](#setup-) — install script & deployment
- [CLI](#cli-) — scripting surface
- [DEVELOPMENT](#development-)

------

## THE PIPELINE :

```
hub/                                    ← FIVEHUB_ROOT (put it on the server share)
├── projects/<Project>/                 ← or anywhere, via the registry (LINKED)
│   ├── project.json                    ← identity + project defaults (fps, res, range)
│   ├── project.db                      ← per-project database
│   ├── image.png · refs/ · reports/ · .trash/
│   ├── assets/<Asset>/<task>/
│   │   ├── scenes/<Asset>_<task>_v###.hip
│   │   ├── caches/                     ← working sim caches ($FH_CACHES)
│   │   ├── render/
│   │   └── publish/<format>/v###/      ← usd · bgeo · vdb · obj · hda · fbx · abc · tex · render
│   └── shots/<Shot>/<task>/            ← same layout; shots carry sequence,
│                                          frame range, fps and resolution
├── exchange/<user>/                    ← per-artist handoff (no collisions)
├── registry.json                       ← projects living outside the hub
└── backups/
```

- **Projects** are created in the app with a name, an image, and **where they live** (hub default or any folder — shared drive, synced repo). Each project owns its SQLite database.
- **Shots carry metadata**: sequence grouping plus frame range / fps / resolution (project defaults, editable per shot). Houdini applies them on load; renders read them.
- **Scenes** are versioned per task with notes — every save and publish is **signed** by the logged-in artist and timestamped.
- **Publishes** are versioned per task *and format*; USD is the default and produces a full component asset. Deletion is **soft**: history stays in the database and files move to the project `.trash`.

## THREE WAYS TO RUN :

FiveHub is the same tool in all three — pick per project, mix freely:

| Mode | Setup | How work is shared |
|---|---|---|
| **Local** | none — clone, install, go. The hub defaults to `<repo>/hub` | it isn't — solo work, full pipeline |
| **Server** | point every machine's `FIVEHUB_ROOT` at a share | live: claims + presence + shared DB on the share |
| **Git** | put a project in a repo (⋯ → *Set up Git*, or `git-setup`) | pull/push: **SYNC** in the app (`git-sync` = commit → pull --rebase → push → apply pulled records) |

What makes git mode work: **the database is a local cache**. Every entity, task, scene, publish and dependency is mirrored as a tiny JSON *record sidecar* under `.fivehub/records/` — one file per record, so **git merges them without conflicts**. `project.db` is gitignored and rebuilds itself from the records whenever they change (after a pull, on a fresh clone, or via `fivehub rebuild`). A generated `.gitignore` keeps caches, renders, trash and the DB out of the repo; publishes and scenes are tracked (use git-lfs for heavy binaries if you like). On git projects, publishes and scene saves **auto-commit** with signed messages (`[fivehub] publish usd v003 Crate/modeling — Ana`; disable with `"git_autocommit": false` in `project.json`); pushing stays a deliberate SYNC. Two artists claiming the same version *offline* can't be prevented without a server — sync reports those rare collisions explicitly instead of hiding them.

## MULTI-USER & SERVER :

Built so several artists on one share cannot hurt each other:

- **Atomic version claims** — scene and publish numbers are reserved in the database (UNIQUE-constraint claim) *before* any file is written. Two artists saving the same task get v004 and v005, never a silent overwrite. Failed writes release their claim and clean up.
- **Network-filesystem-safe SQLite** — per-operation connections, DELETE journal (WAL is unsafe on NFS/SMB), busy timeout and retry-with-backoff.
- **Relative paths in the database** — a hub mounted at `/mnt/hub`, `Z:\hub` and `/Volumes/hub` at the same time keeps working; paths resolve per machine.
- **Per-user exchange** — staged imports and viewport captures live under `exchange/<user>/`.
- **Presence** — opening/saving a scene marks the task "in use by <name>"; the app shows it on task chips and in the task window. Advisory, not a hard lock.
- **Soft delete + trash** — nothing is ever hard-deleted from the UI; `fivehub trash <project> --empty --days 30` purges.
- **Schema migrations** — databases carry a version and upgrade in place.
- **Backups** — `python -m fivehub.cli backup` snapshots every project DB (SQLite backup API) + the registry into `hub/backups/<stamp>/`; run it from cron on the server.

## INSIDE HOUDINI :

| Menu item | What it does |
|---|---|
| **Save Scene As... / Increment Save** | Claim-safe versioned saves with notes; binds `$JOB` + `FH_*` vars to the project, applies shot range/fps, updates presence |
| **Load Scene...** | Browse versions with notes; same context binding on open |
| **Publish Selection...** | Context locked from the saved scene. Formats: **USD** (full validation, UVs + principled-shader textures carried), **BGEO / VDB / OBJ** (single frame or **frame-range sequences**), **HDA** (the selected node's definition library). ANIMATED toggle bakes the frame range — USD gets time-sampled points |
| **Load Published Asset... / Import Staged** | Reference publishes (USD → `/stage`, sequences → `$F4` File SOPs, HDA → install). Every import is **tracked as a dependency** — pinned when you pick a version, following-latest when you take the root layer |
| **Submit Render...** | Pick a ROP (from `/out` and `/stage`) + range (prefilled from the shot) → queued as a job for the FiveHub worker |
| **Publish Shot Assembly** | One USD layer referencing everything this task imported — the whole shot in a single file |
| **Open Hub App / Reload Pipeline** | |

## VALIDATION :

Errors block the publish; warnings are recorded. Reports are stored with the version (blocked attempts go to `reports/`), signed with who + when.

| Rule | Checks | Severity |
|---|---|---|
| `naming.*` | asset/variant/mesh/material identifiers, UpperCamelCase style | ERROR / style WARNING |
| `geo.empty` / `geo.unwelded` / `geo.degenerate` | faces exist · no coincident points · no broken faces | ERROR |
| `geo.unused` | no points detached from faces | WARNING |
| `scale.units` / `scale.bounds` / `scale.size` / `scale.origin` | sane units · non-degenerate · 1mm–100m · near origin | ERROR / WARNING |
| `mtl.missing` / `mtl.unknown` | every face bound · every bound material shipped | ERROR |
| `mtl.textures` | referenced texture files exist | ERROR |
| `anim.topology` | animated meshes keep constant topology | ERROR |
| `asset.thumbnail` | a capture was taken | WARNING |
| files: `files.exist` / `files.format` | files exist & non-empty · extensions match format | ERROR / WARNING |

## USD STRUCTURE :

Every USD publish is a component asset in dependency-free `usda`: entry layer (`kind = "component"`, `assetInfo`, `extentsHint`, thumbnail via `AssetPreviewsAPI`), **payload arc inside a `geo` variantSet**, **geo/mtl split**. Lookdev is real now: **`st` UVs**, and principled-shader textures are **collected into the publish** and authored as `UsdUVTexture` networks (diffuse / roughness / metallic / normal). Animated publishes carry **time-sampled points** with the range in the layer metadata. Shot assemblies are `kind = "assembly"` layers referencing the tracked imports — pinned dependencies reference exact versions, unpinned ones follow each asset's root interface.

## INGEST & REFERENCES :

- **INGEST FILES** (task window, or `fivehub ingest ...`): drop vendor FBX / Alembic / USD kits / textures / caches into a task — validated, versioned, signed, same as any publish. Formats are inferred from extensions; mixed drops are rejected with a clear message.
- **REFERENCES** (project window): a per-project gallery under `refs/` for boards, briefs and style frames — add via file picker, view images inline, trash via ⋯.

## RENDERING :

1. **Submit** from Houdini (menu) or `fivehub render <project> shot SH010 lighting 3 /out/karma1` — range/fps come from the shot.
2. **Worker** — run `python -m fivehub.cli worker` on the server (or any Houdini machine; several workers coexist, jobs are claimed atomically). It opens the scene in `hython` (set `FIVEHUB_HYTHON` if not on PATH), drives the ROP, and registers the frames as a **render publish** (`publish/render/v###/`).
3. **Dailies** — when `ffmpeg` is on the worker, an encode job follows automatically and writes `preview.mp4` next to the frames.
4. The app's **JOBS** section shows queue state per project; queued jobs can be cancelled.

## THE APP :

Mainly white, black ink, red only for critical/destructive (see [STYLEGUIDE.md](STYLEGUIDE.md)). Separate windows, auto-refreshing every 30s so you see teammates' work land:

- **LOGIN** — a name that signs everything.
- **PROJECTS** — cards with image/counts; NEW PROJECT sheet (name, **location**, image); ⋯ open/reveal/unlink/delete.
- **PROJECT** — scoped to one project: **search**, ASSETS and SHOTS (**grouped by sequence**, frame ranges shown, **presence dots** on task chips), entity sheets with task toggles + **shot metadata editing**, **REFERENCES** gallery, **JOBS**, and the activity feed.
- **TASK** — scenes (icon-only **Open in Houdini** launching with `$JOB` set, ⋯ edit/delete), publishes with **thumbnails**, BY/PUBLISHED columns, **INGEST FILES**, and a **DEPENDENCIES** panel (uses / used-by, pinned vs latest, "v005 AVAILABLE" nudges).
- **VALIDATION** — verdict + rule breakdown, signed.

Package installers: `cd app && npm install && npm run dist` (electron-builder → dmg/nsis/AppImage in `app/dist`).

## SETUP :

One step. Clone, then:

- **Windows** — double-click **`install.bat`** (or run it in any shell)
- **macOS / Linux** — `./install.sh`

That's the whole install. It sets up, best-effort with a clear summary (a
failed step never blocks the rest): the **Houdini package** into every
Houdini preferences folder found (menu + shelf + splash; delete
`packages/fivehub.json` to uninstall), the **Houdini binary location**
(recorded in `~/.fivehub/machine.json` so the app's open/launch buttons
work with zero setup — if it ever goes missing the app asks you to point
at houdini once and remembers), **Pillow**, the **Satoshi fonts**
(downloaded from Fontshare into `assets/fonts/` — your download, never
shipped in the repo), the generated **splash screen**, and the **app
dependencies** (`npm install`, when Node.js is present).

Then launch Houdini — the FIVE HUB menu is in the main menu bar, and the
HUB button opens the app (first launch asks your name; that's the login).
On Windows the installer also adds **FiveHub to the Start Menu** (with the
goop icon), so Windows search finds it; Linux gets an applications-menu
entry. Rerun `install.bat` once after the first `npm install` if the
shortcut step reported a skip.

**Updating is one click.** FiveHub installs by reference to its git clone,
so an update is one `git pull` — and the app handles it: windows open
immediately while a background check runs (at boot, then every 5 minutes),
and when a newer version is tagged on `main` a small popup offers it —
**UPDATE** pulls and restarts the app, **LATER** dismisses it until the
next launch. The **UPDATE — vX.Y.Z** button stays in the header the whole
time an update exists. Houdini has **FIVE HUB ▸ Check for Updates**; after
an update, restart Houdini (or Reload Pipeline for python-only changes).
Every update (and every installer run) re-renders the splash art, so
Houdini always launches with the latest FIVE HUB look.
Manual: `python -m fivehub.cli update [--check]`. Server deployments
update once for everyone — pull the shared clone. Set
`FIVEHUB_NO_AUTOUPDATE=1` to mute the popup (the button still works).
Files the installer generates on your machine (`app/package-lock.json`,
the splash PNG) are gitignored, so the clone stays clean and pullable —
never commit them.

**Uninstall / reset.** `uninstall.bat` (Windows) / `./uninstall.sh`
removes everything the installer set up — the Houdini package, the Start
Menu shortcut, app dependencies, the generated splash, the downloaded
fonts and the login — and never touches your projects. **`reset.bat` /
`./reset.sh` is a factory reset: uninstall + fresh install in one go**
(close the app and Houdini first; Windows keeps their files locked).
To also erase the hub with every project in it, run
`python uninstall.py --purge-hub` — it asks you to type ERASE, and
linked project folders outside the hub are always kept.

For teams: point every machine's `FIVEHUB_ROOT` at the shared hub, and on
the server run a cron for `python -m fivehub.cli backup` plus
`python -m fivehub.cli worker` as a service for renders. Manual installs
remain available (`python houdini/install.py [--auto|--prefs <dir>]`).

Env vars: `FIVEHUB_ROOT` (hub), `FIVEHUB_USER` (identity override), `FIVEHUB_HOUDINI` (GUI binary for the app's open buttons), `FIVEHUB_HYTHON` (worker), `FIVEHUB_PYTHON` (app→CLI bridge).

## CLI :

```
login / whoami / projects / project-create [--location] / project-remove
entity-create|update|delete  (--sequence --frame-start --frame-end --fps --res-x --res-y)
task-create / task-delete / browse / task-info
send / activity / log / report --path
ingest <project> <kind> <entity> <task> <files...>
refs <project> [--add ...|--delete NAME]
scene-notes / scene-delete / publish-comment / publish-delete
render <project> <kind> <entity> <task> <scene_version> <rop> [--start --end --step]
jobs <project> [--cancel ID]     worker [--project] [--once]
assemble <project> <entity> <task>
trash <project> [--empty --days N]     backup     demo
```

Every command prints JSON; `--hub` overrides the root.

## EXTENDING — YOUR HDAS & TOOLS :

FiveHub is the base; the pipeline grows by dropping things in, never by editing core:

- **Pipeline HDAs** → drop `.hda` files into `houdini/otls/`. They load in every session automatically (the folder is on Houdini's HDA scan path via the package). Commit them; teammates get them on next launch/pull. Build your custom FileCache here whenever it outgrows the Python version.
- **Project HDAs** → publish them (format `hda`) into the show; FiveHub **auto-installs a project's latest HDA publishes** when you open one of its scenes — show tools follow the show.
- **Python tools** → add a module in `fivehub/tools/`. Decorators plug it into every surface, no registration files:
  - `@houdini_tool("Label")` → appears under **FIVE HUB ▸ Pipeline Tools...**
  - `@cli_command("name", "help", configure)` → becomes a `fivehub.cli` subcommand (and is reachable from the app)
  - `@validation_rule` → joins the USD publish gate
  - `@job_handler("type")` → executed by the worker
  A broken tool is reported and skipped — it never takes the pipeline down.
- **The shipped example** is exactly the cache workflow: `fivehub/tools/cachepath.py` defines the cache nomenclature (`<task>/caches/<name>/v###/<Entity>_<task>_<name>_v###.$F4.bgeo.sc`), exposes it as `cache-path` on the CLI, and registers **Create Pipeline File Cache** — a filecache SOP dropped after your selection, pre-pointed at `$FH_CACHES` (which FiveHub binds to the scene's task on load/save).

## DEVELOPMENT :

```
python -m unittest discover -s tests -v    # 68 tests, no external deps
python -m fivehub.cli demo                 # demo project for the app
```

**Versioning is automatic.** Every merge to `main` bumps the version by the
size of the change (`.github/workflows/version-bump.yml` →
`scripts/bump_version.py`): under 100 changed lines = patch (+0.0.1),
under 500 = minor (+0.1.0), 500 and up = major (+1.0.0). The bot commit
updates `fivehub/__init__.py` + `app/package.json` and tags `vX.Y.Z` —
never edit the version by hand.

Core is dependency-free Python; the app shells out to the CLI so storage has one implementation. Houdini modules are compile-checked in CI-less environments — exercise them with a `hython` smoke run studio-side.

## UPCOMING :
- [ ] Proxy purpose geometry (viewport LODs) and instanceable assembly refs
- [ ] Deadline/Tractor adapter as an alternative to the built-in worker
- [ ] Review page for dailies (per-shot mp4 playlist)
