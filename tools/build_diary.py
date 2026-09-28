#!/usr/bin/env python3
"""Build diary/index.html from diary/chapters.json and diary/entries/*.json.

Usage (from the repository root):  python3 tools/build_diary.py
Only the standard library is used. See diary/README.md for the entry format.
"""
import html
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIARY = ROOT / "diary"
ENTRIES = DIARY / "entries"
OUT = DIARY / "index.html"
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


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


def block(b):
    """One item of an entry's body: a paragraph string, or {"list"|"steps"|"table"|"note": ...}."""
    if isinstance(b, str):
        return f"<p>{inline(b)}</p>"
    if "list" in b:
        return "<ul>" + "".join(f"<li>{inline(x)}</li>" for x in b["list"]) + "</ul>"
    if "steps" in b:
        return '<ol class="steps">' + "".join(f"<li>{inline(x)}</li>" for x in b["steps"]) + "</ol>"
    if "table" in b:
        t = b["table"]
        head = "".join(f"<th scope=\"col\">{inline(c)}</th>" for c in t["head"])
        rows = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
        return f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'
    if "note" in b:
        return f'<p class="note">{inline(b["note"])}</p>'
    fail(f"unknown body block {b!r}")


def figure(img, entry_file):
    path = DIARY / img["file"]
    if not path.exists():
        fail(f"{entry_file}: missing image {img['file']}")
    for key in ("alt", "caption"):
        if not img.get(key):
            fail(f"{entry_file}: image {img['file']} needs '{key}'")
    w, h = jpeg_size(path)
    return (f'<figure><img src="{html.escape(img["file"])}" alt="{html.escape(img["alt"])}" '
            f'width="{w}" height="{h}" loading="lazy" decoding="async">'
            f'<figcaption>{inline(img["caption"])}</figcaption></figure>')


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


def render(chapters, entries):
    by_chapter = {c["id"]: [] for c in chapters}
    for e in sorted(entries, key=lambda e: (e["date"], e["_file"])):
        by_chapter[e["chapter"]].append(e)
    live = [c for c in chapters if by_chapter[c["id"]]]
    latest = max(entries, key=lambda e: (e["date"], e["_file"]))

    toc = "".join(f'<li><a href="#{c["id"]}"><span class="num">{i:02d}</span>{html.escape(c["title"])}</a></li>'
                  for i, c in enumerate(live, 1))
    sections = []
    for i, c in enumerate(live, 1):
        items = []
        for e in by_chapter[c["id"]]:
            body = "".join(block(b) for b in e["body"])
            figs = "".join(figure(img, e["_file"]) for img in e.get("images", []))
            items.append(f'<article class="entry" id="{e["slug"]}">'
                         f'<p class="date"><time datetime="{e["date"]}">{nice_date(e["date"])}</time></p>'
                         f'<h3><a href="#{e["slug"]}">{inline(e["title"])}</a></h3>{body}{figs}</article>')
        intro = f'<p class="intro">{inline(c["intro"])}</p>' if c.get("intro") else ""
        sections.append(f'<section class="chapter" id="{c["id"]}" aria-labelledby="{c["id"]}-h">'
                        f'<h2 id="{c["id"]}-h"><span class="num">{i:02d}</span>{html.escape(c["title"])}</h2>'
                        f'{intro}{"".join(items)}</section>')

    first = min(e["date"] for e in entries)
    page = TEMPLATE
    page = page.replace("{{TOC}}", toc)
    page = page.replace("{{SECTIONS}}", "\n".join(sections))
    page = page.replace("{{LATEST}}", f'<a href="#{latest["slug"]}">{inline(latest["title"])}</a>, {nice_date(latest["date"])}')
    page = page.replace("{{RANGE}}", f"{nice_date(first)} – {nice_date(latest['date'])}")
    page = page.replace("{{COUNT}}", str(len(entries)))
    return page


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Development Diary · Fonder</title>
<meta name="description" content="How Fonder, a film camera for iPhone, is being built: films fitted to real camera renders, camera-style recipes, white balance, Cine video and Film Roll.">
<link rel="icon" href="/icon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/fonts/bricolage-grotesque-700-opsz72-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/be-vietnam-pro-400-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/diary/diary.css">
</head>
<body>
<header class="site-nav">
  <a class="brand" href="/"><img src="/icon.png" width="28" height="28" alt="" aria-hidden="true">Fonder</a>
  <nav><a href="/diary/" aria-current="page">Diary</a></nav>
</header>
<main>
  <header class="intro-head">
    <div class="eyebrow">Fonder · Development diary</div>
    <h1>Building a film camera, frame by frame</h1>
    <p class="lede">Notes from building Fonder: films fitted to real camera renders, recipes that behave like the camera's own controls, and the app around them.</p>
    <p class="meta">{{RANGE}} · {{COUNT}} entries · Latest: {{LATEST}}</p>
  </header>

  <div class="summary" role="note">
    <h2>About these images</h2>
    <p>Every image on this page comes from my own camera files or my own phone, rendered through Fonder. Where a picture sits next to “the camera”, that side is the camera's own JPEG of the same shutter press.</p>
    <p>Some photos used during development and local testing come from <a href="https://www.dpreview.com/sample-galleries/0248558391/">dpreview's public sample gallery</a>. They're used only for testing on my own machines and aren't published here.</p>
    <p>CC, CN, RA and NN stand for the camera simulations each fitted film follows. The film names are Fonder's own.</p>
  </div>

  <nav class="toc" aria-label="Chapters">
    <h2>Chapters</h2>
    <ol>{{TOC}}</ol>
  </nav>

{{SECTIONS}}

</main>
<footer class="site-footer">
  <p>Made in Hà Nội by Trung Hai.</p>
  <nav><a href="/diary/">Diary</a><a href="/privacy/">Privacy</a><a href="/terms/">Terms</a></nav>
</footer>
</body>
</html>
"""


def main():
    chapters, entries = load()
    if not entries:
        fail("no entries in diary/entries/")
    OUT.write_text(render(chapters, entries))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(entries)} entries")


if __name__ == "__main__":
    main()
