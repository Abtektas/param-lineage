# Changelog

## Unreleased

- Project started: design ([docs/DESIGN.md](docs/DESIGN.md)), licenses and
  notices, and the `param-lineage --version` command.
- The upgrade check page for PX4 v1.17.0 to v1.18.0-rc1, from the earlier
  local project px4-param-upgrade (never published), in [web/](web/).
- Snapshots of every tracked release (v1.12.0 to v1.17.0 with their patch
  releases, and v1.18.0-rc1) in `data/snapshots/`, made by PX4's own
  generators with `python -m paramlineage.extract`, and their JSON Schema.
- Translations of every tracked release in `data/translations/`: each
  release's `param_translation.cpp`, compiled unchanged with the harness in
  `src/paramlineage/harness/` and run on probe values with
  `python -m paramlineage.translations`, with what the import does next,
  coverage, and their JSON Schema. CI runs them again and compares. Tests
  run the extractor on a fake release, and values the probes do not reach
  (v1.12 device IDs, v1.18 heater IDs) on the releases' own code.
- Curated facts for the parameters removed from v1.16.2 to v1.17.0 (59) and
  from v1.17.0 to v1.18.0-rc1 (60) in `data/curated/`, and their JSON Schema.
  The v1.18.0-rc1 entries come from the upgrade check page's notes. Tests
  check every entry against the snapshots and the translations, and CI
  checks the commits against PX4's history.
- Changes between every pair of consecutive tracked releases in
  `data/changes/`, built with `python -m paramlineage.changes`, and their
  JSON Schema.
- The history of every parameter in `data/params.json`, built with
  `python -m paramlineage.history`, and its JSON Schema.
- The commands `param-lineage history`, `diff` and `check`. The package
  carries the data they read.
- The upgrade check page is built from this data: the snapshots of
  v1.17.0 and v1.18.0-rc1, the curated facts and the changes between them.
  Its notes are the curated entries; its conversion rules and suggestions
  stay in `web/tools/hints_v1_17_to_v1_18.py`, and its tests check every
  conversion against the translations of v1.18.0-rc1. It now knows
  `HIL_ACT_FUNC1` to `16` and `HIL_ACT_REV`, which it listed as unknown, and
  the notes of seven parameters fixed at their old default show that value
  instead of "{old}". The notes no longer mention fixes proposed to PX4 for
  some of these parameters: curated facts state what the release does.
- The terms say that the code, the data and the documentation were mostly
  written by an AI assistant, that a person has not reviewed all of them, and
  that the authors accept no liability for their errors: in the README, in
  `--version`, after the output of every command and on the page. The curated
  facts are no longer described as written by hand.
- In-place upgrades run in PX4 SITL in `data/sitl/`, made with
  `python -m paramlineage.sitl`, and their JSON Schema: v1.16.2 to v1.17.0
  and v1.17.0 to v1.18.0-rc1, on `px4_sitl_default` with the SIH quadrotor.
  Every conversion runs with a value from each probe case and matches the
  translations; the other removed parameters are dropped; two runs show the
  import order, and one shows that setting an old name by name converts
  nothing. The eight `migrated` entries whose every successor passed are now
  `sitl-tested`. `MOT_POLE_COUNT` is not: the SITL build has no DShot
  parameters.
- Curated facts for the parameters removed from v1.15.4 to v1.16.0 (35) and
  from v1.14.0 to v1.14.1 (1), each read from the commit that removed it and
  from the source of both releases. `check` and `history` now say what
  happened to them.
- Curated facts for the 40 parameters removed from v1.14.4 to v1.15.0, read
  the same way. Three are converted by v1.15.0 (`CBRK_AIRSPD_CHK`,
  `FW_ARSP_MODE`, `SYS_MC_EST_GROUP`) and match its translations; the 20
  `MODAL_IO_*` parameters were renamed to `VOXL_ESC_*`. Every parameter
  removed after v1.14.0 is now curated.
- Every curated entry was read a second time against the source of both
  releases. Commits, pull requests, kinds and fixed values held; 23 notes were
  incomplete or imprecise and are corrected: ten of v1.14.4 to v1.15.0, five of
  v1.15.4 to v1.16.0 and v1.14.0 to v1.14.1, one of v1.16.2 to v1.17.0 and
  seven of v1.17.0 to v1.18.0-rc1, which the upgrade check page shows. The 23
  entries of v1.17.0 to v1.18.0-rc1 that named no pull request now do.
  CONTRIBUTING.md now asks for that second reading.
- Every command now also ends with the trademark notice, in text and in
  JSON, as `--version`, the README and the page already did.
- How to make a release, in [CONTRIBUTING.md](CONTRIBUTING.md), and a test
  of the built wheel and sdist (`PARAMLINEAGE_DIST`): the wheel holds the
  package, the data the commands read and both licenses, and the sdist
  exactly the committed files.
- PX4 v1.18.0 replaces v1.18.0-rc1: its snapshot, translations, firmware
  lists of fmu-v5 and fmu-v6x, changes, histories and SITL run, and the
  upgrade check page for v1.17.0 to v1.18.0. v1.18.0 converts the heater
  parameters (`SENS_IMU_TEMP*`, `SENS_TEMP_ID`) and the `EKF2_AGP_*`
  parameters, which rc1 did not, so their ten curated entries are now
  `migrated` (the five `EKF2_AGP` ones `sitl-tested`), and the page writes
  them to the corrected file instead of suggesting them. `COM_FLTT_LOW_ACT`,
  removed after rc1, has an entry (61 in all). The `SENS_TEMP_ID` entry says
  that its default 0 is not stored and so not converted, which starts the
  heater on boards that enable it without a sensor default.
- The page no longer converts a removed parameter whose value is its old
  default: PX4 does not store such a value, so it does not convert it, and
  the successor keeps its own default (`EKF2_AGP0_NOISE` is 1.0 where
  `EKF2_AGP_NOISE` was 0.9).
- `python -m paramlineage.sitl` finds a value for the import-order runs when
  an enum has no value other than its default and the converted one
  (`EKF2_AGP0_MODE`).
- Tests: the snapshots against the parameter lists of official PX4 firmware
  builds, known history, the license check, and the extractor on a fake
  source tree. CI checks the schema with a pinned `jsonschema` and extracts
  every release again to compare.
