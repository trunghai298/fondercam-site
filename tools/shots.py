#!/usr/bin/env python3
"""Headless-Chrome checks for the homepage. Starts a local server on :8765 for the run.

  --overflow PATH WIDTH   print "overflow: none" or the offending elements
  --lang-bar              print the tests/lang_bar.html results
  --matrix OUTDIR         screenshot every chapter: 390/1280 × en/vi × motion/reduce × js/nojs
"""
import base64, json, os, re, shutil, socket, struct, subprocess, sys, time, urllib.request
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
    m = re.search(r'data-overflow="([^"]*)"', dom)
    return f"overflow: {m.group(1) if m else 'probe missing'}"


def lang_bar():
    dom = chrome("--virtual-time-budget=3000", "--dump-dom", f"{BASE}/tests/lang_bar.html")
    import html
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    return html.unescape(m.group(1)) if m else "no output"


# --- Minimal stdlib WebSocket/CDP client, used only for the true no-JS shots below. ---
# `--disable-javascript` is a no-op in this Chrome build (verified while chasing task 9's
# no-JS matrix: a page with a DOM-mutating <script> mutates identically with or without the
# flag), and `--blink-settings=scriptEnabled=false` crashes headless mode outright. The only
# way to actually block a page's own <script> tags is the DevTools Protocol call
# Emulation.setScriptExecutionDisabled, so the nojs matrix shots go through CDP instead of a
# command-line flag.
class _WS:
    def __init__(self, url):
        rest = url[len("ws://"):]
        host, path = rest.split("/", 1)
        path = "/" + path
        hostname, port = (host.split(":") + ["80"])[:2]
        self.sock = socket.create_connection((hostname, int(port)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
               f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        self._id = 0
        self._buf = b""

    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def call(self, method, params=None, timeout=15):
        self._id += 1
        mid = self._id
        payload = json.dumps({"id": mid, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        ln = len(payload)
        if ln < 126:
            header = struct.pack("!BB", 0x81, 0x80 | ln)
        elif ln < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, ln)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, ln)
        self.sock.sendall(header + mask + masked)
        self.sock.settimeout(timeout)
        while True:
            b1b2 = self._recv_exact(2)
            length = b1b2[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._recv_exact(8))[0]
            data = self._recv_exact(length)
            msg = json.loads(data.decode())
            if msg.get("id") == mid:
                return msg


def _wait_for_devtools(port, tries=50):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
                json.loads(r.read())
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"chrome devtools endpoint on {port} never came up")


def cdp_nojs_screenshot(url, width, height, dest, port=9411):
    """A true no-JS screenshot: launches Chrome with remote debugging, disables script
    execution over CDP, navigates, and captures the viewport. See the _WS docstring above
    for why this is needed instead of a command-line flag."""
    profile = Path(f"/tmp/fonder-shots-nojs-{port}")
    args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "about:blank"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_devtools(port)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
        with urllib.request.urlopen(req, timeout=5) as r:
            tab = json.loads(r.read())
        ws = _WS(tab["webSocketDebuggerUrl"])
        ws.call("Page.enable")
        ws.call("Emulation.setScriptExecutionDisabled", {"value": True})
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 700})
        ws.call("Page.navigate", {"url": url})
        time.sleep(1.5)  # let the (script-free) page load and lay out
        r = ws.call("Page.captureScreenshot", {"format": "png"})
        Path(dest).write_bytes(base64.b64decode(r["result"]["data"]))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


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
                    dest = out / name
                    if js:
                        args = [f"--window-size={width},{height * 9}", "--virtual-time-budget=6000", f"--screenshot={dest}"]
                        if reduce:
                            args.append("--force-prefers-reduced-motion")
                        chrome(*args, f"{BASE}{path}")
                    else:
                        cdp_nojs_screenshot(f"{BASE}{path}", width, height * 9, dest)
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
