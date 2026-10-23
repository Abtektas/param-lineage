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
- Tests: the snapshots against the parameter lists of official PX4 firmware
  builds, known history, the license check, and the extractor on a fake
  source tree. CI checks the schema with a pinned `jsonschema` and extracts
  every release again to compare.
