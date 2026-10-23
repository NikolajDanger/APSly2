# Nerd zone
Want to have a bit of a poke at the code? Go for it! Bug fixes, new options, logic improvements, client tweaks, tests: all welcome. Open a pull request and describe what you changed and why.

## Developing
Unlike many other apworld repos, this repo isn't a fork of the Archipelago source: every import from the Archipelago source (`BaseClasses`, `worlds.AutoWorld`, `CommonClient`, ...) needs to come from somewhere. The way this repo is developed is to clone [Archipelago](https://github.com/ArchipelagoMW/Archipelago), and then link this repository into its `worlds` folder under the name `Sly2`, so Archipelago loads it like any in-tree world:

- Linux / macOS:
  ```sh
  ln -s /path/to/APSly2 /path/to/Archipelago/worlds/Sly2
  ```
- Windows (from an administrator `cmd`):
  ```bat
  mklink /D C:\path\to\Archipelago\worlds\Sly2 C:\path\to\APSly2
  ```
  (I think. Please let me know if it doesn't work like that; I haven't used Windows in years.)

With the link in place, the Archipelago launcher, `Generate.py`, and the "Sly 2 Client" all pick up your working copy directly: no need to rebuild the apworld to test a change. Point your editor at the Archipelago checkout for imports (I do it with `.vscode/settings.json`, through `python.analysis.extraPaths`).

Style is enforced with [ruff](https://docs.astral.sh/ruff/) (`pip install ruff`, then `ruff check .` from the repo root): 2-space indentation, 80-column lines, type hints on every function. Types are checked with [pyright](https://github.com/microsoft/pyright) in "basic" mode (`pip install pyright`, then `PYTHONPATH=/path/to/Archipelago pyright -p build/pyright.json` from the repo root; that's the same engine Pylance uses in VS Code).

## Tests
The test suite in `test/` runs inside Archipelago's own test runner, so it needs the link above. From the Archipelago checkout:
```sh
AP_TEST_WORLDS=Sly2 python -m pytest -q test/general worlds/Sly2
```
`worlds/Sly2` is this repo's suite; `test/general` is Archipelago's generic per-world checks.

There is also an end-to-end suite in `e2e/` that runs against a real PCSX2 with the game loaded, over PINE. It is never picked up by the command above (or by any Archipelago-wide test run): it only runs when asked for explicitly. From the Archipelago checkout:
```
SLY2_E2E=1 SLY2_E2E_ISO="/path/to/Sly 2.iso" python -m worlds.Sly2.e2e
```
With `SLY2_E2E_ISO` set the suite starts `pcsx2-qt` itself (`SLY2_E2E_PCSX2` picks another binary) when nothing answers on PINE, and shuts it down afterwards; PINE must be enabled in PCSX2's settings (slot 28011). Without it, the suite connects to a PCSX2 you already have running with the game loaded and no other PINE client attached, and skips when none answers.
The suite loads the savestates checked in under `e2e/states/` through PCSX2 savestate slot 99 and never touches your own slots. `e2e/states/README.md` lists what each state contains and how to recapture one with `python -m worlds.Sly2.e2e.capture_state <name>`.

## Building
`build/build.sh` lints, type checks, runs the test suite, and zips the repo into `build/target/sly2_apworld-<date_time>/` (the `.apworld` plus `sly2.yaml`). It's a bash script, so on Windows use Git Bash or WSL. It needs `zip`, `rsync`, `pip`, `ruff` and `pyright` on the path, and `AP_ROOT` pointing at your Archipelago checkout (the script checks that `$AP_ROOT/worlds/Sly2` really resolves to the repo being built):

```sh
AP_ROOT=/path/to/Archipelago ./build/build.sh   # build a bundle
./build/build.sh clean                          # remove old bundles
```

A failing test aborts the build. When `SLY2_E2E_ISO` is set the end-to-end suite runs as well (starting PCSX2 itself); otherwise it is skipped. The checkout is also where the bundled `archipelago.json` gets its container `version`/`compatible_version` from.
