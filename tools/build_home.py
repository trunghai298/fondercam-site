#!/usr/bin/env python3
"""Build index.html (English) and vi/index.html (Vietnamese) from home/template.html,
home/strings.*.json and config.json.

Usage (from the repository root):
  python3 tools/build_home.py          # write both pages
  python3 tools/build_home.py --check  # verify config, strings, images and that pages are current
Only the standard library is used.
"""
import html
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGES = ("follow", "testflight", "appstore")
# Real stock and camera-simulation names never appear on the site (owner's rule).
FORBIDDEN = ["kodak", "fuji", "portra", "ektar", "ektachrome", "gold 200", "ultramax", "superia",
             "provia", "velvia", "astia", "classic chrome", "classic neg", "nostalgic neg",
             "reala", "eterna", "acros", "cinestill", "ilford", "agfa", "lomography"]


class BuildError(Exception):
    pass


def validate_config(cfg, root=None):
    if cfg.get("stage") not in STAGES:
        raise BuildError(f"config stage must be one of {STAGES}, got {cfg.get('stage')!r}")
    n = cfg.get("filmCount")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise BuildError("config filmCount must be a positive integer")
    for key in ("instagram", "threads", "testflight", "appstore"):
        value = cfg.get(key, "")
        if value and not value.startswith("https://"):
            raise BuildError(f"config {key} must be an https:// link")
    for key in ("instagram", "threads"):
        if not cfg.get(key):
            raise BuildError(f"config {key} is required")
    if cfg["stage"] in ("testflight", "appstore") and not cfg.get(cfg["stage"]):
        raise BuildError(f"config stage is {cfg['stage']} but its link ({cfg['stage']}) is empty")
    if "ga4" in cfg and not re.fullmatch(r"G-[A-Z0-9]{6,12}", str(cfg["ga4"])):
        raise BuildError(f"config ga4 must be a GA4 measurement id like G-XXXXXXXXXX, got {cfg['ga4']!r}")
    if cfg["stage"] == "appstore":
        badge = Path(root if root is not None else ROOT) / "img/home/app-store-badge.svg"
        if not badge.exists():
            raise BuildError("config stage is appstore but img/home/app-store-badge.svg does not exist — "
                              "add Apple's official badge art before switching to this stage")


def load_config(path):
    path = Path(path)
    cfg = json.loads(path.read_text(encoding="utf-8"))
    validate_config(cfg, root=path.parent)
    return cfg


def check_parity(en, vi):
    only_en = sorted(set(en) - set(vi))
    only_vi = sorted(set(vi) - set(en))
    if only_en or only_vi:
        raise BuildError(f"string keys differ — only in en: {', '.join(only_en) or '-'}; only in vi: {', '.join(only_vi) or '-'}")


def check_names(strings):
    for key, value in strings.items():
        low = value.lower()
        for name in FORBIDDEN:
            if name in low:
                raise BuildError(f"string {key} names a real film or simulation ({name!r})")


_PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")


def fill(text, values, _depth=0):
    """Replace {{key}}. Values are escaped unless the key ends in _html; values may hold placeholders."""
    if _depth > 3:
        raise BuildError("placeholders nest too deeply")

    def sub(m):
        key = m.group(1)
        if key not in values:
            raise BuildError(f"unknown placeholder {{{{{key}}}}}")
        value = fill(str(values[key]), values, _depth + 1)
        return value if key.endswith("_html") else html.escape(value, quote=True)

    return _PLACEHOLDER.sub(sub, text)


def _link(href, label, cls):
    return f'<a class="{cls}" href="{html.escape(href)}" rel="noopener" target="_blank">{html.escape(label)}</a>'


def action_html(cfg, s):
    stage = cfg["stage"]
    if stage == "follow":
        return (f'<p class="action-title">{html.escape(s["action_follow_title"])}</p>'
                f'<p class="action-body">{html.escape(s["action_follow_body"])}</p>'
                f'<p class="action-buttons">{_link(cfg["instagram"], s["action_instagram"], "btn")}'
                f'{_link(cfg["threads"], s["action_threads"], "btn")}</p>')
    if stage == "testflight":
        return (f'<p class="action-buttons">{_link(cfg["testflight"], s["action_testflight"], "btn btn-primary")}</p>'
                f'<p class="action-body">{html.escape(s["action_testflight_note"])}</p>')
    return (f'<a class="badge" href="{html.escape(cfg["appstore"])}" rel="noopener" target="_blank">'
            f'<img src="/img/home/app-store-badge.svg" width="156" height="52" alt="{html.escape(s["action_appstore_alt"])}"></a>')


# Chapter 3's prints, in fan order: (file in img/home/prints, the film it was shot on).
# tools/roll_images.py makes the files from the source renders.
FAN_PRINTS = [("01", "Dusk"), ("02", "Dusk"), ("03", "Dusk"),
              ("04", "Toffee Neg"), ("05", "Toffee Neg"), ("06", "Toffee Neg")]

# A 1x1 transparent GIF: the src for chapter images until home.js's IntersectionObserver
# swaps in data-src as their chapter approaches. The <noscript> twin covers the no-JS path.
LAZY_PLACEHOLDER = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"


def fan_html(s, root=ROOT):
    items = []
    for i, (fid, film) in enumerate(FAN_PRINTS):
        src = f"/img/home/prints/{fid}.jpg"
        w, h = jpeg_size(root / src.lstrip("/"))   # each print keeps its own ratio (3:2 or 4:3)
        alt = fill(s["alt_ch3_print"], {"film": film})
        items.append(f'<li class="print-card" style="--i:{i}"><img hidden src="{LAZY_PLACEHOLDER}" data-src="{src}" width="{w}" height="{h}" '
                     f'alt="{alt}"><noscript><img src="{src}" width="{w}" height="{h}" alt="{alt}"></noscript><span class="pencil">{html.escape(film)}</span></li>')
    return "".join(items)


def lazy_img(src, w, h, cls=""):
    """A decorative chapter image that loads as its chapter approaches, with its no-JS twin."""
    c = f' class="{cls}"' if cls else ""
    return (f'<img{c} hidden src="{LAZY_PLACEHOLDER}" data-src="{src}" width="{w}" height="{h}" alt="" aria-hidden="true">'
            f'<noscript><img{c} src="{src}" width="{w}" height="{h}" alt="" aria-hidden="true"></noscript>')


# Chapter 1's viewfinder, in the order the scroll shows them (tools/roll_images.py --still makes them).
# The last is the finished state, and the one shown without motion.
STILL_FRAMES = ["01-summer", "02-hanoi", "03-amber", "04-stillair", "05-k3200", "06-k7000", "07-grain"]
# The recipe strip: (look id, name, the fitted simulation's letters the app puts on its tile, or "").
STILL_STRIP = [("summer", "Summer Chrome", ""), ("hanoi", "Ha Noi Chrome", ""), ("amber", "Amber 400", ""),
               ("chrome50", "Chrome 50", ""), ("stillair", "Still Air 100", "CC"), ("ordinaryday", "Ordinary Day 200", "RA")]
STILL_ACTIVE = "stillair"


def cam_vf_html():
    return "".join(lazy_img(f"/img/home/still/{n}.jpg", 600, 900, f"vf vf-{i + 1}") for i, n in enumerate(STILL_FRAMES))


def cam_strip_html():
    tiles = []
    for i, (lid, name, badge) in enumerate(STILL_STRIP):
        on = " is-on" if lid == STILL_ACTIVE else ""
        chip = f'<span class="sw-chip">{badge}</span>' if badge else ""
        tiles.append(f'<div class="sw sw-{i}{on}"><div class="sw-img">{lazy_img(f"/img/home/still/sw-{lid}.jpg", 128, 128)}{chip}'
                     f'<i class="sw-ring"></i></div><p class="sw-name"><span class="sw-dim">{html.escape(name)}</span>'
                     f'<span class="sw-on">{html.escape(name)}</span></p></div>')
    return "".join(tiles)


def cam_recent_html():
    # The last shot before the scroll's, then the one the scroll takes (the finished frame).
    return (lazy_img("/img/home/develop/f05.jpg", 240, 160, "rc-old")
            + lazy_img(f"/img/home/still/{STILL_FRAMES[-1]}.jpg", 600, 900, "rc-new"))


DEVELOP_FRAMES = 12


def sheet_html():
    """The #ch2 phone's contact sheet: strips of four frames, each a numbered dark slot with
    its developed photo on top (hidden until home.js develops it, or shown when motion is off)."""
    strips = []
    for start in range(1, DEVELOP_FRAMES + 1, 4):
        frames = []
        for n in range(start, start + 4):
            src = f"/img/home/develop/f{n:02d}.jpg"
            frames.append(f'<div class="app-frame"><span class="app-slot">{n:02d}</span>'
                          f'<img hidden src="{LAZY_PLACEHOLDER}" data-src="{src}" width="240" height="160" alt="" aria-hidden="true">'
                          f'<noscript><img src="{src}" width="240" height="160" alt="" aria-hidden="true"></noscript>'
                          f'<span class="app-fn"><span class="fn-dim">{n:02d} ▸</span><span class="fn-on">{n:02d} ▸</span></span></div>')
        strips.append(f'<div class="app-strip">{"".join(frames)}</div>')
    return "".join(strips)


def font_preload_html(lang):
    """Preload what the first screen draws: the headline's face and the body text (the Vietnamese
    page's accents are a separate subset). The rest load on use (unicode-range in home.css)."""
    files = ["bricolage-grotesque-700-opsz72-latin", "be-vietnam-pro-400-latin"]
    if lang == "vi":
        files.append("be-vietnam-pro-400-vietnamese")
    return "\n".join(f'<link rel="preload" href="/fonts/{f}.woff2" as="font" type="font/woff2" crossorigin>' for f in files)


def render_page(template, strings, cfg, lang):
    en_home, vi_home = "https://fondercam.online/", "https://fondercam.online/vi/"
    values = dict(strings)
    values.update({
        "lang": lang,
        "stage": cfg["stage"],
        "film_count": str(cfg["filmCount"]),
        "canonical": en_home if lang == "en" else vi_home,
        "home_href": "/" if lang == "en" else "/vi/",
        "alt_href": "/vi/" if lang == "en" else "/",
        "alt_lang": "vi" if lang == "en" else "en",
        "action_html": action_html(cfg, strings),
        "fan_html": fan_html(strings),
        "sheet_html": sheet_html(),
        "font_preload_html": font_preload_html(lang),
        "cam_vf_html": cam_vf_html(),
        "cam_strip_html": cam_strip_html(),
        "cam_recent_html": cam_recent_html(),
        "cam_shot_html": lazy_img(f"/img/home/still/{STILL_FRAMES[-1]}.jpg", 600, 900),
        "develop_total": str(DEVELOP_FRAMES),
    })
    return fill(template, values)


def build(root):
    cfg = load_config(root / "config.json")
    template = (root / "home/template.html").read_text(encoding="utf-8")
    strings = {lang: json.loads((root / f"home/strings.{lang}.json").read_text(encoding="utf-8")) for lang in ("en", "vi")}
    check_parity(strings["en"], strings["vi"])
    for s in strings.values():
        check_names(s)
    return {"index.html": render_page(template, strings["en"], cfg, "en"),
            "vi/index.html": render_page(template, strings["vi"], cfg, "vi")}


def jpeg_size(path):
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise BuildError(f"{path} is not a JPEG")
    i = 2
    while i < len(data) - 3:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    raise BuildError(f"no size found in {path}")


def check_images(root, budget=3_200_000, long_edge=1600):
    total = 0
    for path in sorted((root / "img/home").rglob("*")):
        if not path.is_file():
            continue
        total += path.stat().st_size
        if path.suffix.lower() == ".jpg":
            data = path.read_bytes()
            if b"Exif\x00" in data[:65536] or b"http://ns.adobe.com/xap" in data[:65536]:
                raise BuildError(f"{path.relative_to(root)} still carries metadata (EXIF/XMP)")
            w, h = jpeg_size(path)
            if max(w, h) > long_edge:
                raise BuildError(f"{path.relative_to(root)} is {w}x{h}; long edge must be ≤ {long_edge}")
    if total > budget:
        raise BuildError(f"img/home totals {total} bytes; budget is {budget}")


CONSENT_PAGES = ["index.html", "vi/index.html", "diary/index.html", "privacy/index.html", "terms/index.html"]


def check_consent(root, cfg):
    """Analytics is one id in two places — config.json and home/consent.js — and every page that
    counts must load consent.js and carry the banner it asks with. Nothing loads Google otherwise."""
    gid = cfg.get("ga4")
    if not gid:
        return
    js = (Path(root) / "home/consent.js").read_text(encoding="utf-8")
    if f"const ID = '{gid}';" not in js:
        raise BuildError(f"home/consent.js does not carry config ga4 {gid}")
    for rel in CONSENT_PAGES:
        page = (Path(root) / rel).read_text(encoding="utf-8")
        if '<script defer src="/home/consent.js"></script>' not in page:
            raise BuildError(f"{rel} does not load /home/consent.js")
        if not re.search(r'<div class="consent-bar" hidden>.*?<button class="consent-yes" type="button">[^<]+</button>'
                         r'\s*<button class="consent-no" type="button">[^<]+</button>', page, re.S):
            raise BuildError(f"{rel} has no consent banner with named OK and No buttons")


def main(argv):
    check = "--check" in argv
    try:
        if check:
            check_images(ROOT)
            check_consent(ROOT, load_config(ROOT / "config.json"))
        pages = build(ROOT)
    except BuildError as e:
        sys.exit(f"build_home: {e}")
    for rel, content in pages.items():
        path = ROOT / rel
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                sys.exit(f"build_home: {rel} is stale; run python3 tools/build_home.py")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print("build_home: " + ("pages are current" if check else f"wrote {', '.join(pages)}"))


if __name__ == "__main__":
    main(sys.argv[1:])
