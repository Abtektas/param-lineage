# param-lineage

Parameter history for PX4: a machine-readable record of how PX4 parameters
change between releases.

**Status: early development. There is no release yet. The snapshots are
built; the rest of the data described below is not yet.** The plan is in
[docs/DESIGN.md](docs/DESIGN.md).

## Why

PX4 renames, removes and changes parameters in most releases. When it renames
one, PX4 can convert the stored value as it upgrades a vehicle in place
(`param_translation.cpp`). A parameter file saved on the old release and loaded
later does not get that conversion: values under old names are dropped
silently.

What changed is written down today only as prose, in release notes and wiki
pages. param-lineage turns it into data that tools can use:

- every parameter of every tracked release, extracted with PX4's own
  generators from the release tag;
- the conversions PX4 performs on upgrade, parsed from each release;
- for every parameter a release removed, what happened to it, with the commit
  as evidence;
- a history per parameter, and a list of changes between any two releases.

## Data

| What | Where | Status |
|---|---|---|
| All parameter metadata of a release | `data/snapshots/<tag>.json` ([schema](schema/snapshot.schema.json)) | v1.12.0 to v1.17.0 with their patch releases, and v1.18.0-rc1 |
| Conversions PX4 performs on upgrade | `data/translations/` | not built yet |
| What happened to each removed parameter | `data/curated/` | not built yet |
| History per parameter, changes between releases | `data/params/`, `data/changes/` | not built yet |

The snapshots are made from the release tags by PX4's own generators. Each one
records the commit it came from and how it was made, and the tests compare
them with the parameter lists of official PX4 firmware builds. What a snapshot
includes and leaves out, and why, is in
[docs/DESIGN.md](docs/DESIGN.md#1-snapshots-generated). The parameter data is
PX4's, under its BSD-3-Clause license ([LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY)).

## The upgrade check page

[web/](web/) holds a single offline HTML page that checks a QGroundControl
`.params` file saved on PX4 v1.17.0 before it is loaded on v1.18.0-rc1, and
writes a corrected copy. It will move to the data above as it is built.

## Command line

```
pip install .
param-lineage --version
```

The commands that read the data (`history`, `diff`, `check`) come with it.

## Safety and liability

- This software and its data are provided "as is", without warranty of any
  kind. See [LICENSE](LICENSE).
- The project and its authors accept no liability and no responsibility for
  any use of the software, the data or their results. Whether and how you use
  them is entirely your own decision, at your own risk.
- It describes what changed. It does not approve a vehicle as safe or
  airworthy, and it does not say which values are right for a vehicle.
- Data that has not been checked is marked as such. A check that lists
  nothing does not mean the configuration is right.
- Review every value before you load it. It does not replace bench tests,
  motor tests without propellers, or careful step-by-step flight testing.
- You decide whether to fly, and you are responsible for the result. The
  authors accept no liability for damage, injury or loss of any kind.
- This project is not affiliated with or endorsed by the PX4 project or the
  Dronecode Foundation. PX4 is a trademark of Dronecode Project, Inc. It is
  used here only to name the software this project describes.

These terms are part of the program: the command prints them with
`--version`, and the page shows them under every check.

## Licenses

- The code and the curated data of this project: BSD 3-Clause, see
  [LICENSE](LICENSE).
- The parameter data (names, descriptions, defaults, ranges, enum values and
  conversions) comes from the PX4 Autopilot project
  (https://github.com/PX4/PX4-Autopilot), copyright PX4 Development Team,
  licensed under the BSD 3-Clause license in
  [LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
