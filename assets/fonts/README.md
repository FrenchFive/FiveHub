# FIVE HUB fonts — Satoshi

The project typeface is **Satoshi** (Indian Type Foundry, free via
Fontshare). **FIVE HUB titles always use Satoshi Black**; UI text uses
Regular/Medium/Bold.

The font files are **not committed** — Fontshare's Free Font License
allows using Satoshi in products, rendered images and self-hosted
webfonts, but not redistributing the font files themselves.

## Set it up (once per machine / per clone)

1. Download the family free at <https://www.fontshare.com/fonts/satoshi>
   (or `curl -L -o satoshi.zip https://api.fontshare.com/v2/fonts/download/satoshi`).
2. Drop into this folder:
   - `Satoshi-Variable.woff2` (or `.ttf`) — the app's webfont
   - `Satoshi-Black.otf`, `Satoshi-Medium.otf`, `Satoshi-Regular.otf` —
     used by the splash generator
3. Install the OTFs system-wide too, so the Qt windows inside Houdini
   pick the family up.

Everything degrades gracefully without Satoshi: the app falls back to the
system stack, the Qt windows to the OS font, and the splash generator to
DejaVu — nothing breaks, it just isn't wearing the brand.
