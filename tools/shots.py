#!/usr/bin/env python3
"""Headless-Chrome checks for the homepage. Starts a local server on :8765 for the run.

  --overflow PATH WIDTH   print "overflow: none" or the offending elements
  --lang-bar              print the tests/lang_bar.html results
  --matrix OUTDIR         screenshot every chapter: 390/1280 × en/vi × motion/reduce × js/nojs
"""
import json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = "http://localhost:8765"


def chrome(*args):
    return subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", *args],
                          capture_output=True, text=True, timeout=120).stdout


def with_server(fn):
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765"], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.8)
        return fn()
    finally:
        srv.terminate()


def overflow(path, width):
    # home.js runs the overflow probe when the URL has ?probe=overflow and writes the result to <body data-overflow>.
    dom = chrome(f"--window-size={width},900", "--virtual-time-budget=4000", "--run-all-compositor-stages-before-draw",
                 f"--dump-dom", f"{BASE}{path}?probe=overflow")
    import re
    m = re.search(r'data-overflow="([^"]*)"', dom)
    return f"overflow: {m.group(1) if m else 'probe missing'}"


def lang_bar():
    dom = chrome("--virtual-time-budget=3000", "--dump-dom", f"{BASE}/tests/lang_bar.html")
    import re, html
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    return html.unescape(m.group(1)) if m else "no output"


def matrix(outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    shots = []
    for width, height in ((390, 844), (1280, 800)):
        for path, lang in (("/", "en"), ("/vi/", "vi")):
            for js in (True, False):
                for reduce in (False, True):
                    if not js and reduce:
                        continue
                    name = f"{lang}-{width}-{'js' if js else 'nojs'}-{'reduce' if reduce else 'motion'}.png"
                    args = [f"--window-size={width},{height * 9}", "--virtual-time-budget=6000", f"--screenshot={out / name}"]
                    if not js:
                        # Ruling 6: --blink-settings=scriptEnabled=false crashes this Chrome build.
                        args.append("--disable-javascript")
                    if reduce:
                        args.append("--force-prefers-reduced-motion")
                    chrome(*args, f"{BASE}{path}")
                    shots.append(name)
    return "\n".join(shots)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--overflow"]:
        print(with_server(lambda: overflow(a[1], int(a[2]))))
    elif a[:1] == ["--lang-bar"]:
        print(with_server(lang_bar))
    elif a[:1] == ["--matrix"]:
        print(with_server(lambda: matrix(a[1])))
    else:
        sys.exit(__doc__)
