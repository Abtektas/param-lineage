# param-lineage

Parameter history for PX4: a machine-readable record of how PX4 parameters
change between releases.

**Status: early development. There is no release yet. The data described
below is built, the removed parameters of the last two upgrades are curated,
and the commands and the upgrade check page work on it.**
The plan is in [docs/DESIGN.md](docs/DESIGN.md).

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
- the conversions PX4 performs on upgrade, found by running each release's
  own conversion code;
- for every parameter a release removed, what happened to it, with the commit
  as evidence;
- a history per parameter, and a list of changes between any two releases.

## Data

| What | Where | Status |
|---|---|---|
| All parameter metadata of a release | `data/snapshots/<tag>.json` ([schema](schema/snapshot.schema.json)) | v1.12.0 to v1.17.0 with their patch releases, and v1.18.0-rc1 |
| Conversions PX4 performs on upgrade | `data/translations/<tag>.json` ([schema](schema/translations.schema.json)) | the same releases |
| What happened to each removed parameter | `data/curated/<from>..<to>.json` ([schema](schema/curated.schema.json)) | v1.16.2 to v1.17.0, and v1.17.0 to v1.18.0-rc1 |
| Changes between consecutive releases | `data/changes/<from>..<to>.json` ([schema](schema/changes.schema.json)) | every pair of consecutive tracked releases |
| History of every parameter | `data/params.json` ([schema](schema/params.schema.json)) | every parameter of the tracked releases |

The snapshots are made from the release tags by PX4's own generators. Each one
records the commit it came from and how it was made, and the tests compare
them with the parameter lists of official PX4 firmware builds. What a snapshot
includes and leaves out, and why, is in
[docs/DESIGN.md](docs/DESIGN.md#1-snapshots-generated). The parameter data is
PX4's, under its BSD-3-Clause license ([LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY)).

The translations come from compiling each release's `param_translation.cpp`
unchanged and running it on probe values: every parameter of the tracked
releases, with its defaults, ranges, enum values and the numbers in the code.
Each file says what the code did with each value, what the import does next,
which parts of the code no probe reached, and what the data does not cover
([docs/DESIGN.md](docs/DESIGN.md#2-translations-generated)). PX4 runs this code
only when it upgrades the stored parameters of a vehicle in place.

The curated facts are written by hand: for every parameter a release removed,
whether PX4 converts it, renamed or replaced it, fixed the behaviour in code,
or dropped the feature, with the commit that removed it. The tests check each
entry against the snapshots, the translations and PX4's history
([docs/DESIGN.md](docs/DESIGN.md#3-curated-facts-human)).

## The upgrade check page

[web/](web/) holds a single offline HTML page that checks a QGroundControl
`.params` file saved on PX4 v1.17.0 before it is loaded on v1.18.0-rc1, and
writes a corrected copy. It is built from the data above: the snapshots of
both releases, the curated facts and the changes between them. Its tests check
every conversion it writes against the translations of v1.18.0-rc1.

## Command line

```
pip install .
param-lineage --version
param-lineage history MPC_HOLD_DZ
param-lineage diff v1.16.2 v1.18.0-rc1
param-lineage check saved.params --from v1.17.0 --to v1.18.0-rc1
```

`history` shows how one parameter changed across the tracked releases, and
`diff` what changed between two of them, following renames through the
releases in between. `check` reads a parameter file that QGroundControl saved
on one release and lists what to look at before loading it on a newer one:
removed parameters with what happened to them, type changes, ranges the newer
release narrowed, and values that keep a default the newer release changed. It does not write a corrected file
(the page does). Each command takes `--json`, and the package carries the
data, so nothing else is needed.

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
  [LICENSE-THIRD-PARTY](LICENSE-THIRD-PARTY). So do three lines of
  `src/paramlineage/harness/platform.h`, marked there.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
