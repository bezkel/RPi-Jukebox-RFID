# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository context

This is the **Version 2.x** branch of Phoniebox / RPi-Jukebox-RFID — a Raspberry Pi contactless
jukebox driven by RFID cards, GPIO buttons, a PHP web app and MPD/Mopidy as the audio backend.
Version 2 is in maintenance mode; the actively developed rewrite lives on the
`future3/main` and `future3/develop` branches (a Python core + React web client) and is a
**completely different codebase**. Do not copy patterns or imports between the two — work on
v2 stays in shell, PHP and the Python helper scripts in this tree.

Default working branch is `develop` (PRs from `master` are discouraged). The version is
tracked in `settings/version-number`.

## Languages and how they fit together

The codebase is a polyglot stack glued together by the filesystem and `systemd`:

* **Bash scripts** in `scripts/` are the runtime control plane. The web UI and the RFID
  daemon both shell out to scripts like `rfid_trigger_play.sh`, `playout_controls.sh`,
  `shuffle_play.sh`, `resume_play.sh`, `single_play.sh`. These scripts talk to MPD over
  `nc localhost 6600` and read/write small state files under `settings/` (one file per
  setting, e.g. `settings/Max_Volume_Limit`, `settings/Second_Swipe`).
* **Python daemons** in `scripts/` (`daemon_rfid_reader.py` + the various `Reader.py.*`
  variants) read RFID cards and invoke `rfid_trigger_play.sh` per swipe. The `Reader.py`
  symlink/copy is chosen at install time from the `Reader.py.*` flavors (USB HID,
  experimental, KKMoon, PC/SC, etc.) according to the user's hardware.
* **PHP web app** in `htdocs/` is the user-facing control surface, served by the Phoniebox's
  webserver. `htdocs/inc.*.php` are includes used by the top-level pages
  (`index.php`, `settings.php`, `cardEdit.php`, …); `htdocs/api/` holds the AJAX/JSON
  endpoints; `htdocs/ajax.*.php` are status pollers. `htdocs/config.php` is generated from
  `config.php.sample` on first request.
* **GPIO control** is its own Python service under `components/gpio_control/`, configured by
  the user's `settings/gpio_settings.ini` and run via `systemctl … phoniebox-gpio-control`.
* **Install scripts** in `scripts/installscripts/` provision a fresh Raspberry Pi OS image
  (packages, MPD, autohotspot, optionally Spotify, optional GPIO/RFID setup) and lay down the
  systemd units that tie the pieces above together.

The `settings/` directory is the shared state — most of the gitignored files there are
created at install/runtime, and the small files there are the contract between the bash
scripts, the PHP UI, and the Python daemons.

## Components

`components/` holds opt-in hardware/feature subsystems, each in its own subfolder with its own
`README.md`, `requirements.txt` and install script. New hardware support belongs here, not in
`scripts/`. Folder layout convention (from `CONTRIBUTING.md`):

* sub-folders are plural categories (`displays`, `rfid-reader`, `controls`, `audio`)
* sub-sub-folders are specific products (`PN532`, `RC522`, `dot-matrix-module-MAX7219`)
* every folder gets a `README.md`

Owned subtrees (see `.github/CODEOWNERS`): `components/controls/buttons_usb_encoder`
(@jeripeierSBB), `components/synchronisation/sync-shared` (@AlvinSchiller),
`scripts/installscripts/install-jukebox.sh` (@jeripeierSBB),
`scripts/helperscripts/setup_autohotspot.sh` (@Groovylein).

## Commands

### Python (linting + tests)

```bash
pip install -r requirements.txt -r requirements-GPIO.txt
pip install flake8 pytest pytest-cov mock

flake8 --config .flake8
pytest --cov --cov-config=.coveragerc --cov-report xml
```

`flake8` is configured with `filename = *.py,*.py.*` so it lints the `Reader.py.*` variants
too. CI runs on Python 3.9–3.12 (`.github/workflows/pythonpackage.yml`).

The actual Python tests today live under `components/gpio_control/test/`. A single test:

```bash
pytest components/gpio_control/test/test_SimpleButton.py::TestButton::test_init
```

`components/gpio_control/test/conftest.py` mocks `RPi`/`RPi.GPIO` so the suite runs without
real hardware — any new GPIO-touching test must rely on this fixture rather than importing
hardware modules directly.

### PHP (PHPUnit)

```bash
composer install
composer test       # excludes the @real-env group (default in CI)
composer test-all   # includes @real-env (needs MPD/etc. actually running)
```

PHP tests use `php-mock` to stub built-ins like `parse_ini_file`, `exec` and `file_get_contents`
inside the `JukeBox\…` namespaces — see `tests/htdocs/api/PlayerTest.php` for the pattern.
Tests `require_once` the page under test, so any new page-level test needs to mock the I/O
that page touches.

### Markdown

```bash
npx markdownlint-cli2 --config .markdownlint-cli2.yaml "**/*.md"
```

`htdocs/**` is excluded from markdown linting.

### Install / Docker

`ci/Dockerfile.debian` builds a Debian image (bullseye/bookworm, armv6/armv7) that the
install scripts can run against. See `ci/README.md` for how to build and exec into the image,
and `scripts/installscripts/tests/test_installation.sh` for the per-edition verification
called by CI (`test_docker_debian.yml`).

`tests/test-commandline-shellscripts.sh` is a manual / interactive harness for the playout
scripts; it is **not** wired into CI and expects sample audio set up by
`scripts/helperscripts/CreateSampleAudiofoldersStreams.sh`.

## Conventions worth knowing

* **GPIO library**: use `RPi.GPIO` API only. The actual installed package is `rpi-lgpio` (a
  drop-in shim — see `requirements.txt` and `requirements-excluded.txt`). Do **not** add
  `RPi.GPIO` or `gpiozero` as a dependency; `RPi.GPIO` breaks GPIO on kernel ≥ 6.6 (bookworm),
  and `gpiozero` is intentionally not used in v2. Behavior differences vs. the original
  library (notably `bouncetime` and `hold_time`) are documented in
  `components/gpio_control/README.md`.
* **Reader.py variants**: don't edit `scripts/Reader.py` in a way that breaks the
  `Reader.py.<flavor>` pattern — the install script picks one of them and copies it in place.
  When adding RFID hardware, add a new `Reader.py.<name>` rather than branching inside an
  existing one. Note `scripts/Reader.py.pcsc` and `components/displays/HD44780-i2c/` are
  excluded from flake8 because they come from external sources.
* **Naming**: files and folders are lowercase with dashes (`bluetooth-sink-switch`,
  `dot-matrix-module-MAX7219`), general → specific. Product IDs keep their original casing
  and come last. Every component folder gets a `README.md`.
* **flake8**: max line length 127, max complexity 12; see `.flake8` for the per-file ignores
  (notably `components/smart-home-automation/MQTT-protocol/daemon_mqtt_client.py` and the USB
  encoder buttons).
* **Trivial commits**: prefix with `(docs)`, `(maint)` or `(packaging)` per
  `CONTRIBUTING.md`; non-trivial commits should reference an issue.
* **EditorConfig**: 4-space indent for everything, 2-space for `*.js`, `*.yaml`, `*.yml`. LF
  line endings, trailing whitespace trimmed except in markdown.

## CI workflows

`.github/workflows/`:

* `pythonpackage.yml` — flake8 + pytest on Python 3.9–3.12, runs on every push except
  `future3/**`.
* `php.yml` — `composer validate` + `composer test` on PHP 8.x, only on pushes/PRs to
  `develop`.
* `test_docker_debian.yml` — builds the Debian image and runs the install scripts for
  bookworm/bullseye on `linux/arm/v7`. Path-filtered to `ci/`, `packages*.txt`,
  `requirements*.txt`, `scripts/installscripts/**`, `scripts/helperscripts/setup_*`,
  `misc/sampleconfigs/**`, `settings/version-number` and the workflow file itself.
* `markdown.yml` — markdownlint, only when `**.md` changes.
* `codeql-analysis.yml`, `release.yml` — CodeQL + release packaging.
