# Changelog

## Unreleased

- Project started: design ([docs/DESIGN.md](docs/DESIGN.md)), licenses and
  notices, and the `param-lineage --version` command.
- The upgrade check page for PX4 v1.17.0 to v1.18.0-rc1, from the earlier
  local project px4-param-upgrade (never published), in [web/](web/).
- Snapshots of every tracked release (v1.12.0 to v1.17.0 with their patch
  releases, and v1.18.0-rc1) in `data/snapshots/`, made by PX4's own
  generators with `python -m paramlineage.extract`, and their JSON Schema.
- Tests: the snapshots against the parameter lists of official PX4 firmware
  builds, known history, the license check, and the extractor on a fake
  source tree. CI checks the schema with a pinned `jsonschema` and extracts
  every release again to compare.
