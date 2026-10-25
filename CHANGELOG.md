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
- How to make a release, in [CONTRIBUTING.md](CONTRIBUTING.md), and a test
  of the built wheel and sdist (`PARAMLINEAGE_DIST`): the wheel holds the
  package, the data the commands read and both licenses, and the sdist
  exactly the committed files.
- Tests: the snapshots against the parameter lists of official PX4 firmware
  builds, known history, the license check, and the extractor on a fake
  source tree. CI checks the schema with a pinned `jsonschema` and extracts
  every release again to compare.
