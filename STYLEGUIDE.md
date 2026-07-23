# FIVEHUB STYLE GUIDE

The single source of truth for how anything FiveHub looks and behaves —
the Electron app, the Qt windows inside Houdini, and any surface added
later. If a screen doesn't follow this document, the screen is wrong.

Implementation of these tokens lives in:
- `app/renderer/style.css` — the web/Electron implementation
- `houdini/fivehub_windows.py` (`STYLE`) — the Qt/QSS implementation

------

## 1. PHILOSOPHY

**Mainly white.** Artists stare at dark viewports all day; FiveHub is the
calm, bright surface next to them. White cards float on a soft wash.
Black is *ink* — text, emphasis, the primary action — never the ground.

**Red means stop.** One accent, `#FF3B30`, and it is rationed. Red says
"this publish did not make it" and nothing else. If red appears more than
once on a healthy screen, something is misdesigned.

**Rounded and liquid.** Nothing snaps. Surfaces are continuous rounded
cards, controls are pills, and every interaction moves on a spring —
things lift when considered, compress when pressed, and settle softly.
Metaballs are the decorative signature: soft blobs that merge like
droplets, always ambient, never carrying information.

**Calm data.** The pipeline is dense (versions, tasks, reports); the UI
compensates with generosity — one idea per card, row separators instead
of grids of lines, secondary facts in gray.

## 2. COLOR

| Token | Value | Role |
|---|---|---|
| `--wash` | `#F5F5F7` | Window background. Everything floats on this. |
| `--surface` | `#FFFFFF` | Cards, sheets, tables, dialogs. |
| `--ink` | `#0B0B0C` | Text, primary buttons, the FAILED verdict card. |
| `--ink-2` | `#6E6E73` | Secondary text: labels, paths, timestamps. |
| `--fill` | `#F2F2F3` | Filled controls: inputs, chips, quiet pills. |
| `--line` | `rgba(0,0,0,.08)` | Hairlines, card borders, row separators. |
| `--line-strong` | `rgba(0,0,0,.16)` | Focus borders, outlined status pills. |
| `--red` | `#FF3B30` | **Critical only.** See the red rules below. |

### The red rules

Red is allowed in exactly four places:

1. The **FAIL** status pill on a blocked publish.
2. **Error-severity** rule failures inside a validation report
   (status pill + severity tag). Warning failures stay monochrome.
3. The **blocked-publish verdict** — rendered as the one black card in
   the system (`--ink` ground, red type), so black exists to showcase red.
4. **Destructive actions**: delete/unlink items inside ⋯ menus and the
   confirm button of a destructive sheet — red marks the point of no return.

Red is never used for: hover states, selection, branding, icons,
decorations, warnings, links, or anything that is not a blocking problem
or an irreversible action. When in doubt: not red.

### Grays

Grays are only for *content* (grayscale-filtered thumbnails and captures)
and for the secondary-ink/hairline tokens above. Never introduce new gray
values; pick a token.

## 3. TYPOGRAPHY

System stack, Apple-first:
`-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
Monospace for paths and file names: `"SF Mono", "Cascadia Mono", Consolas, monospace`.

| Role | Size / weight | Treatment |
|---|---|---|
| Title (`.title`) | 32px / 700 | Tight tracking (−0.02em), true case ("DemoCrate / modeling") |
| Brand (`.brand`) | 15px / 700 | "FIVEHUB", slight positive tracking |
| Body | 13–14px / 400–500 | True case, never uppercase |
| Label (`.label`) | 10px / 600 | UPPERCASE, +0.12em tracking, `--ink-2` — the *only* uppercase role besides buttons |
| Button text | 11px / 600 | UPPERCASE, +0.06em |
| Mono (`.mono`) | 11px | Paths, filenames, IDs |

Data names (assets, tasks, users) always render in their true case.
Numbers that align in columns get `font-variant-numeric: tabular-nums`.

## 4. SHAPE & ELEVATION

| Token | Value | Used for |
|---|---|---|
| `--radius-lg` | 20px | Cards, tables, sheets (sheets go to 24px) |
| `--radius-md` | 14px | Thumbnails, project images |
| `--radius-sm` | 10px | Inputs, Qt fields |
| pill | 999px | Buttons, chips, status pills, toasts |
| `--shadow-soft` | 2-layer, ≤ .05 alpha | Resting cards |
| `--shadow-lift` | 2-layer, ≤ .09 alpha | Hovered cards, sheets, toasts |

Borders are always the hairline token — never solid black outlines.
Shadows are diffuse and gray, never colored.

## 5. MOTION

Two curves, used everywhere:

| Token | Curve | Meaning |
|---|---|---|
| `--spring` | `cubic-bezier(0.32, 0.72, 0, 1)` | Settle: hovers, fades, sheets sliding in |
| `--pop` | `cubic-bezier(0.34, 1.4, 0.64, 1)` | Overshoot: presses, toasts, playful arrivals |

Rules:
- Hover = **lift** (translateY(−1..3px) + shadow bloom). Never color inversion.
- Press = **compress** (`scale(0.96)`, 80ms). Everything tappable compresses.
- Enter = rise + settle (`opacity` + `translateY`), staggered ~60ms per sibling.
- Sheets scale from 0.96 with `--pop`; their overlay fades with `--spring`.
- Everything respects `prefers-reduced-motion: reduce` — animation off, function intact.

### Metaballs

The gooey signature: circles blurred and contrast-thresholded through the
shared SVG filter (`#goo`), drifting on slow alternating keyframes.
- Ambient only: empty states, mastheads, quiet backgrounds.
- Never behind or on top of text, data, or controls (`pointer-events: none`, behind content).
- Blob color is `--fill` — they read as soft liquid, not decoration-noise.

## 6. COMPONENTS

- **Buttons** — pills. Default: white, hairline, ink text. Primary
  (`.btn.solid`): ink ground, white text — at most one primary per view.
  Round `+` buttons (`.btn.round`) are the only entry to creation flows.
  **Icon buttons** (`.btn.icon`) are circular and glyph-only with a
  tooltip — the Houdini launch is just the swirl, nothing more.
- **Overflow menus (⋯)** — every row and card keeps at most one visible
  primary action; everything secondary (copy, reveal, edit, send) lives
  behind a ⋯ button (`dotsButton`) that opens a popover menu. Destructive
  entries sit last, below a separator, in red (red rule 4), and always go
  through a confirm sheet with a red confirm button (`.btn.danger`).
- **Sheets** — all creation and input happens in modal sheets (centered
  card, dimmed blurred backdrop). Never inline input rows in lists;
  a `+` opens a sheet with everything that creation needs. Escape and
  backdrop-click dismiss (except the login sheet).
- **Chips** — pill facts (tasks with `S/P` counts). Toggle chips fill
  with ink when on. The dashed `+ TASK` chip opens the task sheet.
- **Tables** — rounded white shells, row separators only (no vertical
  grid lines), uppercase gray column heads, wash-tint row hover.
- **Status pills** — PASS: outlined, monochrome. FAIL: red (rule 1).
- **Toast** — one floating dark pill, bottom center, pops in with
  `--pop`, gone in ~2.6s. Confirmations only, never errors that need reading.
- **User pill** — the signed-in identity, dot + name, in the header.
- **Houdini glyph** — the monochrome swirl (`houdiniGlyph()` in
  `common.js`) marks every "opens Houdini" action; it inherits
  `currentColor` and never gets its own color.

## 7. QT (INSIDE HOUDINI)

The QSS in `fivehub_windows.py` mirrors the tokens: `#F5F5F7` dialog
ground, white rounded fields (10px), pill buttons (16px radius), ink
primary button, and **red only on the "VALIDATION FAILED" heading**.
When adding a Qt widget, translate the web token — don't invent values.

## 8. COPY

- Buttons say exactly what happens: "VALIDATE + PUBLISH", then the toast
  confirms in past tense.
- Labels name what artists recognize (WORK SCENES, PUBLISHES, ACTIVITY),
  not internals.
- Errors state what's wrong and the fix, without apology:
  "Project 'X' does not exist. Create projects in the hub app first."
- Timestamps are short (`2026-07-23 14:02`); users are names, not IDs.

## 9. DO / DON'T

- **Do** keep every screen scoped: inside a project, show only that
  project's entities, tasks and activity.
- **Do** use the wash for grounds and white for content — never white on white without a hairline.
- **Don't** use red for anything that isn't a blocking failure.
- **Don't** add inline creation inputs — `+` → sheet, always.
- **Don't** introduce new colors, radii, shadows, fonts or curves —
  extend the token set deliberately or don't.
- **Don't** put information in metaballs, or metaballs on information.
