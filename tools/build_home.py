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


def validate_config(cfg):
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


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_config(cfg)
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


FAN_FILMS = [("olive-neg", "Olive Neg"), ("lantern-neg", "Lantern Neg"), ("toffee-neg", "Toffee Neg"),
             ("guava-neg", "Guava Neg"), ("ink-neg", "Ink Neg"), ("pollen-neg", "Pollen Neg")]


def fan_html(s):
    items = []
    for i, (fid, name) in enumerate(FAN_FILMS):
        alt = fill(s["alt_ch3_print"], {"film": name})
        items.append(f'<li class="print-card" style="--i:{i}"><img src="/img/home/prints/{fid}.jpg" width="1200" height="800" '
                     f'loading="lazy" alt="{alt}"><span class="pencil">{html.escape(name)}</span></li>')
    return "".join(items)


def render_page(template, strings, cfg, lang):
    en_home, vi_home = "https://fondercam.online/", "https://fondercam.online/vi/"
    values = dict(strings)
    values.update({
        "lang": lang,
        "film_count": str(cfg["filmCount"]),
        "canonical": en_home if lang == "en" else vi_home,
        "home_href": "/" if lang == "en" else "/vi/",
        "alt_href": "/vi/" if lang == "en" else "/",
        "alt_lang": "vi" if lang == "en" else "en",
        "action_html": action_html(cfg, strings),
        "fan_html": fan_html(strings),
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


def main(argv):
    check = "--check" in argv
    try:
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
