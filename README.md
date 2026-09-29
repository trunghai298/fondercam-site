# fondercam.online

Static site for the Fonder iPhone app, served by GitHub Pages:
landing page, development diary (`/diary/`), privacy policy (`/privacy/`) and terms of use (`/terms/`).

The diary is generated from `diary/entries/*.json` by `python3 tools/build_diary.py`;
see `diary/README.md`.

## Homepage

`/index.html` (English) and `/vi/index.html` (Vietnamese) are generated —
edit the sources below, then rebuild.

- **Sources:** `home/template.html` (one shared template), `home/strings.en.json`
  and `home/strings.vi.json` (the visible copy, one key per `{{placeholder}}`),
  and `config.json` (the action slot and film count).
- **Build:** `python3 tools/build_home.py` writes both pages.
  `python3 tools/build_home.py --check` verifies config, strings, image budget
  and that the committed pages match the sources, without writing anything.
- **Photos:** `python3 tools/roll_images.py [SOURCE_DIR]` makes the shoot, print, roll-thumbnail,
  contact-sheet and share images from Film Roll renders (HEIC, default `~/Downloads/new shooting`), keeping
  every border and date stamp and stripping metadata. The photo-to-slot mapping is at the top of the script.
  Needs sips, ffmpeg, exiftool and Chrome.
- **Switching the stage:** set `stage` in `config.json` to `follow`, `testflight`
  or `appstore`, and fill in that stage's link. `appstore` also requires
  `img/home/app-store-badge.svg` to exist (Apple's badge art isn't checked in
  yet, so that stage isn't usable until it is).
- **Fonts:** self-hosted in `/fonts` (Google Fonts' latin, latin-ext and Vietnamese subsets, OFL —
  the licences are beside them); `home/home.css` declares them with their unicode ranges, and the
  build preloads the headline and body faces the first screen draws.
- **Tests:** `python3 -m unittest discover -s tests -v` runs the build/string/image
  checks. `HOME_SHOTS=1 python3 -m unittest discover -s tests -v` additionally runs
  the headless-Chrome overflow check.
- **Shots:** `python3 tools/shots.py --overflow <path> <width>`,
  `python3 tools/shots.py --lang-bar` and `python3 tools/shots.py --matrix <outdir>`
  (screenshots every chapter across widths, languages, motion/reduced-motion and
  JS/no-JS).

## Analytics

Google Analytics 4 (`ga4` in `config.json`) runs only after a visitor says OK on the banner: `home/consent.js`
stores the choice in `localStorage` (`fonder-analytics`) and makes no request to Google before then or after
"No thanks". Every page (home EN/VI, diary, privacy, terms) loads it and carries the banner; `tools/build_home.py
--check` holds the id in `consent.js` equal to `config.json` and checks each page. The homepage sends
`chapter_view`, `slider_touch`, `action_click`, `lang_bar_accept` and `diary_click`, plus `page_lang` on every
page view; `python3 tools/shots.py --consent` runs the consent decision's browser checks.
