import json, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import challenge_post as c


class FakeAPI:
    """Stands in for Meta: records every call and answers the way the two APIs do."""
    def __init__(self, status="FINISHED", item_states=()):
        self.calls, self.status, self.threads, self.media = [], status, 0, 0
        self.item_states = list(item_states)   # what a carousel item answers first; FINISHED after that

    def __call__(self, method, url, params=None):
        self.calls.append((method, url, dict(params or {})))
        if url.endswith("/threads"):
            self.threads += 1
            return {"id": f"T-item{self.threads}" if (params or {}).get("is_carousel_item") else "T-container"}
        if url.endswith("/threads_publish"): return {"id": "T-post"}
        if url.endswith("/media"):
            self.media += 1
            return {"id": f"I-item{self.media}" if (params or {}).get("is_carousel_item") else "I-container"}
        if url.endswith("/media_publish"): return {"id": "I-post"}
        if "I-container" in url: return {"status_code": self.status}
        if "-item" in url:
            state = self.item_states.pop(0) if self.item_states else "FINISHED"
            return {"status": state} if "T-item" in url else {"status_code": state}
        raise AssertionError(f"unexpected call {method} {url}")

    def posts(self): return [u.rsplit("/", 1)[1] for m, u, _ in self.calls if m == "POST"]


ENV = {"FONDER_THREADS_USER_ID": "111", "FONDER_THREADS_TOKEN": "tt",
       "FONDER_IG_USER_ID": "222", "FONDER_IG_TOKEN": "it"}


class DayFileTests(unittest.TestCase):
    def test_first_line_is_the_recipe_and_the_rest_is_kept_as_written(self):
        recipe, lines = c.parse_day("Harvest 400\n\nthis one was made for autumn.\nwarm light, dry tones, and that soft seasonal feeling.\n")
        self.assertEqual(recipe, "Harvest 400")
        self.assertEqual(lines, ["this one was made for autumn.", "warm light, dry tones, and that soft seasonal feeling."])

    def test_a_file_without_a_recipe_or_without_lines_is_refused(self):
        for text in ("", "\n\n", "Harvest 400\n", "Harvest 400\n\n   \n"):
            with self.assertRaises(c.ChallengeError): c.parse_day(text)

    def test_caption_has_the_header_and_the_sign_off(self):
        text = c.caption(6, "Harvest 400", ["this one was made for autumn.", "warm light, dry tones, and that soft seasonal feeling."])
        self.assertEqual(text, "Day 06/30 — Harvest 400\nthis one was made for autumn.\n"
                               "warm light, dry tones, and that soft seasonal feeling.\niPhone 16 Pro + Fonder.")

    def test_instagram_caption_has_no_day_count(self):
        text = c.instagram_caption("Harvest 400", ["this one was made for autumn."])
        self.assertEqual(text, "Harvest 400\nthis one was made for autumn.\niPhone 16 Pro + Fonder.")

    def test_day_must_be_in_the_challenge(self):
        for day in (0, 31, -1):
            with self.assertRaises(c.ChallengeError): c.caption(day, "Harvest 400", ["a line."])

    def test_a_caption_too_long_for_threads_is_refused(self):
        with self.assertRaises(c.ChallengeError): c.caption(1, "Harvest 400", ["x" * 500])


class ImageTests(unittest.TestCase):
    def test_instagram_canvas_pads_a_tall_photo_to_four_by_five(self):
        self.assertEqual(c.instagram_canvas(1000, 1500), (1200, 1500))   # 2:3 is taller than 4:5
        self.assertEqual(c.instagram_canvas(1200, 1500), (1200, 1500))   # 4:5 already
        self.assertEqual(c.instagram_canvas(1500, 1000), (1500, 1000))   # 3:2 is inside the range

    def test_instagram_canvas_pads_a_very_wide_photo_to_the_widest_allowed(self):
        w, h = c.instagram_canvas(3000, 1000)
        self.assertEqual(w, 3000)
        self.assertAlmostEqual(w / h, 1.91, places=2)

    def test_scaled_keeps_the_long_edge_within_the_limit(self):
        self.assertEqual(c.scaled(4000, 6000, 1440), (960, 1440))
        self.assertEqual(c.scaled(800, 600, 1440), (800, 600))

    def test_public_urls_are_on_the_site(self):
        self.assertEqual(c.public_urls(6), [("https://fondercam.online/img/challenge/day-06.jpg",
                                              "https://fondercam.online/img/challenge/day-06-ig.jpg")])
        self.assertEqual(c.public_urls(6, 2)[1], ("https://fondercam.online/img/challenge/day-06-2.jpg",
                                                  "https://fondercam.online/img/challenge/day-06-2-ig.jpg"))

    def test_a_post_of_several_photos_shares_one_instagram_shape(self):
        # A 3:2 photo and its nearly square recipe card: Instagram would crop the card to the
        # photo's shape, so both sit on the card's shape and the photo is padded.
        photo, card = (1440, 960), (1440, 1363)
        aspect = c.carousel_aspect([photo, card])
        self.assertAlmostEqual(aspect, 1440 / 1363)
        self.assertEqual(c.instagram_canvas(*card, aspect), card)
        self.assertEqual(c.instagram_canvas(*photo, aspect), (1440, 1363))
        self.assertIsNone(c.carousel_aspect([photo]), "one photo keeps its own shape")
        # A very tall photo in the set pulls every one to 4:5, the tallest Instagram takes.
        self.assertAlmostEqual(c.carousel_aspect([(1000, 1500), (1440, 960)]), 0.8)


class PostingTests(unittest.TestCase):
    def test_threads_creates_a_container_waits_then_publishes(self):
        api, waits = FakeAPI(), []
        post = c.post_threads(ENV, ["https://x/day.jpg"], "caption", api, waits.append)
        self.assertEqual(post, "T-post")
        self.assertEqual(api.calls[0], ("POST", "https://graph.threads.net/v1.0/111/threads",
                                        {"media_type": "IMAGE", "image_url": "https://x/day.jpg", "text": "caption",
                                         "topic_tag": "FonderCam", "access_token": "tt"}))
        self.assertEqual(api.calls[1], ("POST", "https://graph.threads.net/v1.0/111/threads_publish",
                                        {"creation_id": "T-container", "access_token": "tt"}))
        self.assertEqual(waits, [30], "Meta recommends about 30 seconds before publishing")

    def test_instagram_publishes_once_the_container_is_finished(self):
        api = FakeAPI()
        post = c.post_instagram(ENV, ["https://x/day-ig.jpg"], "caption", api, lambda s: None)
        self.assertEqual(post, "I-post")
        self.assertEqual(api.calls[0], ("POST", "https://graph.instagram.com/222/media",
                                        {"image_url": "https://x/day-ig.jpg", "caption": "caption", "access_token": "it"}))
        self.assertEqual(api.calls[-1], ("POST", "https://graph.instagram.com/222/media_publish",
                                         {"creation_id": "I-container", "access_token": "it"}))

    def test_instagram_gives_up_on_a_container_that_errors_or_never_finishes(self):
        for status in ("ERROR", "IN_PROGRESS"):
            api = FakeAPI(status)
            with self.assertRaises(c.ChallengeError): c.post_instagram(ENV, ["https://x/a.jpg"], "caption", api, lambda s: None)
            self.assertNotIn("media_publish", api.posts())

    def test_several_photos_go_out_as_one_carousel_on_both(self):
        api = FakeAPI()
        self.assertEqual(c.post_threads(ENV, ["https://x/1.jpg", "https://x/2.jpg"], "caption", api, lambda s: None), "T-post")
        items = [p for m, u, p in api.calls if u.endswith("/threads")]
        self.assertEqual(items[0], {"media_type": "IMAGE", "image_url": "https://x/1.jpg", "is_carousel_item": "true", "access_token": "tt"})
        self.assertEqual(items[2], {"media_type": "CAROUSEL", "children": "T-item1,T-item2", "text": "caption",
                                    "topic_tag": "FonderCam", "access_token": "tt"})
        api = FakeAPI()
        self.assertEqual(c.post_instagram(ENV, ["https://x/1.jpg", "https://x/2.jpg"], "caption", api, lambda s: None), "I-post")
        items = [p for m, u, p in api.calls if u.endswith("/media")]
        self.assertEqual(items[1], {"image_url": "https://x/2.jpg", "is_carousel_item": "true", "access_token": "it"})
        self.assertEqual(items[2], {"media_type": "CAROUSEL", "children": "I-item1,I-item2", "caption": "caption", "access_token": "it"})


    def test_a_carousel_is_joined_only_once_every_item_is_finished(self):
        # Meta refuses to join items it is still fetching, which is what a real Threads post met.
        for post, joined in ((c.post_threads, "T-post"), (c.post_instagram, "I-post")):
            api, waits = FakeAPI(item_states=["IN_PROGRESS", "FINISHED", "FINISHED", "IN_PROGRESS"]), []
            self.assertEqual(post(ENV, ["https://x/1.jpg", "https://x/2.jpg"], "caption", api, waits.append), joined)
            carousel = next(i for i, (m, u, p) in enumerate(api.calls) if p.get("media_type") == "CAROUSEL")
            asked = [u for m, u, p in api.calls[:carousel] if m == "GET"]
            self.assertEqual(len(asked), 6, "both items are asked about three times before the carousel is made")
            self.assertEqual(waits[:2], [5, 5])

    def test_a_carousel_item_that_fails_or_never_finishes_stops_the_post(self):
        for post in (c.post_threads, c.post_instagram):
            for states in (["ERROR"], ["IN_PROGRESS"] * 100):
                api = FakeAPI(item_states=states)
                with self.assertRaises(c.ChallengeError):
                    post(ENV, ["https://x/1.jpg", "https://x/2.jpg"], "caption", api, lambda s: None)
                self.assertFalse(any(p.get("media_type") == "CAROUSEL" for m, u, p in api.calls))
                self.assertFalse(any("publish" in u for m, u, p in api.calls))


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "challenge/days").mkdir(parents=True)
        (self.root / "challenge/days/06.txt").write_text("Harvest 400\n\nthis one was made for autumn.\n", encoding="utf-8")
        (self.root / "challenge/days/06.jpg").write_bytes(b"not really a photo")
        self.prepared = []

    def tearDown(self): self.tmp.cleanup()

    def run_it(self, argv, api, live=True, env=ENV, branch="main"):
        out = []
        self.git = []
        def git(*args):
            self.git.append(args)
            if args[:2] == ("rev-parse", "--abbrev-ref"): return branch
            if args[0] == "push": self.pushed = True
            return ""
        code = c.run(argv, root=self.root, env=env, request=api, sleep=lambda s: None, say=out.append,
                     prepare=lambda *a: self.prepared.append(a),
                     is_live=lambda url: live if live is not None else getattr(self, "pushed", False), git=git)
        return code, "\n".join(out)

    def test_dry_run_prepares_and_prints_and_posts_nothing(self):
        api = FakeAPI()
        code, out = self.run_it(["6", "--dry-run"], api)
        self.assertEqual(code, 0)
        self.assertEqual(api.calls, [], "a dry run never calls Meta")
        self.assertIn("Day 06/30 — Harvest 400", out)
        self.assertIn("https://fondercam.online/img/challenge/day-06.jpg", out)
        self.assertEqual(len(self.prepared), 1)
        self.assertFalse((self.root / "challenge/posted.json").exists())

    def test_posts_to_threads_then_instagram_and_records_it(self):
        api = FakeAPI()
        code, _ = self.run_it(["6"], api)
        self.assertEqual(code, 0)
        self.assertEqual(api.posts(), ["threads", "threads_publish", "media", "media_publish"])
        log = json.loads((self.root / "challenge/posted.json").read_text())
        self.assertEqual(log["06"]["threads"], "T-post"); self.assertEqual(log["06"]["instagram"], "I-post")
        sent = {u.rsplit("/", 1)[1]: p for m, u, p in api.calls if u.endswith(("/threads", "/media"))}
        self.assertEqual(sent["threads"]["text"], "Day 06/30 — Harvest 400\nthis one was made for autumn.\niPhone 16 Pro + Fonder.")
        # The challenge is counted on Threads only.
        self.assertEqual(sent["media"]["caption"], "Harvest 400\nthis one was made for autumn.\niPhone 16 Pro + Fonder.")

    def test_a_day_already_posted_is_not_posted_again(self):
        self.run_it(["6"], FakeAPI())
        api = FakeAPI()
        code, out = self.run_it(["6"], api)
        self.assertEqual(api.calls, []); self.assertEqual(code, 0); self.assertIn("already posted", out)

    def test_only_one_platform_leaves_the_other_for_later(self):
        self.run_it(["6", "--only", "threads"], FakeAPI())
        api = FakeAPI()
        self.run_it(["6"], api)
        self.assertEqual(api.posts(), ["media", "media_publish"], "Threads is done; only Instagram is left")

    def test_refuses_to_post_a_photo_that_is_not_live_on_the_site(self):
        api = FakeAPI()
        code, out = self.run_it(["6"], api, live=False)
        self.assertEqual(code, 1); self.assertEqual(api.calls, [])
        self.assertIn("not live", out)

    def test_refuses_to_post_without_the_tokens(self):
        api = FakeAPI()
        code, out = self.run_it(["6"], api, env={})
        self.assertEqual(code, 1); self.assertEqual(api.calls, [])
        self.assertIn("FONDER_THREADS_TOKEN", out)

    def test_extra_photos_are_found_in_order_and_listed(self):
        (self.root / "challenge/days/06-2.png").write_bytes(b"the recipe card")
        code, out = self.run_it(["6", "--dry-run"], FakeAPI())
        self.assertEqual(code, 0)
        sources, outputs = self.prepared[0]
        self.assertEqual([p.name for p in sources], ["06.jpg", "06-2.png"])
        self.assertEqual(outputs[1][1].name, "day-06-2-ig.jpg")
        self.assertIn("https://fondercam.online/img/challenge/day-06-2.jpg", out)

    def test_without_publish_git_is_never_touched(self):
        self.run_it(["6"], FakeAPI())
        self.assertEqual(self.git, [])

    def test_publish_commits_the_days_files_pushes_waits_then_posts(self):
        api = FakeAPI()
        code, out = self.run_it(["6", "--publish"], api, live=None)   # live only once pushed
        self.assertEqual(code, 0, out)
        writes = [g for g in self.git if g[0] in ("add", "commit", "push")]
        self.assertEqual(writes[0], ("add", "--", "challenge/days/06.txt",
                                     "img/challenge/day-06.jpg", "img/challenge/day-06-ig.jpg"))
        self.assertEqual(writes[1], ("commit", "-m", "feat(challenge): day 06 photos"))
        self.assertEqual(writes[2], ("push", "origin", "main"))
        self.assertEqual(api.posts(), ["threads", "threads_publish", "media", "media_publish"])
        # The log of what was posted is published too, so the next run on any machine knows.
        self.assertEqual(writes[3:], [("add", "--", "challenge/posted.json"),
                                      ("commit", "-m", "chore(challenge): day 06 posted"), ("push", "origin", "main")])

    def test_publish_never_stages_a_source_photo(self):
        # A source photo still carries the camera's metadata, which can include where it was taken.
        (self.root / "challenge/days/06-2.heic").write_bytes(b"x")
        code, out = self.run_it(["6", "--publish"], FakeAPI(), live=None)
        self.assertEqual(code, 0, out)
        staged = [path for g in self.git if g[0] == "add" for path in g[2:]]
        self.assertIn("img/challenge/day-06-2.jpg", staged)
        photos = [path for path in staged if path.startswith("challenge/days/") and not path.endswith(".txt")]
        self.assertEqual(photos, [], "only the day's text may be staged from challenge/days/")

    def test_the_repository_ignores_source_photos(self):
        rules = (c.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("challenge/days/*", rules)
        self.assertIn("!challenge/days/*.txt", rules)

    def test_publish_is_refused_off_main_where_a_push_would_publish_nothing(self):
        api = FakeAPI()
        code, out = self.run_it(["6", "--publish"], api, live=False, branch="feat/something")
        self.assertEqual(code, 1); self.assertEqual(api.calls, [])
        self.assertEqual([g for g in self.git if g[0] in ("add", "commit", "push")], [])
        self.assertIn("main", out)

    def test_publish_gives_up_when_the_site_never_shows_the_photos(self):
        api = FakeAPI()
        code, out = self.run_it(["6", "--publish"], api, live=False)
        self.assertEqual(code, 1); self.assertEqual(api.calls, [], "nothing is posted with the photos not live")
        self.assertIn("not live", out)

    def test_a_dry_run_with_publish_commits_nothing(self):
        code, out = self.run_it(["6", "--publish", "--dry-run"], FakeAPI(), live=False)
        self.assertEqual(code, 0)
        self.assertEqual([g for g in self.git if g[0] in ("add", "commit", "push")], [])
        self.assertIn("would commit and push", out)

    def test_a_missing_day_says_which_file_it_wants(self):
        code, out = self.run_it(["7", "--dry-run"], FakeAPI())
        self.assertEqual(code, 1); self.assertIn("challenge/days/07.txt", out)


if __name__ == "__main__":
    unittest.main()
