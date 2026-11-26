import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import build_diary as d

EN = lambda key, source: source


class EmbedTests(unittest.TestCase):
    """An entry can embed a live page of the site, such as an interactive prototype, as a
    figure: a lazy iframe, a caption, and a link to open the page on its own."""
    EMBED = {"embed": {"src": "/diary/index.html", "title": "The mode dial, to try", "height": 700,
                       "caption": "A web mock of the dial. Hold the ring, then slide."}}

    def test_an_embed_is_a_lazy_iframe_with_a_caption_and_a_link_to_open_it(self):
        out = d.block(self.EMBED, "x.p3", EN)
        self.assertIn('<figure class="embed"><iframe src="/diary/index.html"', out)
        self.assertIn('title="The mode dial, to try"', out)
        self.assertIn('height="700"', out)
        self.assertIn('loading="lazy"', out)
        self.assertIn('<figcaption>A web mock of the dial. Hold the ring, then slide.', out)
        self.assertIn('<a href="/diary/index.html">Open it full screen</a>', out)

    def test_an_embed_is_translated_by_its_keys(self):
        seen = []
        d.block(self.EMBED, "x.p3", lambda key, source: seen.append(key) or source)
        self.assertEqual(seen, ["x.p3.title", "x.p3.cap", "page.embed_open"])

    def test_an_embed_of_a_missing_page_fails(self):
        missing = {"embed": {**self.EMBED["embed"], "src": "/diary/demos/nope.html"}}
        with self.assertRaises(SystemExit):
            d.block(missing, "x.p3", EN)

    def test_an_embed_needs_a_title_and_a_caption(self):
        for key in ("title", "caption"):
            bare = {"embed": {k: v for k, v in self.EMBED["embed"].items() if k != key}}
            with self.assertRaises(SystemExit):
                d.block(bare, "x.p3", EN)

    def test_an_embedded_page_may_not_name_a_real_film(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "demo.html").write_text("<p>A roll of Portra 400</p>", encoding="utf-8")
            root, d.ROOT = d.ROOT, Path(tmp)
            try:
                with self.assertRaises(SystemExit):
                    d.block({"embed": {**self.EMBED["embed"], "src": "/demo.html"}}, "x.p3", EN)
            finally:
                d.ROOT = root


if __name__ == "__main__":
    unittest.main()


class LinkTests(unittest.TestCase):
    """A link's address is escaped once: a campaign link's & must reach the browser as &, or the
    App Store reads the campaign as "amp;ct" and never counts it."""

    def test_an_ampersand_in_a_link_is_escaped_once(self):
        html_out = d.inline("[Here it is](https://apps.apple.com/app/id1?pt=2&ct=site-diary&mt=8).")
        self.assertIn('href="https://apps.apple.com/app/id1?pt=2&amp;ct=site-diary&amp;mt=8"', html_out)
        self.assertNotIn("&amp;amp;", html_out)

    def test_the_text_around_a_link_is_still_escaped(self):
        self.assertEqual(d.inline("A & B, [x](https://a.test/)"), 'A &amp; B, <a href="https://a.test/">x</a>')
