"""The FIVE HUB Houdini splash screen.

Generates the launch artwork Houdini shows when the pipeline is installed
(the package points HOUDINI_SPLASH_FILE at the output): goop metaballs in
the house style, FIVE HUB in Satoshi Black, and the facts of the session —
FiveHub version, Houdini build, license type, signed-in artist.

Three ways to regenerate:

    python -m fivehub.cli splash --houdini 20.0.345 --license FX
    FIVE HUB > Pipeline Tools > "Regenerate FiveHub Splash"   (reads the
        real build + license from the running session)
    fivehub.tools.splash.render(...) from any script

Requires Pillow (pip install pillow) and the Satoshi fonts — drop them in
assets/fonts/ (free at fontshare.com; see assets/fonts/README.md). Without
Satoshi it falls back to DejaVu so the pipeline never blocks on a font.
"""

import math
import os

from . import cli_command, houdini_tool
from .. import __version__, config

WIDTH, HEIGHT = 1200, 675

INK = (11, 11, 12)
WASH = (245, 245, 247)
GOOP = (228, 228, 232)
GRAY = (110, 110, 115)

# The goop: (x, y, radius) in a 1200x675 frame, one field, merged edges.
# Centers sit far enough apart that lobes stay readable, close enough that
# liquid necks form between them.
BLOBS = [
    (905, 155, 116), (1100, 275, 96), (868, 372, 90),
    (1030, 470, 76), (1180, 110, 64), (748, 268, 52), (940, 545, 40),
]
# A second light cluster bleeding in from the top-left corner.
BLOBS_CORNER = [(60, -40, 120), (215, 20, 74), (150, 130, 52), (305, 95, 30)]
INK_BLOBS = [(688, 448, 30), (645, 495, 17), (728, 511, 12)]
GOOP_THRESHOLD = 1.22

# Floating bits: hairline rings and satellite dots (x, y, radius).
RINGS = [(618, 108, 42), (762, 196, 16), (1168, 452, 26)]
DOTS_GRAY = [(576, 448, 8), (498, 96, 6), (1108, 545, 7)]
DOTS_INK = [(1002, 168, 13), (388, 486, 5)]

# The ink band along the bottom: Houdini draws its own version, license
# and loading text over the splash — this gives that overlay a home and
# keeps it readable whatever build the artist launches.
BAND_HEIGHT = 108


def _font_dirs():
    dirs = [os.environ.get("FIVEHUB_FONTS", "")]
    dirs.append(os.path.join(config.repo_root(), "assets", "fonts"))
    dirs.append(os.path.join(os.path.expanduser("~"), ".fivehub", "fonts"))
    return [d for d in dirs if d and os.path.isdir(d)]


def _find_font(*keywords):
    for directory in _font_dirs():
        for base, _dirs, files in os.walk(directory):
            for name in sorted(files):
                lowered = name.lower()
                if not lowered.endswith((".otf", ".ttf")):
                    continue
                if "italic" in lowered:
                    continue
                if all(keyword.lower() in lowered for keyword in keywords):
                    return os.path.join(base, name)
    return None


def _load_fonts(sizes):
    """{'black': font, 'medium': ..., 'regular': ...} at requested sizes,
    Satoshi first, DejaVu as the never-fail fallback."""
    from PIL import ImageFont

    fallback_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    fallback = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    paths = {
        "black": _find_font("satoshi", "black") or fallback_bold,
        "medium": _find_font("satoshi", "medium") or fallback,
        "regular": _find_font("satoshi", "regular") or fallback,
    }
    fonts = {}
    for role, size in sizes.items():
        base_role = role.split("@")[0]
        try:
            fonts[role] = ImageFont.truetype(paths[base_role], size)
        except OSError:
            fonts[role] = ImageFont.load_default()
    return fonts, paths


def _field(x, y, blobs):
    total = 0.0
    for bx, by, radius in blobs:
        dx, dy = x - bx, y - by
        d2 = dx * dx + dy * dy
        if d2 < 1.0:
            d2 = 1.0
        total += (radius * radius) / d2
    return total


def _goop_layer(width, height, blobs, threshold=1.0, edge=0.08):
    """Grayscale metaball mask with a smooth (anti-aliased) edge."""
    from PIL import Image

    scale_x = width / float(WIDTH)
    scale_y = height / float(HEIGHT)
    scaled = [(bx * scale_x, by * scale_y, r * scale_x) for bx, by, r in blobs]
    mask = bytearray(width * height)
    low, high = threshold - edge, threshold + edge
    index = 0
    for y in range(height):
        for x in range(width):
            value = _field(x, y, scaled)
            if value <= low:
                index += 1
                continue
            if value >= high:
                mask[index] = 255
            else:
                t = (value - low) / (high - low)
                mask[index] = int(255 * t * t * (3 - 2 * t))  # smoothstep
            index += 1
    return Image.frombytes("L", (width, height), bytes(mask))


def _tracked_text(draw, xy, text, font, fill, tracking=0):
    x, y = xy
    for character in text:
        draw.text((x, y), character, font=font, fill=fill)
        box = draw.textbbox((0, 0), character, font=font)
        x += (box[2] - box[0]) + tracking
    return x


def _pill(draw, x, y, text, font, filled=False, pad_x=22, height=46):
    box = draw.textbbox((0, 0), text, font=font)
    text_width = box[2] - box[0]
    width = text_width + pad_x * 2
    radius = height // 2
    if filled:
        draw.rounded_rectangle((x, y, x + width, y + height), radius, fill=INK)
        color = (255, 255, 255)
    else:
        draw.rounded_rectangle(
            (x, y, x + width, y + height), radius, outline=(0, 0, 0, 60), width=2
        )
        color = INK
    draw.text(
        (x + pad_x, y + (height - (box[3] - box[1])) / 2 - box[1]),
        text, font=font, fill=color,
    )
    return x + width


def render(out_path, houdini_version="", license_type="", user="", hub="",
           width=WIDTH, height=HEIGHT):
    """Render the splash PNG.

    The default art bakes NO Houdini version or license — Houdini itself
    overlays the launching build's version, license and loading text on
    the splash, over the ink band at the bottom. Pass ``houdini_version``
    / ``license_type`` only when you deliberately want them in the art.
    """
    from PIL import Image, ImageDraw

    fonts, font_paths = _load_fonts(
        {"black": int(height * 0.265), "black@brand": int(height * 0.054),
         "medium": int(height * 0.034), "regular@pill": int(height * 0.030),
         "regular@small": int(height * 0.023)}
    )
    scale = height / float(HEIGHT)

    image = Image.new("RGB", (width, height), WASH)

    # Goop fields: big cluster right, corner cluster top-left, ink drip.
    goop = Image.new("RGB", (width, height), GOOP)
    image.paste(goop, (0, 0), _goop_layer(width, height, BLOBS, GOOP_THRESHOLD))
    image.paste(goop, (0, 0), _goop_layer(width, height, BLOBS_CORNER, 1.1))
    ink_goop = Image.new("RGB", (width, height), INK)
    image.paste(ink_goop, (0, 0), _goop_layer(width, height, INK_BLOBS))

    draw = ImageDraw.Draw(image)
    margin = int(90 * scale)

    # Floating bits — rings and satellite dots.
    ring_width = max(2, int(3 * scale))
    for x, y, radius in RINGS:
        box = tuple(int(v * scale) for v in (x - radius, y - radius,
                                             x + radius, y + radius))
        draw.ellipse(box, outline=(200, 200, 205), width=ring_width)
    for dots, color in ((DOTS_GRAY, (208, 208, 213)), (DOTS_INK, INK)):
        for x, y, radius in dots:
            box = tuple(int(v * scale) for v in (x - radius, y - radius,
                                                 x + radius, y + radius))
            draw.ellipse(box, fill=color)

    # Small FIVE HUB (Satoshi Black, ink) over a big "Houdini" —
    # it is Houdini being launched; FIVE HUB is the suit it wears.
    _tracked_text(
        draw, (margin, int(118 * scale)), "FIVE HUB",
        fonts["black@brand"], INK, tracking=int(7 * scale),
    )
    draw.text((margin - int(10 * scale), int(155 * scale)), "Houdini",
              font=fonts["black"], fill=INK)

    _tracked_text(
        draw, (margin, int(388 * scale)), "RUNNING THE FIVE HUB PIPELINE",
        fonts["medium"], GRAY, tracking=int(8 * scale),
    )

    # Our facts as pills. Houdini's own version/license text is overlaid
    # by Houdini in the band below — only bake it when explicitly asked.
    pill_font = fonts["regular@pill"]
    pill_y = int(460 * scale)
    x = margin
    x = _pill(draw, x, pill_y, "FIVEHUB %s" % __version__, pill_font) + int(14 * scale)
    if houdini_version:
        x = _pill(draw, x, pill_y, "HOUDINI %s" % houdini_version,
                  pill_font) + int(14 * scale)
    if license_type:
        _pill(draw, x, pill_y, license_type.upper(), pill_font, filled=True)

    # Ink band: Houdini overlays its version/license/loading text here
    # (bottom-left) — our credits sit right-aligned, out of its way.
    band_top = height - int(BAND_HEIGHT * scale)
    draw.rectangle((0, band_top, width, height), fill=INK)
    small = fonts["regular@small"]
    lines = ["FIVE HUB — pipeline for houdini"]
    facts = "validated usd publishes · versioned scenes · signed work"
    if user:
        facts = "signed in — %s · %s" % (user, facts)
    if hub:
        facts += " · %s" % hub
    lines.append(facts)
    y = band_top + int(26 * scale)
    for line in lines:
        box = draw.textbbox((0, 0), line, font=small)
        draw.text((width - margin - (box[2] - box[0]), y), line,
                  font=small, fill=(200, 200, 205))
        y += int(30 * scale)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(out_path, "PNG")
    return {"path": out_path, "size": [width, height],
            "satoshi": "satoshi" in os.path.basename(font_paths["black"]).lower()}


def default_output():
    return os.path.join(config.repo_root(), "houdini", "splash", "fivehub_splash.png")


def _detect_houdini_version():
    hfs = os.environ.get("HFS", "")
    base = os.path.basename(hfs.rstrip("/\\"))
    return base.replace("hfs", "") if base.startswith("hfs") else ""


def _configure(parser):
    parser.add_argument("--houdini", default="", help="e.g. 20.0.345 (auto from $HFS)")
    parser.add_argument("--license", default="", help="FX / CORE / INDIE / NC / ...")
    parser.add_argument("--user", default="", help="artist name shown as signed in")
    parser.add_argument("--hub", default="", help="hub path shown in the footer")
    parser.add_argument("--out", default="", help="output PNG (default: package splash)")
    parser.add_argument("--if-missing", action="store_true",
                        help="only render when the output file does not exist")


@cli_command("splash", "regenerate the FIVE HUB Houdini splash screen", _configure)
def run(_root, args):
    out_path = args.out or default_output()
    if args.if_missing and os.path.isfile(out_path):
        return {"path": out_path, "skipped": "already exists"}
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("the splash generator needs Pillow: pip install pillow")
    return render(
        out_path,
        houdini_version=args.houdini or _detect_houdini_version(),
        license_type=args.license,
        user=args.user,
        hub=args.hub,
    )


@houdini_tool("Regenerate FiveHub Splash")
def regenerate_from_session():
    """Refresh the splash with this artist's login and hub. The Houdini
    build and license are NOT baked — Houdini overlays the launching
    session's own version text on the splash, so the art always matches
    whatever build starts up."""
    import hou

    try:
        import PIL  # noqa: F401
    except ImportError:
        hou.ui.displayMessage(
            "The splash generator needs Pillow in Houdini's python:\n"
            "hython -m pip install pillow",
            severity=hou.severityType.Error, title="FIVE HUB",
        )
        return None

    from ..user import get_user

    result = render(default_output(), user=get_user(), hub=config.ensure_hub())
    hou.ui.displayMessage(
        "Splash regenerated — it shows on the next Houdini launch.\n"
        "(Houdini draws its own version and license text over the band.)\n%s"
        % result["path"],
        title="FIVE HUB",
    )
    return result
