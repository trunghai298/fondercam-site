import json, sys, unittest
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

if __name__ == "__main__":
    unittest.main()
