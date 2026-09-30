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
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build_home import FORBIDDEN as HOME_FORBIDDEN, BuildError, jpeg_size

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "recipes/data/catalogue.json"
IMG = ROOT / "img/recipes"
PAGE = ROOT / "recipes/index.html"
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

# Recipes whose bundled app sample has a person's face in it (the owner's portrait frames).
# Faces stay off the site, so these cards show the recipe rendered over the shared no-face
# frame instead — through the app's own pipeline at the sample strength, never a substitute
# grade. Checked by eye and by Vision face detection over img/recipes/samples/.
FACE_SAMPLES = {"amber", "sunday", "velour", "windowface"}

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
            "--looks", ",".join(sorted(FACE_SAMPLES)))


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
        # around, never out — nothing below touches it.
        recipes = []
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
    print(f"build_recipes: synced {len(recipes)} recipes, {len(scene)} scene frames, "
          f"{len(ANATOMY_SLUGS)} anatomy renders")
    for line in matched:
        print("  " + line)
    for name in skipped:
        print(f"  skipped (not a shipped recipe): {name}")


# ---------------------------------------------------------------------------- page

def esc(s):
    return html.escape(str(s), quote=True)


def grain_personality(g):
    n, large = g["strength"], g["large"]
    if n == 0:
        word = "opens clean — grain is yours to dial"
    elif n <= 20:
        word = "a fine, quiet grain"
    elif n <= 30:
        word = "a light grain that reads as film"
    elif n <= 45:
        word = "a soft, present grain" if large else "a present, honest grain"
    else:
        word = "a coarse fast-film grain"
    amount = "off" if n == 0 else f"{n} · {'large' if large else 'small'}"
    return f"Grain {amount}", word


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
     "no picture — it needs a face, and faces stay off this site"),
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


def hero_section(dims):
    w, h = dims[f"hero/after-{HERO_WIDTHS[-1]}.jpg"]
    before_set = ", ".join(f"/img/recipes/hero/before-{v}.jpg {v}w" for v in HERO_WIDTHS)
    after_set = ", ".join(f"/img/recipes/hero/after-{v}.jpg {v}w" for v in HERO_WIDTHS)
    slider = (f'<div class="compare" style="aspect-ratio:{w}/{h}">'
              f'<img class="compare-before" src="/img/recipes/hero/before-1600.jpg" '
              f'srcset="{before_set}" '
              f'sizes="{STAGE_SIZES}" width="{w}" height="{h}" alt="" aria-hidden="true" fetchpriority="high">'
              f'<img class="compare-after" src="/img/recipes/hero/after-1600.jpg" '
              f'srcset="{after_set}" '
              f'sizes="{STAGE_SIZES}" width="{w}" height="{h}" '
              f'alt="The same city frame twice: the plain capture, and the Toffee Neg develop of it" fetchpriority="high">'
              f'<label class="compare-label"><span class="sr-only">Drag to compare the plain capture with the developed frame</span>'
              f'<input type="range" min="0" max="100" value="50" aria-label="Drag to compare the plain capture with the developed frame"></label>'
              f'<span class="compare-tag before">Straight off the phone</span><span class="compare-tag after">Toffee Neg</span></div>')
    return f"""
  <section id="rc0" class="chapter rc-hero" data-chapter="rc0_hero">
    <div class="wrap">
      <p class="kicker">Fonder · Recipes</p>
      <h1>What a recipe is</h1>
      <p class="lead">A recipe is a film character and the darkroom decisions around it: where white sits,
      how hard the highlights climb, how much dye goes down, what texture the negative wears.
      One shutter press, developed two ways — drag the line.</p>
      {slider}
      <p class="note">Both halves are the same phone capture. The right one went through a Fonder
      recipe — nothing here is a screen filter laid over a picture.</p>
    </div>
  </section>"""


def anatomy_section(dims):
    cards = []
    for slug, title, body, before, after, labels in SLIDER_CARDS:
        w, h = dims[f"anatomy/{after}-1400.jpg"]
        cards.append(f'<article class="setting" id="set-{slug}"><h3>{esc(title)}</h3><p>{esc(body)}</p>'
                     + compare_html(before, after, f"{title}: before and after on the same frame", w, h, labels)
                     + "</article>")
    for title, body, foot in TEXT_CARDS:
        cards.append(f'<article class="setting setting-text"><h3>{esc(title)}</h3><p>{esc(body)}</p>'
                     f'<p class="setting-foot">{esc(foot)}</p></article>')
    return f"""
  <section id="rc1" class="chapter rc-anatomy" data-chapter="rc1_anatomy">
    <div class="wrap">
      <p class="kicker">Anatomy</p>
      <h2>What a recipe is made of</h2>
      <p class="lead">Every dial the recipe builder has, isolated on one frame — 1998 Neg, one of the
      shipped recipes, taken apart. Each pair below is a real render through Fonder's engine: the recipe's
      film alone on the left of the line, and on the right the film with exactly one of 1998 Neg's own
      settings applied. Nothing is simulated for the page.</p>
      <div class="settings">{"".join(cards)}</div>
      <p class="note">Borders and date stamps are camera controls, set per shot — they are not part of
      a recipe, so they have no card here.</p>
    </div>
  </section>"""


def scene_section(data, dims):
    frames = data["scene"]
    if not frames:
        return ""
    w, h = dims[f"scene/no-look-{STAGE_WIDTHS[-1]}.jpg"]

    def chip_data(slug):
        srcset = ", ".join(f"/img/recipes/scene/{slug}-{v}.jpg {v}w" for v in STAGE_WIDTHS)
        return (f'data-slug="{esc(slug)}" data-img="/img/recipes/scene/{slug}-{STAGE_WIDTHS[0]}.jpg" '
                f'data-srcset="{srcset}"')

    chips = [f'<button class="scene-chip is-on" type="button" {chip_data("no-look")} '
             'data-label="No recipe" aria-pressed="true">No recipe</button>']
    for f in frames:
        badge = ' <span class="chip-badge">built in Fonder</span>' if f["custom"] else ""
        chips.append(f'<button class="scene-chip" type="button" {chip_data(f["slug"])} '
                     f'data-label="{esc(f["label"])}" aria-pressed="false">{esc(f["label"])}{badge}</button>')
    n = len(frames)
    return f"""
  <section id="rc2" class="chapter rc-scene" data-chapter="rc2_scene">
    <div class="wrap">
      <p class="kicker">One scene, every film</p>
      <h2>The scene stays put. The film changes.</h2>
      <p class="lead">One shutter press, developed through {n} different looks. Pick one — the two marked
      <em>built in Fonder</em> are custom recipes made with the recipe builder below, proof the dials
      above are yours too.</p>
      <figure class="scene-stage">
        <img id="scene-img" src="/img/recipes/scene/no-look-{STAGE_WIDTHS[0]}.jpg"
          srcset="{", ".join(f"/img/recipes/scene/no-look-{v}.jpg {v}w" for v in STAGE_WIDTHS)}"
          sizes="{STAGE_SIZES}" width="{w}" height="{h}"
          alt="One city frame, re-developed through the selected recipe" loading="lazy" decoding="async">
        <figcaption id="scene-caption" aria-live="polite">No recipe — straight off the phone</figcaption>
      </figure>
      <div class="scene-chips" role="group" aria-label="Choose a recipe for the scene">{"".join(chips)}</div>
    </div>
  </section>"""


BUILD_FRAMES = """
      <div class="builder-frames">
        <figure class="bframe"><div class="bscreen">
          <p class="b-top"><span>Recipe</span><b>Toffee Neg · yours</b></p>
          <div class="b-photo"></div>
          <div class="b-rows">
            <p><span>Film</span><span class="b-val">Toffee Neg</span></p>
            <p><span>Tone</span><span class="b-val">H −2 · S +1</span></p>
            <p><span>Colour</span><span class="b-val">+3</span></p>
          </div>
        </div><figcaption>1 · Start from any film or recipe and shoot with it.</figcaption></figure>
        <figure class="bframe"><div class="bscreen">
          <p class="b-top"><span>White bal</span><b>6300K · R+1 B−2</b></p>
          <div class="b-photo b-photo-warm"></div>
          <div class="b-slider"><span>2500K</span><i></i><span>10000K</span></div>
          <div class="b-rows">
            <p><span>Grain</span><span class="b-val">30 · small</span></p>
            <p><span>Halation</span><span class="b-val">16</span></p>
          </div>
        </div><figcaption>2 · Dial the darkroom: tone, balance, grain, glow — live on the viewfinder.</figcaption></figure>
        <figure class="bframe"><div class="bscreen">
          <p class="b-top"><span>Save</span><b>Save as new recipe</b></p>
          <div class="b-photo b-photo-warm"></div>
          <div class="b-rows">
            <p><span>Name</span><span class="b-val">Sunday Flyover</span></p>
            <p><span>Base</span><span class="b-val">Toffee Neg</span></p>
            <p><span>Share</span><span class="b-val">As text or QR</span></p>
          </div>
        </div><figcaption>3 · Save it to Mine, and share it as plain text anyone can paste back in.</figcaption></figure>
      </div>"""


def build_section():
    return f"""
  <section id="rc3" class="chapter rc-build" data-chapter="rc3_build">
    <div class="wrap">
      <p class="kicker">Build your own</p>
      <h2>The same dials are on the camera</h2>
      <p class="lead">Every setting above is a control in the app, not a preset you are locked out of.
      Start from any shipped recipe, turn the dials while the viewfinder answers, and save what you
      land on as your own — the two custom looks in the scene above were made exactly this way.</p>
      {BUILD_FRAMES}
    </div>
  </section>"""


def catalogue_section(data, dims):
    cards = []
    for r in data["recipes"]:
        w, h = dims[f"samples/{r['id']}.jpg"]
        amount, word = grain_personality(r["grain"])
        scene_chip = (f'<a class="card-scene" href="#rc2" data-scene="{esc(r["id"])}">See it on the shared scene</a>'
                      if r.get("scene") else "")
        cards.append(f"""<article class="recipe-card" id="r-{esc(r['id'])}">
        <img src="/img/recipes/samples/{esc(r['id'])}.jpg" width="{w}" height="{h}"
          alt="Sample photograph developed with {esc(r['name'])}" loading="lazy" decoding="async">
        <div class="card-body">
          <h3>{esc(r['name'])}</h3>
          <p class="card-film">{esc(r['film']['name'])}{swatches_html(r['film']['palette'])}</p>
          <p class="card-desc">{esc(r['description'])}</p>
          <p class="card-grain"><b>{esc(amount)}</b> — {esc(word)}</p>
          <p class="card-when">{esc(r['guidance'])}</p>
          {scene_chip}
        </div></article>""")
    n = len(data["recipes"])
    return f"""
  <section id="rc4" class="chapter rc-catalogue" data-chapter="rc4_catalogue">
    <div class="wrap">
      <p class="kicker">The catalogue</p>
      <h2>Every recipe that ships</h2>
      <p class="lead">All {n} of them — each with its film's palette line (six memory colours run through
      that film's own maths, the way the app draws it) and its grain, on a sample from the owner's
      own rolls.</p>
      <div class="cards">{"".join(cards)}</div>
    </div>
  </section>"""


# No grain canvas here, unlike the homepage: every photograph on this page carries the
# recipe's own rendered grain, and a page texture on top doubles it (the owner's call).
def render_page(data, dims):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Recipes · Fonder</title>
<meta name="description" content="What a Fonder recipe is — a film character plus darkroom decisions — every setting isolated on one frame, one scene through every film, and the full shipped catalogue.">
<link rel="canonical" href="https://fondercam.online/recipes/">
<meta property="og:title" content="Recipes · Fonder">
<meta property="og:description" content="A film character plus the darkroom decisions around it: every recipe Fonder ships, taken apart on one frame.">
<meta property="og:image" content="https://fondercam.online/img/recipes/hero/after-1600.jpg">
<link rel="icon" href="/icon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/fonts/bricolage-grotesque-700-opsz72-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/be-vietnam-pro-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/home/home.css?v=2">
<link rel="stylesheet" href="/recipes/recipes.css?v=2">
<script defer src="/recipes/recipes.js"></script>
<script defer src="/home/consent.js"></script>
</head>
<body>
<header class="site-nav">
  <a class="brand" href="/"><img src="/img/home/brand-56.png" width="28" height="28" alt="" aria-hidden="true">Fonder</a>
  <nav><a href="/recipes/" aria-current="page">Recipes</a><a href="/diary/">Diary</a></nav>
</header>
<main>{hero_section(dims)}{anatomy_section(dims)}{scene_section(data, dims)}{build_section()}{catalogue_section(data, dims)}
</main>
<footer class="site-footer">
  <p>Made in Hà Nội by Trung Hai. Every photograph on this page is the owner's own frame,
  rendered through Fonder.</p>
  <nav><a href="/">Home</a><a href="/recipes/">Recipes</a><a href="/diary/">Diary</a><a href="/privacy/">Privacy</a><a href="/terms/">Terms</a></nav>
</footer>
<div class="consent-bar" hidden>
  <p>This site uses Google Analytics to count visits. OK?</p>
  <button class="consent-yes" type="button">OK</button>
  <button class="consent-no" type="button">No thanks</button>
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
def check_images(budget=16_500_000, long_edge=2200):
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
        page = render_page(data, image_dims())
        check_page(page)
        if "--check" in argv:
            check_images()
            if not PAGE.exists() or PAGE.read_text(encoding="utf-8") != page:
                raise BuildError("recipes/index.html is stale; run python3 tools/build_recipes.py")
            print("build_recipes: page is current")
        else:
            PAGE.parent.mkdir(parents=True, exist_ok=True)
            PAGE.write_text(page, encoding="utf-8")
            print("build_recipes: wrote recipes/index.html")
    except BuildError as e:
        sys.exit(f"build_recipes: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
