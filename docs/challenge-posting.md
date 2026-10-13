# Posting the 30-day challenge

`tools/challenge_post.py` posts one day of the challenge to Threads and then Instagram. You
write the day's lines; it adds the "Day NN/30" header and the sign-off, prepares the photo, and
talks to Meta.

Written 2026-10-13. Nothing has been posted with it yet, so the Meta steps below are from
Meta's documentation and not from a run. What is not confirmed is listed at the end.

## Each day

1. **Put the day's files in `challenge/days/`:** `07.txt` and `07.jpg` (`.jpeg`, `.png` and
   `.heic` also work). For a post of several photos, such as the photo and its recipe card, add
   `07-2.jpg`, `07-3.jpg` and so on; they go out in that order as one carousel. The text file is
   the recipe's name on the first line, then your lines:

   ```
   Harvest 400

   this one was made for autumn.
   warm light, dry tones, and that soft seasonal feeling.
   ```

2. **Dry run:** `python3 tools/challenge_post.py 7 --dry-run`. It prints both posts exactly as
   they will read, writes the two public photos to `img/challenge/`, and posts nothing. The
   challenge is counted on Threads only, so Instagram's caption opens with the recipe alone. It
   ends with the hashtags, set as `INSTAGRAM_HASHTAGS` in the script; Threads carries its topic
   tag instead.

   ```
   Threads:
   Day 07/30 — Harvest 400
   this one was made for autumn.
   warm light, dry tones, and that soft seasonal feeling.
   iPhone 16 Pro + Fonder.

   Instagram:
   Harvest 400
   this one was made for autumn.
   warm light, dry tones, and that soft seasonal feeling.
   iPhone 16 Pro + Fonder.

   #fondercam #filmlook #shotoniphone #iphonephotography #indiedev
   ```

3. **Publish and post, from `main`:**
   `source ~/.fonder-challenge.env && python3 tools/challenge_post.py 7 --publish`

   Meta fetches a photo from a public address, so the day's photos have to be on `main`, which
   is what fondercam.online serves. `--publish` commits exactly the day's files (the text and
   the prepared photos under `img/challenge/`), pushes them to `main`, waits
   up to ten minutes for the site to show them, posts to Threads and then Instagram, and
   commits and pushes `challenge/posted.json`. It refuses to run from any other branch.

   The photos you put in `challenge/days/` are never committed, and `.gitignore` keeps them out:
   they still carry what the camera wrote into them, which can include where the photo was
   taken. The prepared copies have that removed.

   Without `--publish` the script touches no git: it posts only once the photos already answer
   on fondercam.online, and says which files to push if they do not.

   `--publish` pushes straight to `main` with no pull request. That is a choice made each time
   by typing the flag; leave it off to publish the photos through a pull request instead.

## Posting on a schedule

GitHub posts the day that is due at **20:00 Hanoi time** every day
(`.github/workflows/challenge-post.yml`), so the Mac can be off. GitHub may start a scheduled
run some minutes late.

1. **Prepare a day ahead, from `main`:** put its text and photos in `challenge/days/`, read the
   dry run, then

   `python3 tools/challenge_post.py 8 --prepare`

   It prepares the photos, commits the day's text and prepared photos, pushes them to `main`,
   waits for fondercam.online to show them, and posts nothing. It needs no tokens. Like
   `--publish`, it pushes straight to `main` with no pull request. Run it again after changing
   the text and it pushes the change.

2. **Which day is due:** the lowest-numbered day that has its text on `main` and is not yet
   posted to both Threads and Instagram. One day goes out per run, so three days prepared at
   once go out on three evenings, in order. A day prepared after 20:00 goes out the next evening.

3. **The run** is `python3 tools/challenge_post.py --due`. It posts the day, then commits and
   pushes `challenge/posted.json`. When nothing is due it does nothing and succeeds. When a post
   is refused the run fails, GitHub sends its usual failure email, and the next run tries the
   same day again; a day that reached Threads but not Instagram is finished on Instagram only.

To post without waiting for 20:00, start the workflow by hand: Actions → Challenge post → Run
workflow. To hold a prepared day back, turn the workflow off there (⋯ → Disable workflow).

The scheduled run reads four repository secrets, named exactly as the environment variables
below: Settings → Secrets and variables → Actions → New repository secret. They are the same
four values as in `~/.fonder-challenge.env`, without the quotes. The tokens last 60 days; when
they are renewed, the secrets have to be replaced too.

Because the scheduled run pushes the log, `--publish`, `--prepare` and `--due` all begin by
pulling `main`.

A day in `posted.json` is not posted twice. `--only threads` or `--only instagram` posts to one
and leaves the other for a later run; `--force` posts a day again.

## The two photos

- `day-NN.jpg` is for Threads: the photo at up to 1440 px on its long edge.
- `day-NN-ig.jpg` is for Instagram, which takes a feed photo between 4:5 and 1.91:1. A taller
  photo (Fonder's 2:3) is centred on a white 4:5 canvas; a photo already inside the range is the
  same picture.

In a post of several photos Instagram crops every photo to the shape of the first, so all of
them are put on one shared shape, the tallest among them: a 3:2 photo beside its squarer recipe
card gets white bands above and below, and the card is not cut.

Both are JPEG with the metadata removed, so no location or device data is published.

## What the script cannot do

- **Music.** The APIs do not attach a song. A day that needs one is posted by hand.
- **The AI label.** Not needed here: these are photographs.

## One-time setup: the Meta developer app

This is yours to do; it needs your Meta login. About half an hour.

### Instagram

1. The Instagram account has to be a professional account (Instagram, Settings, Account type
   and tools). It needs to be one for the ads as well.
2. At developers.facebook.com, My Apps, create an app. Add the **Instagram** product and choose
   **API setup with Instagram login**.
3. App roles, Roles, Add People, **Instagram Tester**, and enter `fonder.app`. Accept the
   invitation in Instagram: Settings, Apps and websites, Tester invites.
4. In the Instagram product's setup page, **Generate access tokens**: add the account, log in,
   and allow `instagram_business_basic` and `instagram_business_content_publish`. Copy the
   token. It lasts 60 days.
5. Get the account's id:
   `curl "https://graph.instagram.com/me?fields=user_id,username&access_token=TOKEN"`

### Threads

1. In the app, add the use case **Access the Threads API**, with the permissions
   `threads_basic` and `threads_content_publish`.
2. App roles, Roles, Add People, **Threads Tester**, and enter `fonder.app`. Accept it in
   Threads: Settings, Account, Website permissions, Invites.
3. Generate a token for the tester from the Threads use case's settings (User Token Generator).
   It lasts 60 days.
4. Get the profile's id:
   `curl "https://graph.threads.net/v1.0/me?fields=id,username&access_token=TOKEN"`

An app in development mode can post to the accounts that are its testers without App Review.

### Where the tokens go

In a file outside this repository, readable only by you:

```
# ~/.fonder-challenge.env   (chmod 600)
export FONDER_THREADS_USER_ID=...
export FONDER_THREADS_TOKEN=...
export FONDER_IG_USER_ID=...
export FONDER_IG_TOKEN=...
```

Never commit a token. The script reads these four from the environment and prints none of them.

A token can be renewed for another 60 days before it runs out:

```
curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=TOKEN"
curl "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=TOKEN"
```

## Not confirmed yet

- **The exact buttons in Meta's dashboard.** Meta renames them often; the steps above name what
  to look for.
- **Instagram's shape limit.** 4:5 to 1.91:1 is from Meta's media reference as I remember it,
  not from the publishing guide. The first real post will show whether the padded photo is
  accepted.
- **The Threads token generator.** If the use case's settings do not offer one, the token comes
  from Meta's authorisation window instead (documented under Threads API, Get started).
- **Carousels.** Posts of several photos use Meta's carousel calls on both platforms. A first
  real Threads carousel was refused because the script joined the items while Threads was still
  fetching them; the script now waits until every item reads `FINISHED`. No carousel has gone
  out since, on either platform.
- **The topic tag.** The script sends `FonderCam` as `topic_tag`, the tag of the FonderCam
  community on Threads that the challenge posts are building. No post has been made with this
  setting yet, so whether the tag alone places a post in the community is not confirmed.