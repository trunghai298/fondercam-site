import json, re, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_home as b

BASE = {"stage": "follow", "filmCount": 39,
        "instagram": "https://www.instagram.com/fonder.app",
        "threads": "https://www.threads.com/@fonder.app",
        "testflight": "", "appstore": ""}
S = {"action_follow_title": "TestFlight opens soon", "action_follow_body": "Follow Fonder to get the link first.",
     "action_instagram": "Instagram", "action_threads": "Threads",
     "action_testflight": "Join the beta", "action_testflight_note": "Places are limited.",
     "action_appstore_alt": "Download on the App Store"}

class ConfigTests(unittest.TestCase):
    def test_follow_is_valid(self):
        b.validate_config(dict(BASE))
    def test_unknown_stage_refused(self):
        with self.assertRaisesRegex(b.BuildError, "stage"):
            b.validate_config(dict(BASE, stage="beta"))
    def test_testflight_needs_its_link(self):
        with self.assertRaisesRegex(b.BuildError, "testflight"):
            b.validate_config(dict(BASE, stage="testflight"))
    def test_appstore_needs_its_link(self):
        with self.assertRaisesRegex(b.BuildError, "appstore"):
            b.validate_config(dict(BASE, stage="appstore"))
    def test_links_must_be_https(self):
        with self.assertRaisesRegex(b.BuildError, "https"):
            b.validate_config(dict(BASE, instagram="http://instagram.com/x"))
    def test_film_count_positive_int(self):
        with self.assertRaisesRegex(b.BuildError, "filmCount"):
            b.validate_config(dict(BASE, filmCount="39"))
    def test_repo_config_is_valid(self):
        cfg = b.load_config(ROOT / "config.json")
        self.assertEqual(cfg["stage"], "follow")
        self.assertEqual(cfg["instagram"], "https://www.instagram.com/fonder.app")
        self.assertEqual(cfg["threads"], "https://www.threads.com/@fonder.app")

class StringTests(unittest.TestCase):
    def test_parity_names_missing_keys(self):
        with self.assertRaisesRegex(b.BuildError, "only in en: b"):
            b.check_parity({"a": "1", "b": "2"}, {"a": "1"})
    def test_repo_strings_have_parity(self):
        en = json.loads((ROOT / "home/strings.en.json").read_text())
        vi = json.loads((ROOT / "home/strings.vi.json").read_text())
        b.check_parity(en, vi)
    def test_forbidden_names_refused(self):
        for bad in ["Portra 400 look", "like Classic Chrome", "KODAK", "Superia"]:
            with self.assertRaises(b.BuildError, msg=bad):
                b.check_names({"k": bad})
    def test_repo_strings_have_no_forbidden_names(self):
        for lang in ("en", "vi"):
            b.check_names(json.loads((ROOT / f"home/strings.{lang}.json").read_text()))

class FillTests(unittest.TestCase):
    def test_escapes_plain_values(self):
        self.assertEqual(b.fill("<p>{{t}}</p>", {"t": "a < b & c"}), "<p>a &lt; b &amp; c</p>")
    def test_html_keys_pass_through(self):
        self.assertEqual(b.fill("{{x_html}}", {"x_html": "<em>hi</em>"}), "<em>hi</em>")
    def test_unknown_key_refused(self):
        with self.assertRaisesRegex(b.BuildError, "nope"):
            b.fill("{{nope}}", {})
    def test_nested_values(self):
        self.assertEqual(b.fill("{{a}}", {"a": "{{n}} films", "n": "39"}), "39 films")

class ActionTests(unittest.TestCase):
    def test_follow_links_both_accounts(self):
        h = b.action_html(dict(BASE), S)
        self.assertIn('href="https://www.instagram.com/fonder.app"', h)
        self.assertIn('href="https://www.threads.com/@fonder.app"', h)
        self.assertIn("TestFlight opens soon", h)
    def test_testflight_button(self):
        h = b.action_html(dict(BASE, stage="testflight", testflight="https://testflight.apple.com/join/ABC"), S)
        self.assertIn('href="https://testflight.apple.com/join/ABC"', h)
        self.assertIn("Join the beta", h)
    def test_appstore_badge(self):
        h = b.action_html(dict(BASE, stage="appstore", appstore="https://apps.apple.com/app/id1"), S)
        self.assertIn('href="https://apps.apple.com/app/id1"', h)
        self.assertIn('alt="Download on the App Store"', h)
    def test_external_links_are_safe(self):
        h = b.action_html(dict(BASE), S)
        self.assertEqual(h.count('rel="noopener"'), h.count("<a "))

class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = b.build(ROOT)
        cls.en = cls.pages["index.html"]
        cls.vi = cls.pages["vi/index.html"]

    def test_both_pages_built(self):
        self.assertEqual(sorted(self.pages), ["index.html", "vi/index.html"])

    def test_lang_and_hreflang(self):
        self.assertIn('<html lang="en"', self.en)
        self.assertIn('<html lang="vi"', self.vi)
        for page in (self.en, self.vi):
            self.assertIn('hreflang="en" href="https://fondercam.online/"', page)
            self.assertIn('hreflang="vi" href="https://fondercam.online/vi/"', page)
            self.assertIn('hreflang="x-default" href="https://fondercam.online/"', page)

    def test_no_placeholder_left(self):
        for page in (self.en, self.vi):
            self.assertNotIn("{{", page)

    def test_every_chapter_present(self):
        for page in (self.en, self.vi):
            for i in range(5):
                self.assertIn(f'id="ch{i}"', page)

    def test_film_count_filled(self):
        self.assertIn("39 films", self.en)
        self.assertIn("39 loại phim", self.vi)

    def test_action_slot_filled(self):
        self.assertIn("https://www.instagram.com/fonder.app", self.en)
        self.assertIn("TestFlight sắp mở", self.vi)

    def test_every_image_sized_and_described(self):
        for page in (self.en, self.vi):
            for tag in re.findall(r"<img\b[^>]*>", page):
                self.assertRegex(tag, r'width="\d+"', tag)
                self.assertRegex(tag, r'height="\d+"', tag)
                m = re.search(r'alt="([^"]*)"', tag)
                self.assertIsNotNone(m, tag)
                if not m.group(1):
                    self.assertIn('aria-hidden="true"', tag, tag)

    def test_scripts_deferred(self):
        for tag in re.findall(r"<script\b[^>]*src=[^>]*>", self.en):
            self.assertIn("defer", tag)

    def test_pages_are_current(self):
        for rel, content in self.pages.items():
            self.assertEqual((ROOT / rel).read_text(encoding="utf-8"), content,
                             f"{rel} is stale: run python3 tools/build_home.py")


@unittest.skipUnless(__import__("os").environ.get("HOME_SHOTS"), "set HOME_SHOTS=1 to run the browser checks")
class BrowserTests(unittest.TestCase):
    def test_nothing_overflows_at_390_in_vietnamese(self):
        import subprocess
        out = subprocess.run([sys.executable, str(ROOT / "tools/shots.py"), "--overflow", "/vi/", "390"],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip(), "overflow: none")


class ImageTests(unittest.TestCase):
    def test_images_pass_the_check(self):
        b.check_images(ROOT)

    def test_check_refuses_exif(self):
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / "img/home").mkdir(parents=True)
            # A minimal JPEG with an APP1 Exif segment, then SOF0 1x1.
            data = (b"\xff\xd8" + b"\xff\xe1\x00\x08Exif\x00\x00"
                    + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00" + b"\xff\xd9")
            (root / "img/home/x.jpg").write_bytes(data)
            with self.assertRaisesRegex(b.BuildError, "metadata"):
                b.check_images(root)

    def test_every_referenced_image_exists(self):
        for page in b.build(ROOT).values():
            for src in re.findall(r'(?:src|data-src)="(/img/home/[^"]+)"', page):
                self.assertTrue((ROOT / src.lstrip("/")).exists(), src)


class SliderTests(unittest.TestCase):
    def test_slider_is_a_labelled_range(self):
        for page in b.build(ROOT).values():
            m = re.search(r'<input type="range"[^>]*>', page)
            self.assertIsNotNone(m)
            self.assertRegex(m.group(0), r'aria-label="[^"]+"')
            self.assertIn('min="0"', m.group(0)); self.assertIn('max="100"', m.group(0))


if __name__ == "__main__":
    unittest.main()
