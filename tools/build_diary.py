#!/usr/bin/env python3
"""Build diary/index.html (English) and vi/diary/index.html (Vietnamese) from
diary/chapters.json, diary/entries/*.json and diary/strings.vi.csv.

Usage (from the repository root):  python3 tools/build_diary.py
The Vietnamese page mirrors the English structure string for string: every keyed string
(titles, paragraphs, list items, prose table cells, notes, alts, captions) must have its
owner-translated row in diary/strings.vi.csv, keyed <slug>.pN[.liM|.stepM|.hM|.rRcC|.note],
or the build fails. Table cells with no prose (numbers, units) stay as the source writes them.
Only the standard library is used. See diary/README.md for the entry format.
"""
import csv
import html
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_home import FORBIDDEN

ROOT = Path(__file__).resolve().parent.parent
DIARY = ROOT / "diary"
ENTRIES = DIARY / "entries"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
# A table cell carries prose (and so needs a translation) if it has a lowercase word.
PROSE = re.compile(r"[a-z]{3,}")


def fail(msg):
    sys.exit(f"build_diary: {msg}")


def jpeg_size(path):
    """(width, height) from a JPEG's SOF marker, without any imaging library."""
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        fail(f"{path} is not a JPEG")
    i = 2
    while i < len(data):
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
    fail(f"no size found in {path}")


def inline(text):
    """Escape, then allow **bold**, *italic*, `code` and [text](url)."""
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*([^*]+)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', t)
    return t


def nice_date(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def nice_date_vi(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d}/{m}/{y}"


def load_vi_strings(root=None):
    """diary/strings.vi.csv, the owner's translations keyed as the export keyed them."""
    path = Path(root if root is not None else ROOT) / "diary/strings.vi.csv"
    if not path.exists():
        fail(f"{path} is missing")
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["key"]: r["your_vietnamese"] for r in csv.DictReader(f)}


def make_tr(lang, vi):
    """tr(key, source): the source string on the English page; the owner's Vietnamese
    for that key on the Vietnamese page, failing loudly when a row is missing."""
    if lang == "en":
        return lambda key, source: source

    def tr(key, source):
        if key not in vi:
            fail(f"diary/strings.vi.csv is missing key {key!r} (en: {source[:60]!r})")
        return vi[key]
    return tr


def block(b, keybase, tr):
    """One item of an entry's body: a paragraph string, or {"list"|"steps"|"table"|"note": ...}."""
    if isinstance(b, str):
        return f"<p>{inline(tr(keybase, b))}</p>"
    if "list" in b:
        return "<ul>" + "".join(f"<li>{inline(tr(f'{keybase}.li{j}', x))}</li>"
                                for j, x in enumerate(b["list"], 1)) + "</ul>"
    if "steps" in b:
        return '<ol class="steps">' + "".join(f"<li>{inline(tr(f'{keybase}.step{j}', x))}</li>"
                                              for j, x in enumerate(b["steps"], 1)) + "</ol>"
    if "table" in b:
        t = b["table"]
        cell = lambda key, c: tr(key, c) if PROSE.search(c) else c
        head = "".join(f"<th scope=\"col\">{inline(cell(f'{keybase}.h{j}', c))}</th>"
                       for j, c in enumerate(t["head"], 1))
        rows = "".join("<tr>" + "".join(f"<td>{inline(cell(f'{keybase}.r{r}c{j}', c))}</td>"
                                        for j, c in enumerate(rr, 1)) + "</tr>"
                       for r, rr in enumerate(t["rows"], 1))
        return f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
    if "note" in b:
        return f'<p class="note">{inline(tr(f"{keybase}.note", b["note"]))}</p>'
    fail(f"unknown body block {b!r}")


def figure(img, entry_file, slug, j, tr):
    path = DIARY / img["file"]
    if not path.exists():
        fail(f"{entry_file}: missing image {img['file']}")
    for key in ("alt", "caption"):
        if not img.get(key):
            fail(f"{entry_file}: image {img['file']} needs '{key}'")
    w, h = jpeg_size(path)
    cls = ' class="portrait"' if h > 1.3 * w else ''
    return (f'<figure{cls}><img src="/diary/{html.escape(img["file"])}" alt="{html.escape(tr(f"{slug}.alt{j}", img["alt"]))}" '
            f'width="{w}" height="{h}" loading="lazy" decoding="async">'
            f'<figcaption>{inline(tr(f"{slug}.cap{j}", img["caption"]))}</figcaption></figure>')


def load():
    chapters = json.loads((DIARY / "chapters.json").read_text())
    ids = [c["id"] for c in chapters]
    entries = []
    for f in sorted(ENTRIES.glob("*.json")):
        e = json.loads(f.read_text())
        for key in ("date", "chapter", "title", "body"):
            if key not in e:
                fail(f"{f.name}: missing '{key}'")
        if e["chapter"] not in ids:
            fail(f"{f.name}: unknown chapter '{e['chapter']}' (add it to chapters.json)")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"]):
            fail(f"{f.name}: date must be YYYY-MM-DD")
        e["slug"] = f.stem
        e["_file"] = f.name
        entries.append(e)
    return chapters, entries


# The page's own strings (everything outside chapters.json and the entries). English is the
# source; the Vietnamese page takes each one from diary/strings.vi.csv by the same key.
PAGE_EN = {
    "page.meta_title": "Development Diary · Fonder",
    "page.meta_description": "How Fonder, a film camera for iPhone, is being built: films fitted to real camera renders, camera-style recipes, white balance, Cine video and Film Roll.",
    "page.eyebrow": "Fonder · Development diary",
    "page.title": "Building a film camera, frame by frame",
    "page.lede": "Fonder started with a simple question: what if an iPhone camera could feel a little more like shooting film? This is the development diary — the films that worked, the ones that didn't, the tiny details nobody asked for, and everything I'm learning while building it. Colour, grain, cameras, broken builds, long nights and rolls of photos included.",
    "page.lede_sub": "Notes from building Fonder: films fitted to real camera renders, recipes that behave like the camera's own controls, and the app around them.",
    "page.meta_entries": "entries",
    "page.meta_latest": "Latest:",
    "page.toc_title": "Chapters",
    "page.about_title": "About these images",
    "page.about_p1": "Every image on this page comes from my own camera files or my own phone, rendered through Fonder. Where a picture sits next to “the camera”, that side is the camera's own JPEG of the same shutter press.",
    "page.about_p2": "Some photos used during development and local testing come from dpreview's public sample gallery. They're used only for testing on my own machines and aren't published here.",
    "page.about_p3": "CC, CN, RA and NN stand for the camera simulations each fitted film follows. The film names are Fonder's own.",
    "page.footer": "Made in Hà Nội by Trung Hai.",
}
# Chrome that never came from the diary export: nav labels, the language toggle and the
# consent banner, following the homepage's own strings for each language.
CHROME = {
    "en": {"nav_diary": "Diary", "nav_privacy": "Privacy", "nav_terms": "Terms",
           "toggle_label": "Tiếng Việt", "toggle_href": "/vi/diary/", "toggle_lang": "vi",
           "home_href": "/",
           "consent_text": "This site uses Google Analytics to count visits. OK?",
           "consent_ok": "OK", "consent_no": "No thanks"},
    "vi": {"nav_diary": "Nhật ký", "nav_privacy": "Quyền riêng tư", "nav_terms": "Điều khoản",
           "toggle_label": "English", "toggle_href": "/diary/", "toggle_lang": "en",
           "home_href": "/vi/",
           "consent_text": "Trang này dùng Google Analytics để đếm lượt truy cập. Đồng ý?",
           "consent_ok": "Đồng ý", "consent_no": "Không"},
}


def render(chapters, entries, lang, vi):
    tr = make_tr(lang, vi)
    ch = CHROME[lang]
    date_fmt = nice_date if lang == "en" else nice_date_vi
    self_href = "/diary/" if lang == "en" else "/vi/diary/"

    by_chapter = {c["id"]: [] for c in chapters}
    for e in sorted(entries, key=lambda e: (e["date"], e["_file"])):
        by_chapter[e["chapter"]].append(e)
    live = [c for c in chapters if by_chapter[c["id"]]]
    latest = max(entries, key=lambda e: (e["date"], e["_file"]))

    def ch_title(c):
        return html.escape(tr("chapter.%s.title" % c["id"], c["title"]))

    toc = "".join(f'<li><a href="#{c["id"]}"><span class="num">{i:02d}</span>{ch_title(c)}</a></li>'
                  for i, c in enumerate(live, 1))
    sections = []
    for i, c in enumerate(live, 1):
        items = []
        for e in by_chapter[c["id"]]:
            slug = e["slug"]
            body = "".join(block(b, f"{slug}.p{j}", tr) for j, b in enumerate(e["body"], 1))
            figs = "".join(figure(img, e["_file"], slug, j, tr)
                           for j, img in enumerate(e.get("images", []), 1))
            items.append(f'<article class="entry" id="{slug}">'
                         f'<p class="date"><time datetime="{e["date"]}">{date_fmt(e["date"])}</time></p>'
                         f'<h3><a href="#{slug}">{inline(tr(f"{slug}.title", e["title"]))}</a></h3>{body}{figs}</article>')
        intro = (f'<p class="intro">{inline(tr("chapter.%s.intro" % c["id"], c["intro"]))}</p>'
                 if c.get("intro") else "")
        sections.append(f'<section class="chapter" id="{c["id"]}" aria-labelledby="{c["id"]}-h">'
                        f'<h2 id="{c["id"]}-h"><span class="num">{i:02d}</span>{ch_title(c)}</h2>'
                        f'{intro}{"".join(items)}</section>')

    first = min(e["date"] for e in entries)
    p = lambda key: tr(key, PAGE_EN[key])
    latest_title = tr(f"{latest['slug']}.title", latest["title"])
    vn_preload = ('\n<link rel="preload" href="/fonts/be-vietnam-pro-400-vietnamese.woff2" as="font" type="font/woff2" crossorigin>'
                  if lang == "vi" else "")
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(p("page.meta_title"))}</title>
<meta name="description" content="{html.escape(p("page.meta_description"))}">
<link rel="canonical" href="https://fondercam.online{self_href}">
<link rel="alternate" hreflang="en" href="https://fondercam.online/diary/">
<link rel="alternate" hreflang="vi" href="https://fondercam.online/vi/diary/">
<link rel="alternate" hreflang="x-default" href="https://fondercam.online/diary/">
<link rel="icon" href="/icon.png?v=2">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=2">
<link rel="preload" href="/fonts/bricolage-grotesque-700-opsz72-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/be-vietnam-pro-400-latin.woff2" as="font" type="font/woff2" crossorigin>{vn_preload}
<link rel="stylesheet" href="/diary/diary.css">
<script defer src="/home/consent.js"></script>
</head>
<body>
<header class="site-nav">
  <a class="brand" href="{ch["home_href"]}"><img src="/icon.png" width="28" height="28" alt="" aria-hidden="true">Fonder</a>
  <nav><a href="{self_href}" aria-current="page">{html.escape(ch["nav_diary"])}</a><a href="{ch["toggle_href"]}" hreflang="{ch["toggle_lang"]}" lang="{ch["toggle_lang"]}">{html.escape(ch["toggle_label"])}</a></nav>
</header>
<main>
  <header class="intro-head">
    <div class="eyebrow">{html.escape(p("page.eyebrow"))}</div>
    <h1>{html.escape(p("page.title"))}</h1>
    <p class="lede">{html.escape(p("page.lede"))}</p>
    <p class="lede lede-sub">{html.escape(p("page.lede_sub"))}</p>
    <p class="meta">{date_fmt(first)} – {date_fmt(latest["date"])} · {len(entries)} {html.escape(p("page.meta_entries"))} · {html.escape(p("page.meta_latest"))} <a href="#{latest["slug"]}">{inline(latest_title)}</a>, {date_fmt(latest["date"])}</p>
  </header>

  <div class="summary" role="note">
    <h2>{html.escape(p("page.about_title"))}</h2>
    <p>{inline(p("page.about_p1"))}</p>
    <p>{inline(p("page.about_p2")).replace("dpreview", '<a href="https://www.dpreview.com/sample-galleries/0248558391/">dpreview</a>', 1)}</p>
    <p>{inline(p("page.about_p3"))}</p>
  </div>

  <nav class="toc" aria-label="{html.escape(p("page.toc_title"))}">
    <h2>{html.escape(p("page.toc_title"))}</h2>
    <ol>{toc}</ol>
  </nav>

{chr(10).join(sections)}

</main>
<footer class="site-footer">
  <p>{html.escape(p("page.footer"))}</p>
  <nav><a href="{self_href}">{html.escape(ch["nav_diary"])}</a><a href="/privacy/">{html.escape(ch["nav_privacy"])}</a><a href="/terms/">{html.escape(ch["nav_terms"])}</a></nav>
</footer>
<div class="consent-bar" hidden>
  <p>{html.escape(ch["consent_text"])}</p>
  <button class="consent-yes" type="button">{html.escape(ch["consent_ok"])}</button>
  <button class="consent-no" type="button">{html.escape(ch["consent_no"])}</button>
</div>
</body>
</html>
"""


def check_names(page, where):
    """Whole words only, as the recipes page checks (never 'across'/'portraits')."""
    low = page.lower()
    for name in FORBIDDEN:
        if re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", low):
            fail(f"{where} names a real film or simulation ({name!r})")


def main():
    chapters, entries = load()
    if not entries:
        fail("no entries in diary/entries/")
    vi = load_vi_strings()
    for lang, rel in (("en", "diary/index.html"), ("vi", "vi/diary/index.html")):
        page = render(chapters, entries, lang, vi)
        check_names(page, rel)
        out = ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
        print(f"wrote {rel}: {len(entries)} entries")


if __name__ == "__main__":
    main()
