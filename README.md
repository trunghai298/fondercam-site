# fondercam.online

Static site for the Fonder iPhone app, served by GitHub Pages:
landing page, privacy policy (`/privacy/`) and terms of use (`/terms/`).

## Homepage

`/index.html` (English) and `/vi/index.html` (Vietnamese) are generated —
edit the sources below, then rebuild.

- **Sources:** `home/template.html` (one shared template), `home/strings.en.json`
  and `home/strings.vi.json` (the visible copy, one key per `{{placeholder}}`),
  and `config.json` (the action slot and film count).
- **Build:** `python3 tools/build_home.py` writes both pages.
  `python3 tools/build_home.py --check` verifies config, strings, image budget
  and that the committed pages match the sources, without writing anything.
- **Switching the stage:** set `stage` in `config.json` to `follow`, `testflight`
  or `appstore`, and fill in that stage's link. `appstore` also requires
  `img/home/app-store-badge.svg` to exist (Apple's badge art isn't checked in
  yet, so that stage isn't usable until it is).
- **Tests:** `python3 -m unittest discover -s tests -v` runs the build/string/image
  checks. `HOME_SHOTS=1 python3 -m unittest discover -s tests -v` additionally runs
  the headless-Chrome overflow check.
- **Shots:** `python3 tools/shots.py --overflow <path> <width>`,
  `python3 tools/shots.py --lang-bar` and `python3 tools/shots.py --matrix <outdir>`
  (screenshots every chapter across widths, languages, motion/reduced-motion and
  JS/no-JS).
