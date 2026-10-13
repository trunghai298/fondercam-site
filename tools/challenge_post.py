#!/usr/bin/env python3
"""Post one day of the 30-day challenge to Threads and Instagram.

Usage (from the repository root):
  python3 tools/challenge_post.py 6 --dry-run     # prepare the photos, print everything, post nothing
  python3 tools/challenge_post.py 6               # post day 6 to Threads, then Instagram
  python3 tools/challenge_post.py 6 --only threads
  python3 tools/challenge_post.py 8 --prepare     # put day 8 on the site for the scheduled run; post nothing
  python3 tools/challenge_post.py --due           # post the next prepared day (what the scheduled run does)

A day is a text file and its photos in challenge/days: NN.txt and NN.jpg, then NN-2.jpg,
NN-3.jpg for a post of several photos (.jpeg, .png and .heic also work).
NN.txt is the recipe's name on the first line, then the lines of the post as they should read.
The "Day NN/30" header and the sign-off are added here.

Each photo is written to img/challenge/ in two sizes. Meta's APIs fetch a photo from a public
address, so those files have to be live on fondercam.online before anything is posted:
commit and push them, then run this again. docs/challenge-posting.md has the whole routine
and the one-time Meta app setup.

Only the standard library is used; sips and ffmpeg prepare the photos.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://fondercam.online"
DAYS = 30
SIGN_OFF = "iPhone 16 Pro + Fonder."
# Instagram's caption ends with these, after an empty line. Threads uses its topic tag instead.
# Five is the most Instagram counts: the brand's own tag, then what the photo is, then who made it.
INSTAGRAM_HASHTAGS = "#fondercam #filmlook #shotoniphone #iphonephotography #indiedev"
TOPIC_TAG = "FonderCam"
THREADS_LIMIT = 500
# Threads takes a photo up to 1440 px wide; the same long edge is plenty for Instagram.
LONG_EDGE = 1440
# Instagram's feed takes a photo between 4:5 and 1.91:1; anything outside is padded to fit.
IG_TALLEST, IG_WIDEST = 4 / 5, 1.91
PAD_COLOUR = "white"
PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".heic")
# Both platforms take up to this many photos in one post.
MOST_PHOTOS = 10
THREADS_API = "https://graph.threads.net/v1.0"
INSTAGRAM_API = "https://graph.instagram.com"
SECRETS = ("FONDER_THREADS_USER_ID", "FONDER_THREADS_TOKEN", "FONDER_IG_USER_ID", "FONDER_IG_TOKEN")


class ChallengeError(Exception):
    pass


# The post

def parse_day(text):
    """The recipe's name from the first line, and the post's own lines after it."""
    lines = [line.strip() for line in text.splitlines()]
    kept = [line for line in lines if line]
    if len(kept) < 2:
        raise ChallengeError("a day file is the recipe's name on the first line, then at least one line of the post")
    return kept[0], kept[1:]


def caption(day, recipe, lines):
    if not 1 <= day <= DAYS:
        raise ChallengeError(f"day must be 1 to {DAYS}, got {day}")
    text = "\n".join([f"Day {day:02d}/{DAYS} — {recipe}", *lines, SIGN_OFF])
    if len(text) > THREADS_LIMIT:
        raise ChallengeError(f"the post is {len(text)} characters; Threads allows {THREADS_LIMIT}")
    return text


def instagram_caption(recipe, lines):
    """The challenge is counted on Threads only, so Instagram's caption opens with the recipe alone.
    It ends with the hashtags, which Threads does not carry."""
    return "\n".join([recipe, *lines, SIGN_OFF, "", INSTAGRAM_HASHTAGS])


# The photos

def scaled(width, height, long_edge):
    longest = max(width, height)
    if longest <= long_edge:
        return width, height
    return round(width * long_edge / longest), round(height * long_edge / longest)


def instagram_canvas(width, height, aspect=None):
    """The canvas a photo sits on for Instagram: its own size when its shape is allowed (and is
    `aspect`, when one is asked for), or padded out to the shape wanted."""
    wanted = min(max(aspect if aspect is not None else width / height, IG_TALLEST), IG_WIDEST)
    if abs(width / height - wanted) < 0.005:
        return width, height
    if width / height < wanted:
        return round(height * wanted), height
    return width, round(width / wanted)


def carousel_aspect(sizes):
    """One shape for every photo of a post. Instagram crops a post's photos to its first one,
    so they are all padded to the tallest shape among them and nothing is cut off."""
    return min(max(w / h, IG_TALLEST) for w, h in sizes) if len(sizes) > 1 else None


def public_paths(day, count=1):
    """(Threads path, Instagram path) for each photo of the day."""
    names = [f"day-{day:02d}" + (f"-{i}" if i > 1 else "") for i in range(1, count + 1)]
    return [(f"img/challenge/{name}.jpg", f"img/challenge/{name}-ig.jpg") for name in names]


def public_urls(day, count=1):
    return [tuple(f"{SITE}/{path}" for path in pair) for pair in public_paths(day, count)]


def source_photos(root, day):
    """NN.jpg, then NN-2.jpg, NN-3.jpg … for as long as they run on."""
    found = []
    for i in range(1, MOST_PHOTOS + 1):
        stem = f"{day:02d}" + (f"-{i}" if i > 1 else "")
        match = next((root / f"challenge/days/{stem}{s}" for s in PHOTO_TYPES if (root / f"challenge/days/{stem}{s}").exists()), None)
        if match is None:
            break
        found.append(match)
    if not found:
        raise ChallengeError(f"no photo for day {day}: challenge/days/{day:02d}.jpg (or .jpeg, .png, .heic) is missing")
    return found


def prepared_count(root, day):
    """How many prepared photos the day has under img/challenge/, each with its Instagram copy."""
    count = 0
    for plain, padded in public_paths(day, MOST_PHOTOS):
        if not ((root / plain).exists() and (root / padded).exists()):
            break
        count += 1
    return count


def due_day(root, log):
    """The lowest-numbered day that has its text in challenge/days/ and is not yet posted to both.
    One day goes out per scheduled run, so days prepared ahead go out in order, a day apart."""
    for day in range(1, DAYS + 1):
        posted = log.get(f"{day:02d}", {})
        if (root / f"challenge/days/{day:02d}.txt").exists() and not ("threads" in posted and "instagram" in posted):
            return day
    return None


def photo_size(source):
    try:
        out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(source)],
                             capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        raise ChallengeError(f"could not read {source.name} as a photo")
    size = {line.split(":")[0].strip(): int(line.split(":")[1]) for line in out.splitlines() if "pixel" in line}
    return size["pixelWidth"], size["pixelHeight"]


def prepare_photos(sources, outputs):
    """Writes the two public files for each photo: resized, as JPEG, with no metadata."""
    sizes = [scaled(*photo_size(source), LONG_EDGE) for source in sources]
    aspect = carousel_aspect(sizes)
    for source, (width, height), (plain, padded) in zip(sources, sizes, outputs):
        canvas_w, canvas_h = instagram_canvas(width, height, aspect)
        plain.parent.mkdir(parents=True, exist_ok=True)
        # sips reads HEIC and applies the photo's rotation; ffmpeg then resizes, pads and drops the metadata.
        upright = plain.with_suffix(".tmp.jpg")
        try:
            subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "100", str(source), "--out", str(upright)],
                           capture_output=True, check=True)
            base = ["ffmpeg", "-v", "error", "-y", "-i", str(upright), "-map_metadata", "-1", "-q:v", "2"]
            subprocess.run([*base, "-vf", f"scale={width}:{height}:flags=lanczos", str(plain)], check=True)
            if (canvas_w, canvas_h) == (width, height):
                shutil.copyfile(plain, padded)   # already a shape Instagram takes
            else:
                subprocess.run([*base, "-vf", f"scale={width}:{height}:flags=lanczos,"
                                              f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color={PAD_COLOUR}", str(padded)], check=True)
        except subprocess.CalledProcessError as error:
            raise ChallengeError(f"could not prepare {source.name}: {error.cmd[0]} failed")
        finally:
            upright.unlink(missing_ok=True)


# Meta

def http(method, url, params=None):
    data = urllib.parse.urlencode(params or {}).encode()
    request = urllib.request.Request(url, data=data if method == "POST" else None, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        # Meta explains a refusal in the body; the token never appears in it.
        raise ChallengeError(f"{url.split('?')[0]} answered {error.code}: {error.read().decode(errors='replace')[:400]}")


def url_is_live(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def wait_for_items(api, items, field, token, request, sleep):
    """Holds until Meta has fetched every carousel item. Joining items it is still fetching is
    refused as 'children invalid', so ask every five seconds, for no more than two minutes."""
    for attempt in range(24):
        states = [request("GET", f"{api}/{item}?" + urllib.parse.urlencode({"fields": field, "access_token": token}))[field]
                  for item in items]
        if all(state == "FINISHED" for state in states):
            return
        failed = [state for state in states if state not in ("FINISHED", "IN_PROGRESS")]
        if failed:
            raise ChallengeError(f"a photo could not be taken for the carousel: its status is {failed[0]}")
        sleep(5)
    raise ChallengeError("the carousel's photos were still being fetched after two minutes; nothing was published")


def post_threads(env, image_urls, text, request, sleep):
    """One photo is a post of its own; several are a carousel of item containers."""
    user, token = env["FONDER_THREADS_USER_ID"], env["FONDER_THREADS_TOKEN"]
    words = {"text": text, "topic_tag": TOPIC_TAG, "access_token": token}
    if len(image_urls) == 1:
        container = request("POST", f"{THREADS_API}/{user}/threads",
                            {"media_type": "IMAGE", "image_url": image_urls[0], **words})["id"]
    else:
        items = [request("POST", f"{THREADS_API}/{user}/threads",
                         {"media_type": "IMAGE", "image_url": url, "is_carousel_item": "true", "access_token": token})["id"]
                 for url in image_urls]
        wait_for_items(THREADS_API, items, "status", token, request, sleep)
        container = request("POST", f"{THREADS_API}/{user}/threads",
                            {"media_type": "CAROUSEL", "children": ",".join(items), **words})["id"]
    sleep(30)   # Meta's recommended wait before publishing a container
    return request("POST", f"{THREADS_API}/{user}/threads_publish", {"creation_id": container, "access_token": token})["id"]


def post_instagram(env, image_urls, text, request, sleep):
    user, token = env["FONDER_IG_USER_ID"], env["FONDER_IG_TOKEN"]
    if len(image_urls) == 1:
        container = request("POST", f"{INSTAGRAM_API}/{user}/media",
                            {"image_url": image_urls[0], "caption": text, "access_token": token})["id"]
    else:
        items = [request("POST", f"{INSTAGRAM_API}/{user}/media",
                         {"image_url": url, "is_carousel_item": "true", "access_token": token})["id"]
                 for url in image_urls]
        wait_for_items(INSTAGRAM_API, items, "status_code", token, request, sleep)
        container = request("POST", f"{INSTAGRAM_API}/{user}/media",
                            {"media_type": "CAROUSEL", "children": ",".join(items), "caption": text, "access_token": token})["id"]
    # Meta's guidance: ask once a minute, for no more than five minutes.
    for attempt in range(5):
        status = request("GET", f"{INSTAGRAM_API}/{container}?" + urllib.parse.urlencode(
            {"fields": "status_code", "access_token": token}))["status_code"]
        if status == "FINISHED":
            return request("POST", f"{INSTAGRAM_API}/{user}/media_publish", {"creation_id": container, "access_token": token})["id"]
        if status != "IN_PROGRESS":
            raise ChallengeError(f"Instagram could not take the post: the container's status is {status}")
        sleep(60)
    raise ChallengeError("Instagram was still processing the post after five minutes; nothing was published there")


# The site

def run_git(root):
    def git(*args):
        done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        if done.returncode != 0:
            raise ChallengeError(f"git {args[0]} failed: {done.stderr.strip()[:300]}")
        return done.stdout.strip()
    return git


def publish(git, files, message):
    """Commits exactly these files and pushes them. Only ever from main: the site is served from
    main, so a push from anywhere else would publish nothing."""
    git("add", "--", *files)
    git("commit", "-m", message)
    # main may have moved since the run began: the scheduled run and this machine both push to it.
    git("pull", "--rebase", "--autostash", "origin", "main")
    git("push", "origin", "main")


# The run

def run(argv, root=ROOT, env=os.environ, request=http, sleep=time.sleep, say=print,
        prepare=prepare_photos, is_live=url_is_live, git=None):
    parser = argparse.ArgumentParser(description="Post one day of the 30-day challenge to Threads and Instagram.")
    parser.add_argument("day", type=int, nargs="?")
    parser.add_argument("--dry-run", action="store_true", help="prepare the photos and print the post; post nothing")
    parser.add_argument("--only", choices=("threads", "instagram"), help="post to one of the two")
    parser.add_argument("--force", action="store_true", help="post again a day the log says is posted")
    parser.add_argument("--publish", action="store_true",
                        help="commit the day's files and push them to main, wait for the site, then post")
    parser.add_argument("--prepare", action="store_true",
                        help="commit the day's files and push them to main for the scheduled run; post nothing")
    parser.add_argument("--due", action="store_true",
                        help="post the next prepared day that is not posted yet; takes no day")
    args = parser.parse_args(argv)
    root = Path(root)
    try:
        if args.due and (args.day is not None or args.prepare or args.publish or args.force):
            raise ChallengeError("--due picks the day itself: give it no day, and none of --prepare, --publish, --force")
        if args.prepare and (args.publish or args.only or args.force):
            raise ChallengeError("--prepare posts nothing, so it takes none of --publish, --only, --force")
        if not args.due and args.day is None:
            raise ChallengeError("give a day, or --due to post the next prepared day")
        pushes = (args.publish or args.prepare or args.due) and not args.dry_run
        if pushes:
            git = git or run_git(root)
            if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
                raise ChallengeError("--publish, --prepare and --due work from main only: the site is served "
                                     "from main, so a push from another branch would publish nothing")
            # The log of what is posted is pushed by whichever machine posted; read the latest.
            git("pull", "--rebase", "--autostash", "origin", "main")
        log_file = root / "challenge/posted.json"
        log = json.loads(log_file.read_text(encoding="utf-8")) if log_file.exists() else {}
        day = due_day(root, log) if args.due else args.day
        if day is None:
            say("Nothing is due: every prepared day is posted.")
            return 0
        key = f"{day:02d}"
        day_file = root / f"challenge/days/{key}.txt"
        if not day_file.exists():
            raise ChallengeError(f"no text for day {day}: challenge/days/{key}.txt is missing")
        recipe, lines = parse_day(day_file.read_text(encoding="utf-8"))
        text = caption(day, recipe, lines)
        instagram_text = instagram_caption(recipe, lines)
        if args.due:
            # The scheduled run has no source photos and no sips: it posts what --prepare pushed.
            count = prepared_count(root, day)
            if not count:
                raise ChallengeError(f"day {day} has its text but no prepared photos under img/challenge/: "
                                     f"run this with {day} --prepare")
        else:
            sources = source_photos(root, day)
            count = len(sources)
        paths = public_paths(day, count)
        if not args.due:
            prepare(sources, [(root / plain, root / padded) for plain, padded in paths])
        urls = public_urls(day, count)
        threads_urls, instagram_urls = [u[0] for u in urls], [u[1] for u in urls]

        done = {} if args.force else log.get(key, {})
        wanted = [name for name in ("threads", "instagram") if args.only in (None, name) and name not in done]
        live = {url: is_live(url) for url in threads_urls + instagram_urls}

        say("Threads:")
        say(text)
        say("")
        say("Instagram:")
        say(instagram_text)
        say("")
        for label, group in (("Threads", threads_urls), ("Instagram", instagram_urls)):
            for url in group:
                say(f"{label + ' photo:':17}{url}  ({'live' if live[url] else 'not live yet'})")
        if not wanted:
            say(f"Day {day} is already posted: {', '.join(f'{k} {v}' for k, v in done.items() if k != 'at')}")
            return 0
        # The source photos stay on this machine: they still carry what the camera wrote into them
        # (time, and the place when location is on). Only the prepared copies, which have none, go out.
        day_files = [f"challenge/days/{key}.txt", *(path for pair in paths for path in pair)]
        if args.dry_run:
            if args.publish or args.prepare:
                say(f"Dry run: would commit and push {', '.join(day_files)}.")
            if args.prepare:
                say("Dry run: --prepare posts nothing.")
            else:
                say(f"Dry run: would post to {' then '.join(wanted)}. Nothing was posted.")
            return 0
        if args.publish or args.prepare:
            # --prepare also pushes a change to the text alone, which the live photos would not show.
            if not all(live.values()) or (args.prepare and git("status", "--porcelain", "--", *day_files)):
                publish(git, day_files, f"feat(challenge): day {key} photos")
                say("Pushed the day's files; waiting for fondercam.online to show them.")
                # GitHub Pages usually takes a minute or two; ask every 20 seconds for ten minutes.
                for attempt in range(30):
                    live = {url: is_live(url) for url in live}
                    if all(live.values()):
                        break
                    sleep(20)
        if args.prepare:
            if not all(live.values()):
                raise ChallengeError("the day's files are pushed but fondercam.online does not show the photos yet; "
                                     "the scheduled run will refuse the day until it does")
            say(f"Day {day} is prepared and live. Nothing was posted: the scheduled run posts the next "
                "prepared day that is not posted yet.")
            return 0
        if not all(live.values()):
            files = ", ".join(path for pair in paths for path in pair)
            raise ChallengeError(f"the photos are not live on fondercam.online yet: commit and push {files}, "
                                 "wait for the site, then run this again")
        needed = [name for name in SECRETS
                  if ("THREADS" in name and "threads" in wanted) or ("IG" in name and "instagram" in wanted)]
        missing = [name for name in needed if not env.get(name)]
        if missing:
            raise ChallengeError(f"missing {', '.join(missing)}: see docs/challenge-posting.md")

        entry = dict(log.get(key, {}))
        posted = []
        try:
            for name in wanted:
                post = post_threads(env, threads_urls, text, request, sleep) if name == "threads" \
                    else post_instagram(env, instagram_urls, instagram_text, request, sleep)
                entry[name] = post
                entry["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                # Written after each post, so a failure on the second never loses the first.
                log[key] = entry
                log_file.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                posted.append(name)
                say(f"Posted to {name}: {post}")
        finally:
            # Pushed even when the second post fails: the scheduled run starts from a fresh copy
            # each time, and without the log it would post the first one again.
            if posted and (args.publish or args.due):
                publish(git, ["challenge/posted.json"], f"chore(challenge): day {key} posted")
        return 0
    except ChallengeError as error:
        say(f"challenge_post: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
