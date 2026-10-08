#!/usr/bin/env python3
"""Build recipes/index.html — every shipped recipe, what a recipe is made of, and one
scene through many films — from the filmcam repo's own catalogue and render pipeline.

Usage (from the repository root):
  python3 tools/build_recipes.py --sync    # pull catalogue data + render/encode every image
  python3 tools/build_recipes.py           # write recipes/index.html from the synced data
  python3 tools/build_recipes.py --check   # verify data, images and that the page is current

--sync needs the filmcam repo (default ~/personal/filmcam, or `filmcam` in config.json, or
--filmcam PATH) plus the owner's same-frame exports (default ~/Downloads/samples, or --frames
PATH: "No look <NNNN>.JPG" beside "<Recipe Name>[ on Roll] <NNNN>.JPG" exports of one frame).
It builds the app's FilmKit package with tools/siterender/ added (the anatomy pairs are real
renders through the app's own graph, never CSS), converts the app's bundled samples, and
strips EXIF/XMP from every output. Build and --check need only this repository.
Needs swift, sips, ffmpeg and exiftool for --sync; only the standard library otherwise.
"""
import csv
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_home import FORBIDDEN as HOME_FORBIDDEN, BuildError, jpeg_size, load_occasions

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "recipes/data/catalogue.json"
DATA_VI = ROOT / "recipes/data/catalogue.vi.json"
STRINGS_VI = ROOT / "recipes/data/strings.vi.csv"
IMG = ROOT / "img/recipes"
PAGE = ROOT / "recipes/index.html"
PAGE_VI = ROOT / "vi/recipes/index.html"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

# The homepage's list, plus names the recipe exports brushed against. The two custom-recipe
# frames ship as "FC200" and "ClassicNeg" (the owner's display names); the full names never do.
FORBIDDEN = HOME_FORBIDDEN + ["fujicolor", "classic negative", "gold max"]

# ---------------------------------------------------------------------------- sync

def cfg_filmcam(argv):
    for i, a in enumerate(argv):
        if a == "--filmcam" and i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    return Path(cfg.get("filmcam", "~/personal/filmcam")).expanduser()


def frames_dir(argv):
    for i, a in enumerate(argv):
        if a == "--frames" and i + 1 < len(argv):
            return Path(argv[i + 1]).expanduser()
    return Path("~/Downloads/samples").expanduser()


def run(*args):
    subprocess.run([str(a) for a in args], check=True, capture_output=True)


def strip_meta(path):
    run("exiftool", "-all=", "-overwrite_original", path)


def encode(src, dest, vf, q):
    dest.parent.mkdir(parents=True, exist_ok=True)
    run(FFMPEG, "-loglevel", "error", "-y", "-i", src, "-vf", vf, "-q:v", str(q), "-map_metadata", "-1", dest)
    strip_meta(dest)


def heic_jpeg(src, dest, long_edge, quality):
    dest.parent.mkdir(parents=True, exist_ok=True)
    run("sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality), "-Z", str(long_edge), src, "--out", dest)
    strip_meta(dest)


# The film border a Roll export carries: the canvas grows by these margins, the photo
# pixels stay 1:1 (verified against the neutral frame), so cropping them off leaves
# every export the same 3024x2016 scene. A further inset clears the border art's
# rounded photo corners. Measured for the current iPhone exports — when the base scene
# is reshot at another resolution, re-verify these two constants against the new
# "No look" frame (a 50/50 blend of the assumed offsets shows misalignment at once).
BORDER = (15, 10)
INSET = 112, 75, 2800, 1866   # x, y, w, h: a centred 3:2 window inside the content

# The two files the owner asks onto the scene strip under coined display names — his own
# custom recipes, built in the app's recipe builder, not part of the shipped catalogue.
# An explicit map, so nothing else ever rides in on a loosened name filter.
CUSTOM_DISPLAY = {"fujicolor c200": "FC200", "classic negative": "ClassicNeg"}

# Recipes whose bundled app sample the site must not show: their cards get the recipe
# rendered over the shared no-face frame instead — through the app's own pipeline at the
# sample strength, never a substitute grade. Empty today, by the owner's decision: the
# portrait recipes stand on his own portraits, and a street frame with people small in it
# (Nightshade 800, Underpass 400) is shown as the app shows it.
FACE_SAMPLES = set()

# The anatomy renders tools/siterender/main.swift writes, in card order (see SLIDER_CARDS).
ANATOMY_SLUGS = ["neutral", "film", "wb", "highlight", "shadow", "colour", "chrome", "dr",
                 "exposure", "clarity", "sharpness", "grain", "halation", "vignette"]
# Output widths, sized for what the page actually draws at 2x DPR, never past the source.
# Anatomy cards top out around 336 CSS px on desktop (three columns) and ~370 on a phone,
# so 700/1400 covers 2x everywhere — each rendered natively so effects stay true to size.
# The hero and the scene stage draw at up to 1080 CSS px (the wrap), so 2160 is their 2x;
# the exports' usable crop is 2800 px wide, so nothing upscales.
ANATOMY_EDGES = (700, 1400)
STAGE_WIDTHS = (1080, 2160)
HERO_WIDTHS = (800, 1600, 2160)


def normalised(name):
    """A same-frame export's name, ready to match: lower-case, ' on roll' dropped."""
    name = name.lower().strip()
    return re.sub(r"\s+on roll$", "", name)


def sans_iso(name):
    return re.sub(r"\s+\d+$", "", name)


def match_export(name, recipes, films):
    """The shipped recipe or film an export names, tolerant of ISO-number suffixes."""
    n = normalised(name)
    for r in recipes:
        if r["name"].lower() == n:
            return "recipe", r
    for r in recipes:
        if sans_iso(r["name"].lower()) == sans_iso(n):
            return "recipe", r
    for fid, fname in films.items():
        if fname.lower() == n:
            return "film", fid
    return None, None


def render_harness(filmcam, out):
    """Copy the app's FilmKit package (symlinks resolved), add tools/siterender/ as an
    executable target, build it, and run it: the catalogue dump, every film's palette
    line and the anatomy pairs all come out of the app's own code."""
    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "pkg"
        pkg.mkdir()
        run("cp", "-RL", filmcam / "FilmKit/Package.swift", filmcam / "FilmKit/Sources", pkg)
        manifest = (pkg / "Package.swift").read_text(encoding="utf-8")
        manifest = re.sub(r"\n\s*\.testTarget\([^)]*\),", "", manifest)
        manifest = manifest.replace(
            '.executable(name: "filmfit", targets: ["FilmFitCLI"]),',
            '.executable(name: "filmfit", targets: ["FilmFitCLI"]),\n        .executable(name: "siterender", targets: ["SiteRenderCLI"]),')
        manifest = manifest.replace(
            '.executableTarget(name: "FilmFitCLI", dependencies: ["FilmKit"]),',
            '.executableTarget(name: "FilmFitCLI", dependencies: ["FilmKit"]),\n        .executableTarget(name: "SiteRenderCLI", dependencies: ["FilmSample", "FilmKit"]),')
        (pkg / "Package.swift").write_text(manifest, encoding="utf-8")
        shutil.copy(ROOT / "tools/siterender/SiteDump.swift", pkg / "Sources/FilmSample/SiteDump.swift")
        (pkg / "Sources/SiteRenderCLI").mkdir()
        shutil.copy(ROOT / "tools/siterender/main.swift", pkg / "Sources/SiteRenderCLI/main.swift")
        subprocess.run(["swift", "build", "-c", "release", "--package-path", str(pkg)], check=True, capture_output=True)
        run(pkg / ".build/release/siterender",
            "--frame", neutral_frame(frames_dir(sys.argv[1:]))[0],
            "--luts", filmcam / "App/Resources/LUTs",
            "--characters", filmcam / "App/Resources/Characters",
            "--out", out, "--reference", "neg1998", "--longEdge", "1200",
            "--longEdges", ",".join(str(e) for e in ANATOMY_EDGES),
            *(["--looks", ",".join(sorted(FACE_SAMPLES))] if FACE_SAMPLES else []))


def neutral_frame(frames):
    """The one "No look <NNNN>.JPG" in the exports folder, and its frame number — the whole
    page regenerates from whatever frame the owner shoots next; nothing is tied to 0788."""
    hits = sorted(frames.glob("No look *.JPG"))
    numbered = [(h, m.group(1)) for h in hits if (m := re.fullmatch(r"No look (\d{3,4})", h.stem))]
    if len(numbered) != 1:
        raise BuildError(f"expected exactly one 'No look <NNNN>.JPG' in {frames}, found {len(numbered)}")
    return numbered[0]


def sync(argv):
    filmcam = cfg_filmcam(argv)
    frames = frames_dir(argv)
    if not filmcam.is_dir():
        raise BuildError(f"filmcam repo not found at {filmcam} (config.json `filmcam` or --filmcam PATH)")
    neutral, frame_no = neutral_frame(frames)

    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        render_harness(filmcam, work)
        looks = json.loads((work / "catalogue.json").read_text(encoding="utf-8"))
        pal = json.loads((work / "palettes.json").read_text(encoding="utf-8"))
        for slug in ANATOMY_SLUGS:
            for edge in ANATOMY_EDGES:
                q = (5 if edge == 700 else 6) if slug == "grain" else (6 if edge == 700 else 7)
                encode(work / f"anatomy/{slug}-{edge}.jpg", IMG / f"anatomy/{slug}-{edge}.jpg", "null", q)

        # Card text from the app's own records; `inspiredBy` (real stock names) is read
        # around, never out — nothing below touches it. The owner's Vietnamese for the same
        # records (localized.vi) is collected alongside, for the /vi/recipes/ page.
        recipes = []
        vi_looks, vi_films = {}, {}
        for look in looks:
            meta = json.loads((filmcam / f"App/Resources/LookMetadata/{look['id']}.json").read_text(encoding="utf-8"))
            film_id = look["filmCharacter"]
            film_meta = json.loads((filmcam / f"App/Resources/FilmMetadata/{film_id}.json").read_text(encoding="utf-8"))
            if look["id"] in FACE_SAMPLES:
                encode(work / f"looks/{look['id']}.jpg", IMG / f"samples/{look['id']}.jpg",
                       "scale=800:-2:flags=lanczos", 6)
            else:
                sample = filmcam / f"App/Resources/Samples/{meta['sampleID']}.heic"
                heic_jpeg(sample, IMG / f"samples/{look['id']}.jpg", 800, 62)
            look_vi = meta.get("localized", {}).get("vi", {})
            vi_looks[look["id"]] = {"description": look_vi.get("description", ""),
                                    "guidance": look_vi.get("guidance", "")}
            if film_id not in vi_films:
                vi_films[film_id] = film_meta.get("localized", {}).get("vi", {}).get("description", "")
            recipes.append({
                "id": look["id"], "name": look["name"],
                "film": {"id": film_id, "name": pal["names"][film_id], "palette": pal["palettes"][film_id],
                         "line": film_meta["description"]},
                "description": meta["description"], "guidance": meta["guidance"],
                "grain": {"strength": look["grainStrength"], "large": look["grainLarge"]},
            })

        # The same-frame scene strip: the neutral capture, then every export that names a
        # shipped recipe or film, then the owner's two custom recipes under their display
        # names. Anything else in the folder is a personal recipe and is skipped.
        films = pal["names"]
        scene, matched, skipped = [], [], []
        x, y = BORDER
        ix, iy, iw, ih = INSET

        def scene_encode(src, slug, developed=True):
            cx, cy = (x + ix, y + iy) if developed else (ix, iy)
            for w in STAGE_WIDTHS:
                encode(src, IMG / f"scene/{slug}-{w}.jpg",
                       f"crop={iw}:{ih}:{cx}:{cy},scale={w}:-2:flags=lanczos", 7 if w <= 1080 else 10)

        scene_encode(neutral, "no-look", developed=False)
        for f in sorted(frames.glob("*.JPG")):
            if f == neutral:
                continue
            stem = re.sub(rf"\s+{frame_no}$", "", f.stem)
            if stem == f.stem:
                continue   # a different frame number: not this scene
            n = normalised(stem)
            if n in CUSTOM_DISPLAY:
                slug = CUSTOM_DISPLAY[n].lower()
                scene_encode(f, slug)
                scene.append({"slug": slug, "label": CUSTOM_DISPLAY[n], "custom": True})
                matched.append(f"{f.name} -> {CUSTOM_DISPLAY[n]} (custom)")
                continue
            kind, hit = match_export(stem, recipes, films)
            if kind == "recipe":
                scene_encode(f, hit["id"])
                scene.append({"slug": hit["id"], "label": hit["name"], "custom": False})
                hit["scene"] = True
                matched.append(f"{f.name} -> {hit['name']}")
            elif kind == "film":
                scene_encode(f, f"film-{hit}")
                scene.append({"slug": f"film-{hit}", "label": films[hit], "custom": False, "film": True})
                matched.append(f"{f.name} -> {films[hit]} (film)")
            else:
                skipped.append(f.name)
        order = {r["id"]: i for i, r in enumerate(recipes)}
        scene.sort(key=lambda s: (s["custom"], s.get("film", False), order.get(s["slug"], 99)))

        # The hero pair: the neutral capture against the owner's Toffee Neg Roll develop
        # of the same shutter press, border cropped so the two halves align exactly.
        toffee = frames / f"Toffee Neg on Roll {frame_no}.JPG"
        if not toffee.is_file():
            raise BuildError(f"hero develop missing: {toffee}")
        for w in HERO_WIDTHS:
            q = 4 if w <= 800 else (5 if w <= 1600 else 7)
            encode(neutral, IMG / f"hero/before-{w}.jpg", f"crop={iw}:{ih}:{ix}:{iy},scale={w}:-2:flags=lanczos", q)
            encode(toffee, IMG / f"hero/after-{w}.jpg", f"crop={iw}:{ih}:{x + ix}:{y + iy},scale={w}:-2:flags=lanczos", q)

    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps({"recipes": recipes, "scene": scene}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DATA_VI.write_text(json.dumps({"looks": vi_looks, "films": vi_films}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"build_recipes: synced {len(recipes)} recipes, {len(scene)} scene frames, "
          f"{len(ANATOMY_SLUGS)} anatomy renders")
    for line in matched:
        print("  " + line)
    for name in skipped:
        print(f"  skipped (not a shipped recipe): {name}")


# ---------------------------------------------------------------------------- page

def esc(s):
    return html.escape(str(s), quote=True)


def load_vi_strings():
    """recipes/data/strings.vi.csv — the owner's translations of the editorial layer,
    keyed exactly as the translation export keyed them."""
    if not STRINGS_VI.exists():
        raise BuildError(f"{STRINGS_VI.relative_to(ROOT)} is missing")
    with STRINGS_VI.open(encoding="utf-8-sig", newline="") as f:
        return {r["key"]: r["your_vietnamese"] for r in csv.DictReader(f)}


def load_catalogue_vi():
    """recipes/data/catalogue.vi.json — the app's own owner-reviewed Vietnamese for card
    descriptions, guidance lines and film lines (written by --sync from the filmcam repo)."""
    if not DATA_VI.exists():
        raise BuildError(f"{DATA_VI.relative_to(ROOT)} is missing; run --sync")
    return json.loads(DATA_VI.read_text(encoding="utf-8"))


def make_tr(lang, vi):
    """tr(key, en): the English source on the EN page; the owner's row on the VI page,
    failing loudly when a key is missing so a copy edit can't ship half-translated."""
    if lang == "en":
        return lambda key, en: en

    def tr(key, en):
        if key not in vi:
            raise BuildError(f"recipes/data/strings.vi.csv is missing key {key!r} (en: {en[:60]!r})")
        return vi[key]
    return tr


def make_label_tr(lang, vi):
    """Slider labels: translated when the export keyed them (prose like 'No film'),
    left as written when they are values ('+1.5', 'DR200')."""
    if lang == "en":
        return lambda key, en: en
    return lambda key, en: vi.get(key, en)


def grain_personality(g, tr=lambda key, en: en):
    n, large = g["strength"], g["large"]
    if n == 0:
        word = tr("grain.word.zero", "opens clean — grain is yours to dial")
    elif n <= 20:
        word = tr("grain.word.fine", "a fine, quiet grain")
    elif n <= 30:
        word = tr("grain.word.light", "a light grain that reads as film")
    elif n <= 45:
        word = (tr("grain.word.soft_present", "a soft, present grain") if large
                else tr("grain.word.present", "a present, honest grain"))
    else:
        word = tr("grain.word.coarse", "a coarse fast-film grain")
    size = tr("grain.large", "large") if large else tr("grain.small", "small")
    amount = tr("grain.off", "off") if n == 0 else f"{n} · {size}"
    return f'{tr("grain.label", "Grain")} {amount}', word


# What one anatomy card's image actually draws at: ~304 CSS px in the desktop three-column
# grid, ~44vw in two columns, the near-full phone width in one.
CARD_SIZES = "(min-width:1112px) 304px, (min-width:680px) 44vw, calc(100vw - 64px)"


def anatomy_img(slug, w, h, cls, alt, hidden=False):
    srcset = ", ".join(f"/img/recipes/anatomy/{slug}-{e}.jpg {e}w" for e in (700, 1400))
    a = 'alt="" aria-hidden="true"' if hidden else f'alt="{esc(alt)}"'
    return (f'<img class="{cls}" src="/img/recipes/anatomy/{slug}-700.jpg" srcset="{srcset}" '
            f'sizes="{CARD_SIZES}" width="{w}" height="{h}" {a} loading="lazy" decoding="async">')


def compare_html(before, after, alt, w, h, labels=("No recipe", "Recipe")):
    return (f'<div class="compare" style="aspect-ratio:{w}/{h}">'
            + anatomy_img(before, w, h, "compare-before", alt, hidden=True)
            + anatomy_img(after, w, h, "compare-after", alt)
            + f'<label class="compare-label"><span class="sr-only">{esc(alt)}</span>'
            f'<input type="range" min="0" max="100" value="50" aria-label="{esc(alt)}"></label>'
            f'<span class="compare-tag before">{esc(labels[0])}</span>'
            f'<span class="compare-tag after">{esc(labels[1])}</span></div>')


# One card per setting the in-app recipe builder writes into a recipe (the share format's
# own field list), with 1998 Neg as the reference recipe. Each slider pair is a real render
# of the same frame through the app's graph — the recipe's film alone against the film with
# exactly that one setting applied, at 1998 Neg's own authored value (tools/siterender reads
# the value from the shipped catalogue, so a retune re-renders truthfully; only Exposure,
# which 1998 Neg leaves at zero, shows a demonstrative value instead, and says so). The
# three below SLIDER_CARDS need light this scene does not have (or a face), so they stay
# in words rather than get a faked picture.
SLIDER_CARDS = [
    ("film", "Film character", "The stock everything else stands on: how each hue answers — what reds turn into, "
     "how skies and foliage lean, where the shadows fall. Afterglow Neg, the film 1998 Neg is built on, "
     "against the plain capture.", "neutral", "film", ("No film", "Afterglow Neg")),
    ("wb", "White balance", "Where white sits. A recipe can trust the camera, fix a kelvin, or shift the whole "
     "frame along red and blue — 1998 Neg trusts the camera and leans it toward yellow-green, R−2 B−4.",
     "film", "wb", ("As metered", "R−2 B−4")),
    ("highlight", "Highlight tone", "How hard the brightest parts climb. 1998 Neg pushes its top up a step and "
     "a half — the bright, forward top of a snapshot print — where a pulled-down top would roll off gently "
     "instead.", "film", "highlight", ("0", "+1.5")),
    ("shadow", "Shadow tone", "How deep the darks sit. Pushed up, shadows fall to black sooner and the frame "
     "gains weight — 1998 Neg takes them all the way to +3.", "film", "shadow", ("0", "+3")),
    ("colour", "Colour density", "How much of each colour the film lays down — 1998 Neg feeds the whole palette "
     "more dye, all the way up.", "film", "colour", ("0", "+4")),
    ("chrome", "Colour Chrome", "Depth in the strongest colours: saturated reds and blues gain density and "
     "shading instead of blowing flat. 1998 Neg carries the strong grade.", "film", "chrome", ("Off", "Strong")),
    ("dr", "Dynamic range", "The headroom kept for the highlights. At 1998 Neg's DR200 an extra stop of the "
     "brightest tones is held and rolled back down, the way a negative holds a bright sky.",
     "film", "dr", ("DR100", "DR200")),
    ("exposure", "Exposure", "A recipe can build in an exposure drop or lift, in thirds of a stop, under whatever "
     "you dial at the shutter. 1998 Neg builds in none, so this pair shows a demonstrative −2/3.",
     "film", "exposure", ("±0", "−2/3")),
    ("clarity", "Clarity", "Local contrast. Taken away, edges and textures soften into a bloom the way an old "
     "uncoated lens draws — 1998 Neg eases it three steps.", "film", "clarity", ("0", "−3")),
    ("sharpness", "Sharpness", "Fine detail at the pixel level. 1998 Neg eases it two steps for a gentler "
     "negative, where a raised step would make brickwork bite.", "film", "sharpness", ("0", "−2")),
    ("grain", "Grain", "The texture of the stock. 1998 Neg wears a light, fine grain — 25, small — that sits "
     "in the picture, not on it; watch it hold to the sky.", "film", "grain", ("Off", "25 · small")),
    ("halation", "Halation", "The red-orange glow film blooms around its brightest edges — sun on a facade, "
     "a bare bulb, light bounced back through the emulsion. 1998 Neg keeps it quiet, at 10.",
     "film", "halation", ("Off", "10")),
    ("vignette", "Vignette", "The frame's edges eased down, pulling the eye to the middle the way a fast lens "
     "wide open does — a gentle 10 here.", "film", "vignette", ("Off", "10")),
]

TEXT_CARDS = [
    ("Starburst", "Points of light drawn into stars, the way a stopped-down aperture flares a street lamp. "
     "It needs true points of light, so it shows at night rather than on this daylight scene.",
     "no picture — it needs lamps, not noon"),
    ("Protect skin", "Holds faces back from the film's strongest colour moves, so a bold palette does not "
     "walk over skin. It needs a face in frame to show itself.",
     "no picture — it needs a face, and this scene has none"),
    ("Film dials — Drift, Bleed, Compress", "Three dials on the film itself: Drift leans the whole character "
     "further its own way or back toward neutral, Bleed lets neighbouring colours cross-talk like dye layers "
     "do, and Compress fades the deepest shadows the way a print lifts them.",
     "three dials on the film itself"),
]


def swatches_html(palette):
    spans = "".join(f'<i style="background:{esc(c)}"></i>' for c in palette)
    return f'<span class="palette" aria-hidden="true">{spans}</span>'


# The hero and the scene stage both draw at the wrap's width: 1080 CSS px on desktop,
# the viewport minus the gutters below that.
STAGE_SIZES = "(min-width:1112px) 1080px, calc(100vw - 32px)"


def hero_section(dims, tr):
    w, h = dims[f"hero/after-{HERO_WIDTHS[-1]}.jpg"]
    before_set = ", ".join(f"/img/recipes/hero/before-{v}.jpg {v}w" for v in HERO_WIDTHS)
    after_set = ", ".join(f"/img/recipes/hero/after-{v}.jpg {v}w" for v in HERO_WIDTHS)
    alt = tr("hero.alt", "The same city frame twice: the plain capture, and the Toffee Neg develop of it")
    slider_label = tr("hero.slider_label", "Drag to compare the plain capture with the developed frame")
    slider = (f'<div class="compare" style="aspect-ratio:{w}/{h}">'
              f'<img class="compare-before" src="/img/recipes/hero/before-1600.jpg" '
              f'srcset="{before_set}" '
              f'sizes="{STAGE_SIZES}" width="{w}" height="{h}" alt="" aria-hidden="true" fetchpriority="high">'
              f'<img class="compare-after" src="/img/recipes/hero/after-1600.jpg" '
              f'srcset="{after_set}" '
              f'sizes="{STAGE_SIZES}" width="{w}" height="{h}" '
              f'alt="{esc(alt)}" fetchpriority="high">'
              f'<label class="compare-label"><span class="sr-only">{esc(slider_label)}</span>'
              f'<input type="range" min="0" max="100" value="50" aria-label="{esc(slider_label)}"></label>'
              f'<span class="compare-tag before">{esc(tr("hero.tag_before", "Straight off the phone"))}</span><span class="compare-tag after">Toffee Neg</span></div>')
    return f"""
  <section id="rc0" class="chapter rc-hero" data-chapter="rc0_hero">
    <div class="wrap">
      <p class="kicker">{esc(tr("hero.kicker", "Fonder · Recipes"))}</p>
      <h1>{esc(tr("hero.title", "What a recipe is"))}</h1>
      <p class="lead">{esc(tr("hero.lead", "A recipe is a film character and the darkroom decisions around it: where white sits, how hard the highlights climb, how much dye goes down, what texture the negative wears. One shutter press, developed two ways — drag the line."))}</p>
      {slider}
      <p class="note">{esc(tr("hero.note", "Both halves are the same phone capture. The right one went through a Fonder recipe — nothing here is a screen filter laid over a picture."))}</p>
    </div>
  </section>"""


TEXT_SLUGS = ["starburst", "protect-skin", "film-dials"]


def anatomy_section(dims, tr, label_tr):
    cards = []
    for slug, title, body, before, after, labels in SLIDER_CARDS:
        w, h = dims[f"anatomy/{after}-1400.jpg"]
        t = tr(f"set.{slug}.title", title)
        alt = tr("compare.alt_template", "{title}: before and after on the same frame").replace("{title}", t)
        pair = (label_tr(f"set.{slug}.label_a", labels[0]), label_tr(f"set.{slug}.label_b", labels[1]))
        cards.append(f'<article class="setting" id="set-{slug}"><h3>{esc(t)}</h3><p>{esc(tr(f"set.{slug}.body", body))}</p>'
                     + compare_html(before, after, alt, w, h, pair)
                     + "</article>")
    for tslug, (title, body, foot) in zip(TEXT_SLUGS, TEXT_CARDS):
        cards.append(f'<article class="setting setting-text"><h3>{esc(tr(f"text.{tslug}.title", title))}</h3>'
                     f'<p>{esc(tr(f"text.{tslug}.body", body))}</p>'
                     f'<p class="setting-foot">{esc(tr(f"text.{tslug}.foot", foot))}</p></article>')
    return f"""
  <section id="rc1" class="chapter rc-anatomy" data-chapter="rc1_anatomy">
    <div class="wrap">
      <p class="kicker">{esc(tr("anatomy.kicker", "Anatomy"))}</p>
      <h2>{esc(tr("anatomy.title", "What a recipe is made of"))}</h2>
      <p class="lead">{esc(tr("anatomy.lead", "Every dial the recipe builder has, isolated on one frame — 1998 Neg, one of the shipped recipes, taken apart. Each pair below is a real render through Fonder's engine: the recipe's film alone on the left of the line, and on the right the film with exactly one of 1998 Neg's own settings applied. Nothing is simulated for the page."))}</p>
      <div class="settings">{"".join(cards)}</div>
      <p class="note">{esc(tr("anatomy.note", "Borders and date stamps are camera controls, set per shot — they are not part of a recipe, so they have no card here."))}</p>
    </div>
  </section>"""


def scene_section(data, dims, tr):
    frames = data["scene"]
    if not frames:
        return ""
    w, h = dims[f"scene/no-look-{STAGE_WIDTHS[-1]}.jpg"]

    def chip_data(slug):
        srcset = ", ".join(f"/img/recipes/scene/{slug}-{v}.jpg {v}w" for v in STAGE_WIDTHS)
        return (f'data-slug="{esc(slug)}" data-img="/img/recipes/scene/{slug}-{STAGE_WIDTHS[0]}.jpg" '
                f'data-srcset="{srcset}"')

    none_label = tr("scene.chip_none", "No recipe")
    none_caption = tr("scene.caption_none", "No recipe — straight off the phone")
    badge_label = tr("scene.badge_custom", "built in Fonder")
    chips = [f'<button class="scene-chip is-on" type="button" {chip_data("no-look")} '
             f'data-label="{esc(none_label)}" data-caption="{esc(none_caption)}" aria-pressed="true">{esc(none_label)}</button>']
    for f in frames:
        badge = f' <span class="chip-badge">{esc(badge_label)}</span>' if f["custom"] else ""
        chips.append(f'<button class="scene-chip" type="button" {chip_data(f["slug"])} '
                     f'data-label="{esc(f["label"])}" aria-pressed="false">{esc(f["label"])}{badge}</button>')
    n = len(frames)
    lead = tr("scene.lead", "One shutter press, developed through {n} different looks. Pick one — the two marked built in Fonder are custom recipes made with the recipe builder below, proof the dials above are yours too.").replace("{n}", str(n))
    return f"""
  <section id="rc2" class="chapter rc-scene" data-chapter="rc2_scene">
    <div class="wrap">
      <p class="kicker">{esc(tr("scene.kicker", "One scene, every film"))}</p>
      <h2>{esc(tr("scene.title", "The scene stays put. The film changes."))}</h2>
      <p class="lead">{esc(lead)}</p>
      <figure class="scene-stage">
        <img id="scene-img" src="/img/recipes/scene/no-look-{STAGE_WIDTHS[0]}.jpg"
          srcset="{", ".join(f"/img/recipes/scene/no-look-{v}.jpg {v}w" for v in STAGE_WIDTHS)}"
          sizes="{STAGE_SIZES}" width="{w}" height="{h}"
          alt="{esc(tr("scene.alt", "One city frame, re-developed through the selected recipe"))}" loading="lazy" decoding="async">
        <figcaption id="scene-caption" aria-live="polite">{esc(none_caption)}</figcaption>
      </figure>
      <div class="scene-chips" role="group" aria-label="{esc(tr("scene.group_aria", "Choose a recipe for the scene"))}">{"".join(chips)}</div>
    </div>
  </section>"""


def build_frames(tr):
    m = lambda key, en: esc(tr(f"build.mock.{key}", en))
    return f"""
      <div class="builder-frames">
        <figure class="bframe"><div class="bscreen">
          <p class="b-top"><span>{m("recipe", "Recipe")}</span><b>{m("yours", "Toffee Neg · yours")}</b></p>
          <div class="b-photo"></div>
          <div class="b-rows">
            <p><span>{m("film", "Film")}</span><span class="b-val">Toffee Neg</span></p>
            <p><span>{m("tone", "Tone")}</span><span class="b-val">H −2 · S +1</span></p>
            <p><span>{m("colour", "Colour")}</span><span class="b-val">+3</span></p>
          </div>
        </div><figcaption>{esc(tr("build.cap1", "1 · Start from any film or recipe and shoot with it."))}</figcaption></figure>
        <figure class="bframe"><div class="bscreen">
          <p class="b-top"><span>{m("wb", "White bal")}</span><b>6300K · R+1 B−2</b></p>
          <div class="b-photo b-photo-warm"></div>
          <div class="b-slider"><span>2500K</span><i></i><span>10000K</span></div>
          <div class="b-rows">
            <p><span>{m("grain", "Grain")}</span><span class="b-val">{m("grain_v", "30 · small")}</span></p>
            <p><span>{m("halation", "Halation")}</span><span class="b-val">16</span></p>
          </div>
        </div><figcaption>{esc(tr("build.cap2", "2 · Dial the darkroom: tone, balance, grain, glow — live on the viewfinder."))}</figcaption></figure>
        <figure class="bframe"><div class="bscreen">
          <p class="b-top"><span>{m("save", "Save")}</span><b>{m("save_as", "Save as new recipe")}</b></p>
          <div class="b-photo b-photo-warm"></div>
          <div class="b-rows">
            <p><span>{m("name", "Name")}</span><span class="b-val">Sunday Flyover</span></p>
            <p><span>{m("base", "Base")}</span><span class="b-val">Toffee Neg</span></p>
            <p><span>{m("share", "Share")}</span><span class="b-val">{m("share_how", "As text or QR")}</span></p>
          </div>
        </div><figcaption>{esc(tr("build.cap3", "3 · Save it to Mine, and share it as plain text anyone can paste back in."))}</figcaption></figure>
      </div>"""


def build_section(tr):
    return f"""
  <section id="rc3" class="chapter rc-build" data-chapter="rc3_build">
    <div class="wrap">
      <p class="kicker">{esc(tr("build.kicker", "Build your own"))}</p>
      <h2>{esc(tr("build.title", "The same dials are on the camera"))}</h2>
      <p class="lead">{esc(tr("build.lead", "Every setting above is a control in the app, not a preset you are locked out of. Start from any shipped recipe, turn the dials while the viewfinder answers, and save what you land on as your own — the two custom looks in the scene above were made exactly this way."))}</p>
      {build_frames(tr)}
    </div>
  </section>"""


def catalogue_section(data, dims, occasions, tr, lang, cat_vi=None):
    occ_key = "occasion_vi" if lang == "vi" else "occasion_en"
    cards = []
    for r in data["recipes"]:
        w, h = dims[f"samples/{r['id']}.jpg"]
        amount, word = grain_personality(r["grain"], tr)
        scene_chip = (f'<a class="card-scene" href="#rc2" data-scene="{esc(r["id"])}">'
                      f'{esc(tr("catalogue.card_scene", "See it on the shared scene"))}</a>'
                      if r.get("scene") else "")
        occ = occasions.get(r["id"], {}).get(occ_key, "")
        occ_line = f'<p class="card-occasion">{esc(occ)}</p>' if occ else ""
        desc, guidance = r["description"], r["guidance"]
        if lang == "vi":
            look_vi = (cat_vi or {}).get("looks", {}).get(r["id"], {})
            if not look_vi.get("description") or not look_vi.get("guidance"):
                raise BuildError(f"catalogue.vi.json is missing description/guidance for {r['id']!r}")
            desc, guidance = look_vi["description"], look_vi["guidance"]
        alt = tr("catalogue.alt_template", "Sample photograph developed with {name}").replace("{name}", r["name"])
        cards.append(f"""<article class="recipe-card" id="r-{esc(r['id'])}">
        <img src="/img/recipes/samples/{esc(r['id'])}.jpg" width="{w}" height="{h}"
          alt="{esc(alt)}" loading="lazy" decoding="async">
        <div class="card-body">
          {occ_line}<h3>{esc(r['name'])}</h3>
          <p class="card-film">{esc(r['film']['name'])}{swatches_html(r['film']['palette'])}</p>
          <p class="card-desc">{esc(desc)}</p>
          <p class="card-grain"><b>{esc(amount)}</b> — {esc(word)}</p>
          <p class="card-when">{esc(guidance)}</p>
          {scene_chip}
        </div></article>""")
    n = len(data["recipes"])
    lead = tr("catalogue.lead", "All {n} of them — each with its film's palette line (six memory colours run through that film's own maths, the way the app draws it) and its grain, on a sample from the owner's own rolls.").replace("{n}", str(n))
    return f"""
  <section id="rc4" class="chapter rc-catalogue" data-chapter="rc4_catalogue">
    <div class="wrap">
      <p class="kicker">{esc(tr("catalogue.kicker", "The catalogue"))}</p>
      <h2>{esc(tr("catalogue.title", "Every recipe that ships"))}</h2>
      <p class="lead">{esc(lead)}</p>
      <div class="cards">{"".join(cards)}</div>
    </div>
  </section>"""


# No grain canvas here, unlike the homepage: every photograph on this page carries the
# recipe's own rendered grain, and a page texture on top doubles it (the owner's call).
# ---------------------------------------------------------------- editorial layer
# Five close readings before the catalogue. Every factual claim below is rewritten from
# recipes/data/catalogue.json (description, guidance, grain) and occasions.csv — the
# subheading is the recipe's own occasion line, pulled at build time. Toffee Neg is a film,
# not a recipe: its facts come from the app's film description (the same source --sync
# reads), and its picture is its existing scene-viewer render — nothing new is derived.
FEATURED = [
    {"id": "noon", "name": "Noon Neg", "img": "samples/noon.jpg",
     "intro": "The plain reading the rest of the catalogue departs from, on Diary Neg: an honest "
              "photograph with a little more colour in it, and nothing pushed toward a mood.",
     "best": "Days when the light is already right and you want the photograph, not the recipe.",
     "look": [("Colour", "A little fuller than the scene and no further. Whites stay white."),
              ("Contrast", "Even from edge to edge: the corners stay as bright as the middle."),
              ("Grain", "None. A clean frame."),
              ("Highlights", "Held back, so a sunlit wall keeps its surface instead of glaring."),
              ("Shadows", "Left open, so shade stays readable rather than closing up.")],
     "when": "The light is already doing the work."},
    {"id": "summer", "name": "Summer Chrome", "img": "samples/summer.jpg",
     "intro": "The strong-sun chrome, built on Daylight Cine: shadows cool while highlights warm, "
              "so the two ends of the frame disagree — and a face sits protected between them.",
     "best": "Open midday light with a real highlight in the frame — the headroom is built for it.",
     "look": [("Colour", "Golden light over faintly blue-green shade; only the ends of the "
               "picture are coloured. Skin is the one thing protected — a little richer, a "
               "little brighter, eased where the light lands."),
              ("Contrast", "Carried by temperature as much as tone: warm against cool, with the "
               "sky keeping its blue instead of bleaching out."),
              ("Grain", "None — the frame stays clean."),
              ("Highlights", "A white wall or a windscreen rounds off gently at its brightest "
               "edge instead of going white."),
              ("Shadows", "Cool, faintly blue-green, pulling away from the warm light.")],
     "when": "Strong sun, and you want to keep the heat in the picture."},
    {"id": "ferry", "name": "Night Ferry 800", "img": "samples/ferry.jpg",
     "intro": "Humid neon — the warm kind of night. The glow is let run and the edge is taken "
              "off, so the air between you and the lights is part of the picture.",
     "best": "Dense signage after dark, ideally with water or wet ground to carry the glow. A "
             "dry, clean night gives it nothing to work with.",
     "look": [("Colour", "Red, magenta and cyan pushed hard while yellows are held back, so a "
               "sign separates from the street it is lighting. Faces barely move — ordinary "
               "between the signs."),
              ("Contrast", "Low and close rather than sharp: a night that is warm, not crisp."),
              ("Grain", "Coarse — 60, large. A fast-film night, worn openly."),
              ("Highlights", "A bright source eases off early enough to keep its colour rather "
               "than burning to white."),
              ("Shadows", "Lifted rather than crushed, deepened and turned blue.")],
     "when": "The air is thick and every shop is still lit."},
    {"id": "folio", "name": "Folio 100", "img": "samples/folio.jpg",
     "intro": "Lost Summer Neg as an everyday summer roll: colour kept quiet and slightly faded, "
              "tones soft and even, the kind of roll that covers a whole ordinary week.",
     "best": "Everyday summer days — streets, errands, trips and friends outdoors in good light. "
             "Under hard midday sun with a bright sky, raise the dynamic range to hold the "
             "brightest parts.",
     "look": [("Colour", "A clear blue sky pales almost to a soft grey, green roofs go grey-teal, "
               "a red shopfront turns toward vermilion and a pink wall toward salmon. White "
               "walls stay clean, with only a faint warmth."),
              ("Contrast", "Soft and even, with edges and fine detail eased and the corners "
               "gently darkened."),
              ("Grain", "Fine — 25, small. Light enough that skies and plain walls stay calm."),
              ("Highlights", "Bright walls are held back from glare, with a faint glow at their "
               "edges."),
              ("Shadows", "Opened a little.")],
     "when": "Nothing special is happening and you want to keep it anyway."},
    {"id": None, "name": "Toffee Neg", "img": "scene/film-toffee-neg-1080.jpg",
     "occasion": "For photos that feel found, not taken.", "kind": "The film",
     "scene": "film-toffee-neg",
     "intro": "Not a recipe — one of the films the recipes stand on, and the one this page's "
              "hero is developed through. It is also the roll on the homepage: loaded in Film "
              "Roll, shot blind, developed all at once.",
     "best": "Whole rolls. A look this settled suits shooting blind and meeting the pictures "
             "later, already warmed through.",
     "look": [("Colour", "A print left on a sunny shelf for years: amber soaked into the middle, "
               "leaves gone ochre and khaki, oranges and yellows glowing like toffee. The sky "
               "does not fade to grey — it turns a dusty teal against all the warmth, and skin "
               "stays golden without going orange."),
              ("Contrast", "Soft and a little faded at the top of the frame, rich at the bottom."),
              ("Grain", "A recipe decision, not the film's — load it clean or dial texture in."),
              ("Highlights", "The brightest parts settle into a warm cream instead of white."),
              ("Shadows", "Turned a deep chocolate brown.")],
     "when": "The day already feels like a memory."},
]

# The moment-based picker. Every pairing checked against the recipes' own guidance lines.
CHOICES = [
    ("Soft daylight, everyday errands", [("ordinaryday", "Ordinary Day 200"), ("noon", "Noon Neg")]),
    ("Bright sun and travel", [("summer", "Summer Chrome")]),
    ("Warm low light and dinners", [("lastorders", "Midnight Club 100"), ("latesupper", "Late Supper 800")]),
    ("Neon, rain and city nights", [("ferry", "Night Ferry 800"), ("electric", "Electric Rain 800")]),
]


def find_section(tr):
    return f"""
  <section id="rc0b" class="chapter rc-find" data-chapter="rc0b_find">
    <div class="wrap">
      <p class="kicker">{esc(tr("find.kicker", "Find your film"))}</p>
      <h2>{esc(tr("find.title", "One camera. Many ways to remember it."))}</h2>
      <p class="lead">{esc(tr("find.lead1", "Warm afternoons. Grey mornings. Harsh flash. Neon after midnight. Fonder films are built for moments, not test charts. Each one has its own colour, contrast, grain and character — so instead of fixing the photo afterward, you choose how you want the moment to feel before you press the shutter."))}</p>
      <p class="lead">{esc(tr("find.lead2", "Pick a film. Go somewhere. See what happens."))}</p>
    </div>
  </section>"""


LOOK_LABELS = [("colour", "Colour"), ("contrast", "Contrast"), ("grain", "Grain"),
               ("highlights", "Highlights"), ("shadows", "Shadows")]


def featured_section(data, dims, occasions, tr, lang):
    ids = {r["id"] for r in data["recipes"]}
    scene_slugs = {s["slug"] for s in data["scene"]}
    occ_key = "occasion_vi" if lang == "vi" else "occasion_en"
    cards = []
    for f in FEATURED:
        fid = f["id"] or "toffee"
        if f["id"] is not None and f["id"] not in ids:
            raise BuildError(f"featured recipe {f['id']!r} is not in the catalogue")
        occ = occasions[f["id"]][occ_key] if f["id"] else tr("feature.toffee.occasion", f["occasion"])
        kind = (tr("feature.kind_film", "The film") if f["id"] is None
                else tr("feature.kind_recipe", "The recipe"))
        w, h = dims[f["img"]]
        scene = f.get("scene", f["id"] if (f["id"] in scene_slugs) else None)
        scene_link = (f'<a class="card-scene" href="#rc2" data-scene="{esc(scene)}">'
                      f'{esc(tr("feature.link_scene", "See it on the shared scene"))}</a>' if scene else "")
        look = "".join(f'<li><b>{esc(tr(f"look.{lk}", lbl))}</b> — {esc(tr(f"feature.{fid}.look.{lk}", v))}</li>'
                       for (lk, lbl), (_, v) in zip(LOOK_LABELS, f["look"]))
        anchor = f'#r-{f["id"]}' if f["id"] else "#rc2"
        anchor_label = (tr("feature.link_card", "Its card below") if f["id"]
                        else tr("feature.link_scene_render", "Its scene render above"))
        alt = tr("feature.alt_template", "A frame developed with {name}").replace("{name}", f["name"])
        cards.append(f"""<article class="feature">
        <img src="/img/recipes/{esc(f['img'])}" width="{w}" height="{h}"
          alt="{esc(alt)}" loading="lazy" decoding="async">
        <div class="feature-body">
          <p class="feature-kind">{esc(kind)}</p>
          <h3>{esc(f['name'])}</h3>
          <p class="feature-occ">{esc(occ)}</p>
          <p class="feature-intro">{esc(tr(f"feature.{fid}.intro", f['intro']))}</p>
          <p class="feature-best"><b>{esc(tr("feature.label_best", "Best for"))}</b> — {esc(tr(f"feature.{fid}.best", f['best']))}</p>
          <ul class="feature-look">{look}</ul>
          <p class="feature-when"><b>{esc(tr("feature.label_when", "Try it when"))}</b> — {esc(tr(f"feature.{fid}.when", f['when']))}</p>
          <p class="feature-links"><a href="{anchor}">{esc(anchor_label)}</a>{scene_link}</p>
        </div></article>""")
    return f"""
  <section id="rc3b" class="chapter rc-featured" data-chapter="rc3b_featured">
    <div class="wrap">
      <p class="kicker">{esc(tr("featured.kicker", "Read five closely"))}</p>
      <h2>{esc(tr("featured.title", "Five to start with"))}</h2>
      <p class="lead">{esc(tr("featured.lead", "Four recipes and one of the films they stand on, read closely. Everything claimed here comes from the recipe itself — the same records the cards below are built from."))}</p>
      <div class="features">{"".join(cards)}</div>
    </div>
  </section>"""


def choose_section(data, tr):
    ids = {r["id"] for r in data["recipes"]}
    rows = []
    for i, (moment, picks) in enumerate(CHOICES, 1):
        for rid, _ in picks:
            if rid not in ids:
                raise BuildError(f"picker recipe {rid!r} is not in the catalogue")
        joiner = f' {esc(tr("choose.or", "or"))} '
        links = joiner.join(f'<a href="#r-{esc(rid)}">{esc(name)}</a>' for rid, name in picks)
        rows.append(f'<li><span class="pick-when">{esc(tr(f"choose.moment{i}", moment))}</span>'
                    f'<span class="pick-films">{links}</span></li>')
    return f"""
  <section id="rc3c" class="chapter rc-choose" data-chapter="rc3c_choose">
    <div class="wrap">
      <p class="kicker">{esc(tr("choose.kicker", "How to choose a film"))}</p>
      <h2>{esc(tr("choose.title", "Start from the moment"))}</h2>
      <ul class="picks">{"".join(rows)}</ul>
      <p class="lead">{esc(tr("choose.end", "There is no correct choice. The same place photographed with a different film becomes a different memory."))}</p>
    </div>
  </section>"""


def before_section(tr):
    return f"""
  <section id="rc3d" class="chapter rc-before" data-chapter="rc3d_before">
    <div class="wrap">
      <p class="kicker">{esc(tr("before.kicker", "Built before the shutter"))}</p>
      <h2>{esc(tr("before.title", "Not another edit waiting for you"))}</h2>
      <p class="lead">{esc(tr("before.lead", "A Fonder film is more than a filter applied afterward. It decides how highlights roll off, how shadows sit and how colour behaves — in the viewfinder, before the shutter. You choose the film before taking the photo, so the visual decision becomes part of shooting, not another task waiting for you later. No preset hunting. No editing session. Just choose a film and use it."))}</p>
      <p class="anatomy-link">{esc(tr("before.anatomy_line", "Want to see what each setting actually does?"))}
      <a href="#rc1">{esc(tr("before.anatomy_link", "Every control, shown honestly →"))}</a></p>
    </div>
  </section>"""


def manifesto_section(tr):
    return f"""
  <section id="rc5" class="chapter rc-manifesto" data-chapter="rc5_manifesto">
    <div class="wrap">
      <h2>{esc(tr("manifesto.title", "Do not look for the perfect film"))}</h2>
      <p class="lead">{esc(tr("manifesto.lead", "There probably is not one. Pick a film because it fits the day. Or because it does not. Use a warm film in cold weather. Use a night film at noon. The point is not to reproduce reality perfectly. It is to decide how you want to remember it."))}</p>
    </div>
  </section>"""


def cta_section(tr, lang):
    home = "/#ch4" if lang == "en" else "/vi/#ch4"
    return f"""
  <section id="rc6" class="chapter rc-cta" data-chapter="rc6_cta">
    <div class="wrap">
      <p class="kicker">{esc(tr("cta.kicker", "Load one and go"))}</p>
      <p class="lead">{esc(tr("cta.lead", "You can read about a film for ten minutes. Or you can load one and see what happens."))}</p>
      <p><a class="btn" href="{home}">{esc(tr("cta.button", "Load this film"))}</a></p>
    </div>
  </section>"""


def check_occasions(data, occasions):
    """Every occasions.csv row must name a shipped recipe — a renamed or dropped id fails loudly."""
    ids = {r["id"] for r in data["recipes"]}
    for oid in occasions:
        if oid not in ids:
            raise BuildError(f"recipes/data/occasions.csv id {oid!r} is not in the catalogue")
    for oid, row in occasions.items():
        check_names(f"{row.get('name', '')} {row.get('occasion_en', '')} {row.get('occasion_vi', '')}",
                    f"recipes/data/occasions.csv ({oid})")


# Chrome that never came from the translation export: the language toggle and the two
# legal labels, following the homepage's own strings for each language.
PAGE_CHROME = {
    "en": {"home": "/", "self": "/recipes/", "diary": "/diary/", "toggle_href": "/vi/recipes/",
           "toggle_label": "Ti\u1ebfng Vi\u1ec7t", "toggle_lang": "vi", "privacy": "Privacy", "terms": "Terms"},
    "vi": {"home": "/vi/", "self": "/vi/recipes/", "diary": "/vi/diary/", "toggle_href": "/recipes/",
           "toggle_label": "English", "toggle_lang": "en", "privacy": "Quy\u1ec1n ri\u00eang t\u01b0",
           "terms": "\u0110i\u1ec1u kho\u1ea3n"},
}


def render_page(data, dims, occasions, lang, tr, label_tr, cat_vi=None):
    ch = PAGE_CHROME[lang]
    vn_preload = ('\n<link rel="preload" href="/fonts/be-vietnam-pro-400-vietnamese.woff2" as="font" type="font/woff2" crossorigin>'
                  if lang == "vi" else "")
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(tr("meta.title", "Recipes \u00b7 Fonder"))}</title>
<meta name="description" content="{esc(tr("meta.description", "What a Fonder recipe is \u2014 a film character plus darkroom decisions \u2014 every setting isolated on one frame, one scene through every film, and the full shipped catalogue."))}">
<link rel="canonical" href="https://fondercam.online{ch["self"]}">
<link rel="alternate" hreflang="en" href="https://fondercam.online/recipes/">
<link rel="alternate" hreflang="vi" href="https://fondercam.online/vi/recipes/">
<link rel="alternate" hreflang="x-default" href="https://fondercam.online/recipes/">
<meta property="og:title" content="{esc(tr("meta.title", "Recipes \u00b7 Fonder"))}">
<meta property="og:description" content="{esc(tr("meta.og_description", "A film character plus the darkroom decisions around it: every recipe Fonder ships, taken apart on one frame."))}">
<meta property="og:image" content="https://fondercam.online/img/recipes/hero/after-1600.jpg">
<link rel="icon" href="/icon.png?v=2">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2">
<link rel="preload" href="/fonts/bricolage-grotesque-700-opsz72-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/be-vietnam-pro-400-latin.woff2" as="font" type="font/woff2" crossorigin>{vn_preload}
<link rel="stylesheet" href="/home/home.css?v=3">
<link rel="stylesheet" href="/recipes/recipes.css?v=3">
<script defer src="/recipes/recipes.js"></script>
<script defer src="/home/consent.js"></script>
</head>
<body>
<header class="site-nav">
  <a class="brand" href="{ch["home"]}"><img src="/img/home/brand-56.png" width="28" height="28" alt="" aria-hidden="true">Fonder</a>
  <nav><a href="{ch["self"]}" aria-current="page">{esc(tr("nav.recipes", "Recipes"))}</a><a href="{ch["diary"]}">{esc(tr("nav.diary", "Diary"))}</a><a href="{ch["toggle_href"]}" hreflang="{ch["toggle_lang"]}" lang="{ch["toggle_lang"]}">{esc(ch["toggle_label"])}</a></nav>
</header>
<main>{hero_section(dims, tr)}{find_section(tr)}{anatomy_section(dims, tr, label_tr)}{scene_section(data, dims, tr)}{build_section(tr)}{featured_section(data, dims, occasions, tr, lang)}{choose_section(data, tr)}{before_section(tr)}{catalogue_section(data, dims, occasions, tr, lang, cat_vi)}{manifesto_section(tr)}{cta_section(tr, lang)}
</main>
<footer class="site-footer">
  <p>{esc(tr("footer.line", "Made in H\u00e0 N\u1ed9i by Trung Hai. Every photograph on this page is the owner's own frame, rendered through Fonder."))}</p>
  <nav><a href="{ch["home"]}">{esc(tr("nav.home", "Home"))}</a><a href="{ch["self"]}">{esc(tr("nav.recipes", "Recipes"))}</a><a href="{ch["diary"]}">{esc(tr("nav.diary", "Diary"))}</a><a href="/privacy/">{esc(ch["privacy"])}</a><a href="/terms/">{esc(ch["terms"])}</a></nav>
</footer>
<div class="consent-bar" hidden>
  <p>{esc(tr("consent.text", "This site uses Google Analytics to count visits. OK?"))}</p>
  <button class="consent-yes" type="button">{esc(tr("consent.ok", "OK"))}</button>
  <button class="consent-no" type="button">{esc(tr("consent.no", "No thanks"))}</button>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------- build/check

def load_data():
    if not DATA.exists():
        raise BuildError(f"{DATA.relative_to(ROOT)} missing; run python3 tools/build_recipes.py --sync")
    return json.loads(DATA.read_text(encoding="utf-8"))


def image_dims():
    dims = {}
    for path in sorted(IMG.rglob("*.jpg")):
        dims[str(path.relative_to(IMG))] = jpeg_size(path)
    return dims


def check_names(text, where):
    """Whole words only: the app's own copy says "across" and "portraits", which the
    homepage's plain substring test would misread as stock names."""
    low = text.lower()
    for name in FORBIDDEN:
        if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", low):
            raise BuildError(f"{where} names a real film or simulation ({name!r})")


# The budget covers true-2x variants for a 21-state scene viewer whose big renditions load
# only when picked; the page's initial load is the hero pair plus lazy images on approach.
# It also has to hold one lazy card image per shipped recipe: raised from 16.5 MB when the
# fiftieth recipe's sample arrived with 17 KB of room left.
def check_images(budget=16_700_000, long_edge=2200):
    total = 0
    for path in sorted(IMG.rglob("*.jpg")):
        data = path.read_bytes()
        total += len(data)
        if b"Exif\x00" in data[:65536] or b"http://ns.adobe.com/xap" in data[:65536]:
            raise BuildError(f"{path.relative_to(ROOT)} still carries metadata (EXIF/XMP)")
        w, h = jpeg_size(path)
        if max(w, h) > long_edge:
            raise BuildError(f"{path.relative_to(ROOT)} is {w}x{h}; long edge must be ≤ {long_edge}")
    if total > budget:
        raise BuildError(f"img/recipes totals {total} bytes; budget is {budget}")


def check_page(page):
    for m in re.finditer(r"<img\b[^>]*>", page):
        tag = m.group(0)
        if 'width="' not in tag or 'height="' not in tag:
            raise BuildError(f"an <img> is missing explicit width/height: {tag[:80]}…")
    check_names(page, "recipes/index.html")


def main(argv):
    try:
        if "--sync" in argv:
            sync(argv)
        data = load_data()
        check_names(json.dumps(data, ensure_ascii=False), "recipes/data/catalogue.json")
        occasions = load_occasions()
        check_occasions(data, occasions)
        vi = load_vi_strings()
        cat_vi = load_catalogue_vi()
        check_names(json.dumps(cat_vi, ensure_ascii=False), "recipes/data/catalogue.vi.json")
        dims = image_dims()
        pages = {}
        for lang, out in (("en", PAGE), ("vi", PAGE_VI)):
            page = render_page(data, dims, occasions, lang, make_tr(lang, vi),
                               make_label_tr(lang, vi), cat_vi)
            check_page(page)
            pages[out] = page
        if "--check" in argv:
            check_images()
            for out, page in pages.items():
                if not out.exists() or out.read_text(encoding="utf-8") != page:
                    raise BuildError(f"{out.relative_to(ROOT)} is stale; run python3 tools/build_recipes.py")
            print("build_recipes: pages are current")
        else:
            for out, page in pages.items():
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(page, encoding="utf-8")
            print("build_recipes: wrote " + ", ".join(str(o.relative_to(ROOT)) for o in pages))
    except BuildError as e:
        sys.exit(f"build_recipes: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
