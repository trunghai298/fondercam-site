#!/usr/bin/env python3
"""Make the homepage photos from Hai's Film Roll renders (final Fonder HEICs: film look, border
and date stamp already baked in — never re-rendered, never cropped).

  python3 tools/roll_images.py [SOURCE_DIR]     (default: ~/Downloads/today)

Writes img/home/prints/01..06.jpg, develop/f01..f12.jpg, contact.jpg and og.jpg.
Needs macOS sips, ffmpeg, exiftool and Google Chrome. Every output is stripped of metadata.

  python3 tools/roll_images.py --slider BEFORE.png AFTER.png

Encodes chapter 2's before/after slider pair (img/home/develop-before.jpg, develop-after.jpg).
Both halves are Fonder engine renders of one RAW (DSCF9002.RAF, Hai's X-T3), 1600 px on the long
edge, made with FilmKit from the filmcam repo: "before" with no film (the app's RAW decode:
sharpening 0, the RAW's as-shot scene light), "after" with the Roll develop recipe for Toffee Neg
(RollDevelopment.recipe: the film at full strength, Colour +3 and the rest). This step only
fits them to 3:2 and encodes them.

  python3 tools/roll_images.py --still RENDER_DIR

Encodes chapter 1's Still-mode phone (img/home/still/): the viewfinder frames 01..07.png (600x900 from
Hai's own X-T3 JPEG IMG_0303.jpg, a portrait 2:3 frame, decoded as the app imports a JPEG: no measured
light, so the scene is taken as daylight), rendered by FilmKit through the
catalogue's recipes at the camera's default strength: Summer Chrome, Ha Noi Chrome, Amber 400, Still
Air 100, then Still Air 100 at WB 3200K, at 7000K, and at 7000K with Grain 75) and the recipe
strip's swatches sw-<look id>.png.
"""
import html, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "img/home"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

TOFFEE, DUSK = "Toffe Neg", "Dusk"   # source folder names ("Toffe" is how the folder is spelled)

# The roll on the phone and on the contact sheet: (source, film), frames 01..12 in shooting order.
ROLL = [
    (f"{TOFFEE}/IMG_0200", "Toffee Neg"), (f"{TOFFEE}/IMG_0201", "Toffee Neg"),
    (f"{TOFFEE}/IMG_0202", "Toffee Neg"), (f"{TOFFEE}/IMG_0203", "Toffee Neg"),
    (f"{TOFFEE}/render copy", "Toffee Neg"),   # the wide lake with the small red boat (09:07 stamp)
    (f"{TOFFEE}/render 2", "Toffee Neg"), (f"{TOFFEE}/render 3", "Toffee Neg"),
    (f"{TOFFEE}/render 4", "Toffee Neg"), (f"{TOFFEE}/render 5", "Toffee Neg"),
    (f"{TOFFEE}/render 7", "Toffee Neg"), (f"{TOFFEE}/render copy 2", "Toffee Neg"),
    (f"{DUSK}/render 5", "Dusk"),
]

# Chapter 3 prints, in fan order: (source, film). tools/build_home.py FAN_PRINTS labels them.
PRINTS = [(f"{DUSK}/render 2", "Dusk"), (f"{DUSK}/render 3", "Dusk"), ("../render", "Dusk"),   # the flag boat, ~/Downloads/render.HEIC; replaced the gate print (faces)
          (f"{TOFFEE}/IMG_0201", "Toffee Neg"), (f"{TOFFEE}/render copy 2", "Toffee Neg"),
          (f"{TOFFEE}/render 2", "Toffee Neg")]

OG_PHOTO = f"{TOFFEE}/render copy"


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def strip(path):
    run("exiftool", "-all=", "-overwrite_original", str(path))


def to_jpeg(src, dest, long_edge, quality=80):
    """HEIC -> sRGB JPEG with its long edge at `long_edge`, whole frame kept."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    run("sips", "-s", "format", "jpeg", "-s", "formatOptions", str(quality), "-Z", str(long_edge), str(src), "--out", str(dest))
    strip(dest)


def chrome_shot(page, width, height, dest_png):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                    f"--window-size={width},{height}", "--virtual-time-budget=5000", f"--screenshot={dest_png}",
                    page.as_uri()], check=True, capture_output=True, timeout=120)


def png_to_jpeg(png, dest, q=4):
    run(FFMPEG, "-loglevel", "error", "-y", "-i", str(png), "-q:v", str(q), "-map_metadata", "-1", str(dest))
    strip(dest)


FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700'
         '&family=Be+Vietnam+Pro:wght@400&family=JetBrains+Mono:wght@500&display=block">')


def contact_sheet(work, frames, dest):
    """A 4x3 contact sheet on film base: edge print above each frame, sprockets, frame numbers in the rebate."""
    cells = []
    for i, (img, film) in enumerate(frames):
        n = i + 1
        cells.append(f'<div class="cell"><p class="edge">FONDER&nbsp;&nbsp;{html.escape(film.upper())}</p>'
                     f'<div class="holes"></div><div class="pic"><img src="{img.as_uri()}"></div><div class="holes"></div>'
                     f'<p class="num"><span>{n:02d}</span><span>&#9656;{n:02d}A</span></p></div>')
    page = work / "contact.html"
    page.write_text(f"""<!doctype html><meta charset="utf-8">{FONTS}<style>
html,body{{margin:0;width:1600px;height:1100px;background:#0d0c0a;overflow:hidden}}
.sheet{{display:grid;grid-template-columns:repeat(4,384px);grid-auto-rows:366px;column-gap:8px;padding:0 20px;row-gap:1px}}
.cell{{display:grid;grid-template-rows:20px 24px 256px 24px 1fr}}
.edge{{margin:6px 0 0;text-align:center;font:500 10px 'JetBrains Mono';letter-spacing:.08em;color:#a8793c}}
.holes{{background:repeating-linear-gradient(90deg,transparent 0 10px,#2a2622 10px 26px,transparent 26px 49px);
  -webkit-mask:linear-gradient(transparent 4px,#000 4px 20px,transparent 20px)}}
.pic{{display:grid;place-items:center;overflow:hidden}}
.pic img{{max-width:384px;max-height:256px;display:block}}
.num{{margin:0;padding:8px 6px 0;display:flex;justify-content:space-between;font:500 13px 'JetBrains Mono';color:#c08a44;letter-spacing:.06em}}
.num span:first-child{{margin-left:176px}}
</style><div class="sheet">{''.join(cells)}</div>""", encoding="utf-8")
    png = work / "contact.png"
    chrome_shot(page, 1600, 1100, png)
    png_to_jpeg(png, dest, q=6)


def og_image(work, photo, dest):
    page = work / "og.html"
    canister = (OUT / "canisters/olive-neg.png").as_uri()
    page.write_text(f"""<!doctype html><meta charset="utf-8">{FONTS}<style>
html,body{{margin:0;width:1200px;height:630px;overflow:hidden;background:radial-gradient(70% 90% at 30% 45%,#221e1a,#0f0d0c)}}
.can{{position:absolute;left:92px;top:54px;width:250px;filter:drop-shadow(0 18px 26px rgba(0,0,0,.6))}}
h1{{position:absolute;left:70px;top:330px;margin:0;font:700 76px/1 'Bricolage Grotesque';letter-spacing:-.02em;color:#f3efe8}}
p{{position:absolute;left:72px;top:428px;width:360px;margin:0;font:400 30px/1.3 'Be Vietnam Pro';color:#cfc7bc}}
.print{{position:absolute;right:56px;top:50%;height:520px;translate:0 -50%;rotate:1.2deg;box-shadow:0 22px 50px rgba(0,0,0,.6)}}
</style><img class="can" src="{canister}"><h1>Fonder</h1><p>— a film camera<br>for iPhone</p><img class="print" src="{photo.as_uri()}">""",
                    encoding="utf-8")
    png = work / "og.png"
    chrome_shot(page, 1200, 630, png)
    png_to_jpeg(png, dest, q=3)


def slider(before, after):
    for png, name in ((before, "develop-before"), (after, "develop-after")):
        dest = OUT / f"{name}.jpg"
        # Centre-crop to 3:2 (a no-op for a full X-T3 frame), then 1600 px wide at ~q78.
        run(FFMPEG, "-loglevel", "error", "-y", "-i", str(png), "-vf",
            "crop='min(iw,ih*3/2)':'min(ih,iw*2/3)',scale=1600:1067:flags=lanczos", "-q:v", "4", "-map_metadata", "-1", str(dest))
        strip(dest)


def still(render_dir):
    dest = OUT / "still"
    dest.mkdir(parents=True, exist_ok=True)
    for png in sorted(render_dir.glob("*.png")):
        out = dest / f"{png.stem}.jpg"
        # Swatches: a centred square, 128 px (a 64-pt tile at 2x); viewfinder frames as rendered.
        swatch = png.stem.startswith("sw-")
        vf = "crop='min(iw,ih)':'min(iw,ih)',scale=128:128:flags=lanczos" if swatch else "null"
        # Frames at q:v 8: foliage is costly, and the phone shows them at ~280 px wide.
        run(FFMPEG, "-loglevel", "error", "-y", "-i", str(png), "-vf", vf, "-q:v", "5" if swatch else "8", "-map_metadata", "-1", str(out))
        strip(out)


def main(argv):
    if argv[:1] == ["--still"]:
        still(Path(argv[1]))
        print("roll_images: wrote still/*.jpg")
        return
    if argv[:1] == ["--slider"]:
        slider(Path(argv[1]), Path(argv[2]))
        print("roll_images: wrote develop-before.jpg, develop-after.jpg")
        return
    src = Path(argv[0] if argv else Path.home() / "Downloads/today").expanduser()
    heic = lambda name: src / f"{name}.HEIC"
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        for i, (name, _film) in enumerate(PRINTS, 1):
            to_jpeg(heic(name), OUT / f"prints/{i:02d}.jpg", 900, quality=62)
        frames = []
        for i, (name, film) in enumerate(ROLL, 1):
            mid = work / f"roll-{i:02d}.jpg"
            to_jpeg(heic(name), mid, 1200, quality=92)
            frames.append((mid, film))
            # Phone thumbnail: the whole frame fitted into 240x160, padded in the strip's film-base colour.
            thumb = OUT / f"develop/f{i:02d}.jpg"
            thumb.parent.mkdir(parents=True, exist_ok=True)
            run(FFMPEG, "-loglevel", "error", "-y", "-i", str(mid), "-vf",
                "scale=240:160:force_original_aspect_ratio=decrease:flags=lanczos,pad=240:160:(ow-iw)/2:(oh-ih)/2:color=0x0f0e0d",
                "-q:v", "5", "-map_metadata", "-1", str(thumb))
            strip(thumb)
        contact_sheet(work, frames, OUT / "contact.jpg")
        og_src = work / "og-photo.jpg"
        to_jpeg(heic(OG_PHOTO), og_src, 1400, quality=92)
        og_image(work, og_src, OUT / "og.jpg")
    print("roll_images: wrote prints/01..06, develop/f01..f12, contact.jpg, og.jpg")


if __name__ == "__main__":
    main(sys.argv[1:])
