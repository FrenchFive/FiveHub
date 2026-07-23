# FiveHub

**A USD asset publishing pipeline for Houdini** — validated publishes, versioned USD component assets, and a standalone black & white asset browser.

FiveHub 2.0 is a full rework. Assets are no longer serialized Houdini python; every publish now produces a proper, DCC-agnostic **USD component asset**, and every publish is gated by a **validation pass** with a pass/fail report.

## SUMMARY :
- [ARCHITECTURE](#architecture-) — how assets are stored
- [VALIDATION](#validation-) — what gets checked on publish
- [THE APP](#the-app-) — the standalone Electron UI
- [SETUP](#setup-) — install into Houdini
- [USAGE](#usage-) — publish / browse / import
- [CLI](#cli-) — scripting surface
- [DEVELOPMENT](#development-) — tests, demo data

------

## ARCHITECTURE :

### USD component structure

Each publish writes the standard component-asset layer stack:

```
hub/
├── assets/
│   └── WoodenCrate/
│       ├── WoodenCrate.usda            ← root interface, always tracks the latest publish
│       ├── v001/                       ← immutable version
│       │   ├── WoodenCrate.usda        ← entry layer
│       │   ├── WoodenCrate.payload.usda
│       │   ├── WoodenCrate.geo.usda    ← geometry layer
│       │   ├── WoodenCrate.mtl.usda    ← material layer (UsdPreviewSurface)
│       │   ├── thumbnails/WoodenCrate.png
│       │   └── report.json             ← the validation report that let it through
│       └── v002/ ...
├── db/fivehub.db                       ← SQLite index (assets / versions / publish log)
├── reports/                            ← reports of failed publish attempts
└── exchange/                           ← app ⇄ Houdini handoff (import selection)
```

The entry layer is a real component asset interface:

- `kind = "component"`, `assetInfo` (name, version, identifier)
- **payload arc** — geometry stays out of composition until loaded
- **geo / mtl layer split** — the payload composes the material layer *over* the geometry layer; per-face assignments become `materialBind` GeomSubsets
- **variants** — a `geo` variantSet; publishing variant `damaged` of an existing asset composes older variants from their own versions (nothing is copied)
- **thumbnail baked into the asset** via `AssetPreviewsAPI` (`previews:thumbnails:default:defaultImage`), plus `extentsHint` for cheap bounds

Everything is authored as plain `usda` with zero dependencies, so the pipeline runs inside Houdini, in CI, or standalone.

### Storage

The old one-table database is replaced by `asset` / `version` / `publish_log` tables (per-operation connections, foreign keys, UTC timestamps). Every publish attempt — including blocked ones — is recorded in the log with its report.

## VALIDATION :

Publishing runs a rule chain against the DCC-neutral geometry model. **Errors block the publish**; warnings are recorded in the report.

| Rule | Checks | Severity |
|---|---|---|
| `naming.asset` | asset name is a valid USD identifier, not reserved | ERROR |
| `naming.style` | UpperCamelCase asset style | WARNING |
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
| `asset.thumbnail` | a capture was taken | WARNING |

Severities and tolerances are overridable per publish (`publish(request, rule_config={"geo.unwelded": {"severity": "warning"}})`).

The report (JSON + rendered) is stored **inside the version directory** for successful publishes and under `reports/` for blocked ones.

## THE APP :

The UI is no longer dialogs inside Houdini — it is a standalone **Electron app** with separate windows:

- **LIBRARY** — search, project filter, thumbnail grid
- **ASSET** — one window per asset: versions, variants, send-to-Houdini, reveal, copy USD path
- **VALIDATION** — one window per report: PASSED/FAILED verdict and the full rule breakdown

Pure black `#000` and pure white `#fff` only — hairline borders, uppercase tracking, inversion on hover, slow liquid easing. No grays, no color.

The app contains no pipeline logic: it shells out to `python -m fivehub.cli` (JSON), so disk and database have a single implementation.

```
cd app
npm install
npm start
```

Set `FIVEHUB_PYTHON` if your python binary isn't `python3`/`python`.

## SETUP :

1. Clone wherever you want the pipeline to live:
   ```
   git clone https://github.com/FrenchFive/FiveHub.git
   ```
2. Install the Houdini package (writes one JSON file into your prefs, no `houdini.env` editing):
   ```
   python houdini/install.py
   ```
   It lists the Houdini preference folders it finds — pick one, done. Uninstall = delete `<prefs>/packages/fivehub.json`.
3. (Optional, for the app) `cd app && npm install`
4. Launch Houdini — the **FIVE HUB** shelf appears.

The hub root defaults to `<repo>/hub`; point `FIVEHUB_ROOT` at a shared location for team use.

## USAGE :

- **PUBLISH** (shelf) — select geo objects (or SOPs), fill in name / project / variant / comment. The viewport is framed and captured (and restored afterwards), geometry and materials (`shop_materialpath`, principled shader parameters) are extracted, validation runs, and you get the pass/fail report. Blocked publishes write nothing to `assets/`.
- **HUB** (shelf) — opens the Electron app.
- **IMPORT** (shelf) — references the asset staged by the app's *SEND TO HOUDINI* button (or a file chooser) into `/stage` (Solaris), falling back to a SOP USD import.

## CLI :

Every command prints JSON:

```
python -m fivehub.cli list                 # assets with latest version + thumbnail
python -m fivehub.cli show WoodenCrate     # versions, variants, layers
python -m fivehub.cli report WoodenCrate --version 2
python -m fivehub.cli log                  # publish history incl. blocked attempts
python -m fivehub.cli send WoodenCrate     # stage for the Houdini IMPORT tool
python -m fivehub.cli demo                 # seed demo publishes (one deliberately fails)
python -m fivehub.cli --hub /mnt/pipeline list
```

## DEVELOPMENT :

```
python -m unittest discover -s tests -v    # 23 tests, no external deps
python -m fivehub.cli demo                 # demo data for the app
```

Publishing from other DCCs = produce `MeshData`/`PublishRequest` (see `fivehub/geometry.py`) and call `fivehub.publish()` — validation and USD authoring are DCC-free.

## UPCOMING :
- [ ] UV / texture export into the mtl layer
- [ ] Proxy purpose geometry (viewport LODs)
- [ ] Per-asset tags in the app
