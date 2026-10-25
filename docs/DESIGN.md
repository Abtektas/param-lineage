# param-lineage: design

Status: draft 8, 2026-10-25. M0 (skeleton), M1 (snapshots of all tracked
releases), M2 (translations), M3 (changes and curation of the last two
upgrades), M4 (histories and the `history`, `diff` and `check` commands), M5
(the upgrade check page built from this data) and M6 (the last two upgrades
run in SITL) are done; M7 (release v0.1) waits for PX4 v1.18.0 final.
Name: **param-lineage**, "parameter history for PX4". The name must not
contain "PX4" (see [Trademarks](#trademarks)).

## Goal

A machine-readable, verifiable history of PX4 parameters across releases:

- when each parameter was added, renamed and removed;
- how its type, default, range, units, enum values and bitmask bits changed;
- whether PX4 itself migrates a stored value when a vehicle is upgraded
  (`param_translation.cpp`), and what happens to it otherwise.

Today this knowledge exists only as hand-written prose: PX4 release notes,
the "changes since" lists the docs team builds by hand, Auterion's APX4
release notes and ArduPilot's parameter-rename wiki page. None of it is
machine-readable.

## Who it is for

| Audience | What they need | What they get |
|---|---|---|
| Operators and integrators upgrading a fleet | "What happens to my parameters from vX to vY?" | `check` on a `.params` file; a static web page |
| PX4 maintainers and the docs team | Complete change lists per release; no rename without migration | Release-notes draft; a CI check they can run |
| Tool builders (ground stations, fleet software, forks) | Old-name → new-name data they can load | Versioned JSON with a schema |
| Researchers using public flight logs | Comparing parameters of logs from different releases | Per-parameter history and rename links |

## Where it lives

A standalone repository, not part of PX4:

- PX4's tree only describes its own version; this history spans many tags
  and has to live outside any one of them.
- Data files would add size and review load to PX4 for little gain.
- BSD-3-Clause and PX4's conventions keep the door open: if Dronecode or the
  PX4 maintainers want it under their organization later, it can move as is.

Integration happens at the consumers, each as a separate step:

- the upgrade check page in `web/` (formerly the local px4-param-upgrade)
  moves to this data;
- PX4: a small CI check or release-notes helper, proposed upstream only after
  v0.1 has shown real findings;
- other tools load the JSON.

## Non-goals

- **uORB messages.** PX4 already versions messages and translates them for
  ROS 2 (`msg/translation_node`).
- **MAVLink.** Covered by
  [hamishwillee/mavlink-compat-data](https://github.com/hamishwillee/mavlink-compat-data).
- **Per-board availability** in v0. A snapshot lists every parameter defined
  in the source tree at a tag. Whether a parameter exists on a given board
  depends on its Kconfig; that is a later layer.
- **Advice.** The data says what changed. It does not say which value is
  right for a vehicle, and it is not a safety assessment.

## Principles

1. **Generated and curated facts are kept apart.** Generated facts are rebuilt
   from a git tag with PX4's own generators and are never edited by hand.
   Curated facts are what metadata cannot express (that B replaces A, that a
   value is now fixed in code). Each curated fact names its evidence.
2. **Every fact is traceable.** Tag and commit SHA for generated facts. Commit,
   PR and basis for curated facts. (PX4's generators do not report which file
   defines a parameter; `git grep` at the recorded commit finds it.)
3. **Deterministic output.** Sorted keys, stable formatting. Rebuilding from
   the same inputs gives byte-identical files, and CI checks that.
4. **The data is the product.** The JSON files and their schemas are the
   interface. The library, the CLI and the page are consumers of it.
5. **Nothing is silently lost.** A transition marked as curated fails the
   build if a parameter disappears and nothing explains where it went.
6. **Honest coverage.** What has not been checked yet is labelled as such,
   never presented as complete.

## Layers

```
PX4 git tags
   │  extract (PX4's own generators, per tag)
   ▼
1. snapshots/      generated   all parameter metadata at one tag
2. translations/   generated   what that tag's param_translation.cpp does, found by running it
3. curated/        written     what happened to each removed parameter, with evidence
   sitl/           measured    in-place upgrades run in PX4 SITL (optional, see Behaviour verification)
   │  build (deterministic)
   ▼
4. params.json     derived     history of every parameter across all tags
   changes/        derived     everything that changed between two tags
```

### 1. Snapshots (generated)

`data/snapshots/<tag>.json`: the normalized parameter metadata of one tag. The
format is described by `schema/snapshot.schema.json`; `parameters` maps each
name to the fields of PX4's own `parameters.json`.

- **Generators.** PX4's own scripts make the data, run from the tag's source
  the way PX4's `metadata_parameters` build target runs them
  (`cmake/metadata.cmake`): `Tools/serial/generate_config.py`,
  `Tools/module_config/generate_params.py` (from v1.13) and
  `src/lib/parameters/px_process_params.py`. They are not copied into this
  repository. The steps that ran are recorded in each file.
- **Source.** `git archive <tag>` of `LICENSE`, `src`, `Tools` and the two
  board directories the generators read. No build, no submodules. Checked on
  2026-10-23: for v1.17.0, a full checkout with every submodule under `src`
  gives a byte-identical snapshot (the opt-in `FullTree` test).
- **What is read.** Every module config under `src/` and every source
  directory PX4's target scans (`find src -maxdepth 4 -type d`). PX4's own
  target takes module configs only from `src/modules`, `src/drivers` and
  `src/lib`, and leaves out the directories `pwm_out_sim`, `linux_pwm_out` and,
  from v1.16, `src/modules/spacecraft`. That has two effects this project
  avoids:
  - from v1.13, PX4's list lacks `HIL_ACT_FUNC1` to `16` and `HIL_ACT_REV`,
    which only `pwm_out_sim/module_hil.yaml` defines;
  - in v1.18, 64 parameters of the spacecraft build and of
    `src/systemcmds/tests` (`SC_`, `SPC_`, `TEST_`) moved from `.c` files to
    YAML files that target does not read, so they drop out of PX4's v1.18 list
    although they are in its v1.17 list. Reading everything keeps them
    continuous.
- **What is left out**, each for a stated reason:
  - Three module configs that define the same parameters as another module
    (the simulator's and Linux boards' output drivers, and v1.16's spacecraft
    copy of the control allocation config). PX4's target leaves them out too.
    Each is still generated on its own, and the names only it has are listed
    in the snapshot (`excluded_configs[].not_in_snapshot`): `PWM_MAIN_FUNC9` to
    `16` of the simulator, and the 85 `CA_THRUSTER` parameters of v1.16's
    spacecraft build. Nothing is dropped silently.
  - Up to v1.16, `src/lib/parameters/parameters_injected.xml` adds 21
    parameters of UAVCAN nodes, ESCs and GNSS receivers (`ctl_bw`,
    `esc_index`, `gnss.dyn_model`, ...). They are set on the node and PX4 does
    not store them; PX4 removed the file for that reason in 7b68c5dbfc
    (PX4 #25549). The generator gets an empty list instead.
- **Checked against PX4's own target.** On 2026-10-23, PX4's
  `metadata_parameters` steps were run for every tracked tag by a separate
  script, with the tag's own filters and inject file. Every parameter both
  lists have was identical in every field, and the names only one list had
  were exactly the ones described above: the 21 injected names, the 17
  `HIL_ACT` names, and the 64 v1.18 names.
- **Board-dependent parameters** follow PX4's target: fmu-v5 timers with an IO
  board, Ethernet, all serial ports. A board with more outputs has more
  instances (for example `PWM_MAIN_FUNC9`), and the default port of a serial
  port parameter (`RC_PORT_CONFIG`) can differ. Per-board data is a later
  layer.
- **Checked against PX4's builds.** For one release of each minor version,
  the parameter lists of the official fmu-v5 and fmu-v6x firmware were
  compared with the snapshot (`tests/fixtures/firmware`, `test_snapshots.py`):
  every parameter of the build is in the snapshot with the same type and
  default, except the UAVCAN node names above and the serial port defaults.
  The lists come from the `.px4` files of PX4's GitHub releases, which record
  the commit they were built from; v1.12.3 stands for v1.12 because the
  v1.12.0 release's files are v1.11.2 builds; v1.14.0 has no release files and
  its lists come from PX4's firmware bucket, without a recorded commit.
- **Data as PX4 generates it.** Nothing is corrected by hand. Known quirk:
  from v1.16, `VTQ_IO_REV` has a bitmask bit at index -1, because the generator
  assumes channels start at 1.
- **Provenance** in every file: tag, commit, extractor version, steps, board
  options, left-out configs, and the Python, PyYAML and Jinja2 versions. Each
  file also records the copyright line of the tag's `LICENSE` and the license
  check below.
- **Reproducible.** `python -m paramlineage.extract --check --all` extracts
  every tracked tag again and compares it byte by byte. Only different tool
  versions are tolerated, and reported. CI does this when the extractor or the
  data change, and weekly, so a moved tag is noticed.

### 2. Translations (generated)

`data/translations/<tag>.json`: what the firmware of that tag does to each
stored parameter value when it imports the stored parameters of a vehicle,
as decided by `param_modify_on_import()` in
`src/lib/parameters/param_translation.cpp` and the import code that calls it.
The format is described by `schema/translations.schema.json`.

PX4 applies this only when the stored parameters of a vehicle are upgraded in
place. Loading a `.params` file by name does not run it (verified in SITL on
2026-10-20, and by the `by-name` runs in `data/sitl`). The data says this
explicitly.

**Run, not parse.** `param_translation.cpp` is free-form C++, not a list of
rules. Across the tracked tags it uses loops over arrays of names, helper
functions, `strcat`, name families matched by prefix (`RC*_REV`, `HEATER*`),
conditions on the value, `param_set` on other parameters, `#ifdef
__PX4_NUTTX`, and two return types (a `bool` up to v1.14, an enum from
v1.15). A parser would miss rules without noticing. So the extractor
(`python -m paramlineage.translations`) compiles the tag's file and runs it:

- **Harness.** `src/paramlineage/harness/harness.cpp` includes the tag's
  `param_translation.cpp` unchanged, after the headers that file includes
  (`param.h`, `tinybson.h`, `drv_sensor.h`, `Device.hpp`, `mathlib`), all
  from `git archive <tag>`. PX4's platform headers (logging, `PX4_OK`) are
  replaced by `harness/platform.h`. Macros in front of `strcmp`, `strncmp`,
  `strstr`, `strcpy`, `strncpy`, `strcat`, `snprintf`, the logging macros and
  the parameter API (`param_find`, `param_set`, `param_set_no_notification`,
  `param_get`) record the source line of every call. The parameter API
  behaves as PX4's `parameters.cpp`. C++17, `-O0`, `-ffp-contract=off`.
- **The firmware's parameters.** `param_find` knows exactly the parameters in
  the tag's snapshot, numbered by name as PX4 numbers them, so code such as
  "enable `LPE_EN` only if it exists" behaves as in a build with every
  module. `param_get` returns the snapshot default. Every probe starts from
  the defaults.
- **Probes.** Names: every parameter in a tracked snapshot up to and
  including the tag, plus every name the file compares against (some date
  from before v1.12). Types: from the snapshots; names found only in the file
  are probed as both. Values: 0, 1, -1, the numbers in the file and their
  negatives (such as 162128), and from each snapshot the default, min, max,
  enum values and bitmask bits. Floats are rounded to float32, as PX4 stores
  them.
- **Platforms.** Built with and without `__PX4_NUTTX` (defined for the
  translation code only); cases that differ are recorded for both (the SPI
  device ID rule in v1.12).
- **What a result depends on.** Each probe also runs with the parameters
  numbered in reverse, and with the bytes of the node that the BSON decoder
  does not write filled in. A result that changes is marked `depends_on`, and
  its values are not what a firmware gives: v1.14 computes `VT_PSHER_SLEW`
  from the handle `param_find()` returns instead of a value, and from v1.13
  the decoder writes only the low four bytes of an int32 node, so code that
  reads it as a double reads what the value before left there.
- **Import.** The result is then passed through the tag's import rules
  (`param_import_callback()` in `parameters.cpp` and `flashparams.cpp`, read
  for every tracked tag):
  - up to v1.14 the return value is ignored; from v1.15
    `PARAM_SKIP_IMPORT` stops the import of that value;
  - the name after translation is looked up in the tag's snapshot: an
    unknown name or a different type is ignored, otherwise the value is
    stored.

  The extractor recognises these import functions by a hash of their text
  and stops on a tag whose import code differs, so a change is read before
  it counts.

  Each case ends in one outcome: `stored` (name and value), `skipped`,
  `ignored-unknown-name` or `ignored-type`, plus the other parameters it set
  (`also_set`).

Each file lists only the stored names the code touched (compared in full,
changed the node, called the parameter API, or returned something other than
"not modified"), with every probe of those names. Probes with the same result
are grouped. Where a value is the stored value itself for two or more stored
values, it is written `"stored"`; a constant that equals a single stored value
keeps its number. Probes of other names are counted, not listed.

**Coverage is reported, not assumed.** Every recorded call in the file is
listed with the platforms on which a probe reached it (a comparison counts
when it matched), and every name literal with whether a probe used it and
whether a tracked parameter has it. Some rules need specific values (the
device IDs of v1.12) or names that no tracked release has (`HEATER*_IMU_ID`,
which existed only on main, after v1.17 had branched off and before v1.18);
the coverage shows them
as not reached, and tests run them with constructed values.

**Limits, stated in the data:**

- A board built without a module behaves differently where the code checks
  whether a parameter exists.
- `param_get` during import returns values imported earlier from the same
  storage, and a value set by a translation can be overwritten by a stored
  value imported later; each probe here is imported on its own.
- What happens after import (for example `CAL_ACC0_PRIO=-1` being replaced by
  a default later) is outside this layer.

All three were checked on one board in SITL; see Behaviour verification.

**Reproducible.** The 23 tracked tags have 7 different versions of the file.
Each tag is still extracted on its own, and `--check` compares the output
byte by byte like the snapshots; only a different compiler is tolerated, and
reported. Checked on 2026-10-23: Apple clang 21 on macOS (arm64), and GCC 13.3
on Linux arm64 and on Linux x86_64 (QEMU emulation), give the same data for
every tag; on 2026-10-25 also GCC 13.3 on Linux x86_64 without emulation.

### 3. Curated facts (written)

`data/curated/<from>..<to>.json`: one entry for every parameter that exists in
`<from>` and not in `<to>`. The format is described by
`schema/curated.schema.json`.

| kind | meaning |
|---|---|
| `migrated` | PX4 converts the value on in-place upgrade (must match a translation rule). |
| `renamed` | A successor exists, but PX4 does not convert the value. |
| `replaced` | Newer parameters do the job in a different way; no one-to-one mapping. |
| `fixed` | The behaviour is now fixed in code; `fixed_value` when it matches an old setting. |
| `removed` | The feature or setting is gone. |

- Each entry has `commit` (required, the full hash), `pr` (when known),
  `successors` (required for `migrated`, `renamed`, `replaced`),
  `fixed_value` (for `fixed`, when it equals an old setting), `note` and
  `basis`: `code-inspection`, `release-notes` or `sitl-tested`.
- Checked by the tests: every entry is a parameter of `<from>` that `<to>`
  does not have, its successors are parameters of `<to>`, its commit lies
  between the two tags (with a PX4 repository), and it is `migrated` exactly
  when the translations of `<to>` pass the value on, to its successors only.
- Curated files hold facts only. How a tool helps a user act on them (for
  example suggesting a value for a `renamed` successor) belongs to the tool;
  what PX4 converts comes from the translations.
- A family that changed together, such as the mixer-to-control-allocation
  move in v1.14, can be curated as one group rule with a name pattern. The
  build expands it, and the built files list every matched name.
- Each transition has a status: `complete`, `partial` or `not-started`.
  Only `complete` transitions are enforced by the completeness check, and
  consumers see the status next to the data.
- The upgrade check page in `web/` shows the curated entries of its pair as
  they are. Its own rules (`web/tools/hints_<from>_to_<to>.py`) say how it
  converts a `migrated` value and what it suggests for the others; its build
  stops unless every `migrated` entry, and only those, has a conversion rule
  that writes exactly the entry's successors, and its tests check each
  conversion against every probe value of the translations.

### 4. Built views (derived)

- `data/params.json` (`python -m paramlineage.history --all`; format in
  `schema/params.schema.json`): the history of every parameter. For each, a
  list of states, each valid over a range of tags, made of the fields the
  changes compare, so a new state starts exactly where the changes report
  one. Each removal carries its curated kind and successors (`removed`), and
  a successor lists the parameters it took over from (`predecessors`). One
  file, not one per parameter, so that no file of this project is named
  after a parameter: some PX4 parameter names contain "PX4"
  (`SENS_EN_PX4FLOW`).
- `data/changes/<from>..<to>.json`, one per pair of consecutive tracked tags
  (`python -m paramlineage.changes --all`; format in
  `schema/changes.schema.json`): added, removed (with the curated kind and
  successors, and the curated status of the pair), and changes to type,
  default, min, max, units, enum values, bitmask bits and reboot-required.
  Descriptions, group, category, decimal places, increment and volatile are
  not compared. A change between releases further apart is built from the
  snapshots when asked for.
- The views show PX4's metadata as its generators write it. For example
  v1.18.0-rc1 defines `RC*_REV` as `int32` with values, but the generator
  writes values only for enum and float parameters, so the change reads
  "values removed".

Floats are compared as IEEE-754 float32, the way PX4 stores them, so a
default written as `0.1` in one release and `0.100000001` in another is not
reported as a change.

## Integrity checks (CI)

1. **Schema:** every data file validates against its JSON Schema.
2. **Reproducible:** re-extracting a tag gives a byte-identical snapshot and
   translations file, and the changes files match a fresh build.
3. **Complete:** in a `complete` transition, every removed parameter has
   exactly one curated entry.
4. **Consistent:**
   - an entry is `migrated` exactly when the translations of the newer tag
     pass the value on, and then only to its successors;
   - a translation whose target the tag does not have shows in the
     translations as `ignored-unknown-name` (v1.13's `VT_PITCH_MIN`);
   - a `renamed` entry is where users lose values: a successor exists but
     PX4 does not convert it. The changes carry the kind, so tools can warn.
     The heater and `EKF2_AGP` parameters of v1.18.0-rc1 are such entries.
5. **History:** every commit a curated entry cites lies between its two tags
   (`.github/workflows/curated.yml`, with PX4's commits only).
6. **SITL:** the results in `data/sitl` follow from their runs and agree with
   the translations, and `basis: sitl-tested` is on exactly the entries they
   back (see Behaviour verification).

## Behaviour verification (SITL)

`data/sitl/<from>..<to>.json`: in-place upgrades run in PX4 SITL with
`python -m paramlineage.sitl`, from two `px4_sitl_default` builds with the SIH
quadrotor (airframe 10040) and no simulator GUI. The format is described by
`schema/sitl.schema.json`.

Each run stores values in the older release, starts the newer one on the same
parameter storage, as a firmware upgrade in place does, and reads what it has
once it has started:

- `control-1`, `control-2`: nothing stored, for what the upgrade does on its
  own and which values change from run to run.
- `converted-<n>`: every `migrated` entry and every parameter whose type
  changed, with a value from probe case `<n>` of the newer release's
  translations, so that every branch of a rule runs where the older release
  accepts such a value.
- `removed`: every other removed parameter, with a value that is not its
  default.
- `order-target-later`, `order-target-earlier`: the storage also holds the
  parameters a value is converted to, after or before the converted one.
- `by-name`: nothing stored; the old names are then set by name in the newer
  release, one at a time, as loading a parameter file does.

Every stored value is compared with what the translations say it becomes:
`pass`, `fail`, `not-in-build` (the build does not have the parameter), or
`observed` where the import order decides and the translations do not say.
The tests recompute the comparison from the runs, and require no `fail`, no
change that neither a stored value nor the older release explains, and
`basis: sitl-tested` on exactly the `migrated` entries whose every successor
passed. The runs need two PX4 builds, so CI does not repeat them; a file
records one run.

Results of 2026-10-25 (GCC 13.3, Linux x86_64):

- v1.17.0 → v1.18.0-rc1: 16 runs, 89 checks, 88 pass and 1 observed. The
  conversions of `COM_RC_OVERRIDE`, `EKF2_GPS_DELAY`, `EKF2_GPS_POS_X/Y/Z`,
  `MNT_RANGE_PITCH` and `MPC_LAND_RC_HELP`, and `RC*_REV` from float to int32,
  all as the translations say. `MOT_POLE_COUNT` was not run: this build has
  neither it (v1.17.0) nor `DSHOT_MOT_POL1` to `12` (v1.18.0-rc1). Of the
  other removed parameters, 38 were stored and none was passed on; 14 are not
  in this build.
- v1.16.2 → v1.17.0: 7 runs, 9 checks, all pass: `ASPD_FALLBACK_GW` is copied
  to `ASPD_FALLBACK`, and the 58 other removed parameters are dropped, their
  successors unchanged.
- Setting an old name by name in the newer release is refused, so nothing is
  converted.

The limits of the translations (section 2), as seen in these runs:

- **Board:** a parameter the build does not have is neither stored nor
  converted to; on this board that is the DShot, heater, battery ADC, INA226
  and UAVCAN light parameters.
- **Import order:** a target stored after the converted parameter overwrites
  the conversion; stored before, the conversion overwrites it. `param_get`
  reads the value imported before it: with `MPC_AUTO_NUDGING=1` before
  `MPC_LAND_RC_HELP=1`, v1.18.0-rc1 gives 3, where the translations, which
  read the default, give 2. The storage files PX4 saved list parameters in
  name order. An upgrade in place from v1.17.0 cannot have
  `MPC_AUTO_NUDGING` stored, because v1.17.0 does not have it, so this matters
  only for a storage that already holds newer names.
- **After import:** every converted value was still there after the newer
  release had started. The one other change, `EKF2_DELAY_MAX` raised to 300
  with `EKF2_GPS_DELAY=300`, was made and saved by v1.17.0's EKF2 before the
  upgrade.

## Tracked versions

Chosen from what people fly. Public Flight Review logs uploaded between
2026-04-22 and 2026-10-22 (102,579 logs), by release:

| Release | Share of logs | Vehicles |
|---|---|---|
| v1.16 | 25.4% | 2,773 |
| v1.17 | 22.5% | 2,143 |
| v1.15 | 19.1% | 2,059 |
| v1.14 | 12.8% | 1,994 |
| v1.13 | 5.6% | 724 |
| v1.12 | 3.2% | 553 |
| v1.18 (RC) | 2.7% | 266 |
| v1.11 | 1.4% | 179 |

Public uploads lean towards hobby and development use. Companies rarely
upload, so this is a lower bound on how old the releases in use are.

Decision:

- **Snapshots:** every stable tag from v1.12.0 on, patch releases included
  (v1.12.0 … v1.17.0), plus the newest release candidate until its final
  release. Together they cover over 90% of these logs. Extraction is cheap,
  and patch releases rarely remove parameters, so they add little curation.
- **Curation order:** newest first (v1.17 → v1.18, v1.16 → v1.17, …),
  because that is where people are upgrading now. v1.13 → v1.14 (mixer files
  to control allocation) is the largest transition and comes last.
- **Not tracked:** `main` (changes daily, not reproducible from a tag; a dated
  snapshot may be added later, marked as such) and releases before v1.12.

## Code

- Python ≥ 3.11 (the same floor as actuator-lint). The library uses only the
  standard library, so consumers install nothing else.
- Tests use `unittest` from the standard library; the page's tests use
  Node's built-in `node:test`.
- JSON Schemas are checked in CI with `jsonschema`, pinned with hashes in
  `requirements/schema.txt`. The standard tool is easier to trust than a
  checker of our own; the tests also repeat the main rules with the standard
  library, so a plain `unittest` run checks them too.
- Extraction runs PX4's generators. They need PyYAML, Jinja2 and MarkupSafe,
  pinned with hashes in `requirements/extract.txt`; the versions used are
  recorded in each snapshot.
- Translations compile PX4's translation code with the host C++17 compiler
  (Apple clang locally, GCC on the CI runner). The harness and the stand-in
  header are ours (apart from three lines, see Licenses), under
  `src/paramlineage/harness/`; they are installed with
  the package but only used for extraction. PX4's platform header names that
  the code includes are written at build time, each including the stand-in.
  The compiler's first `--version` line is recorded in each translations
  file.
- Pinned versions were published at least two weeks before they were pinned.

```
param-lineage/
  data/              snapshots/ translations/ curated/ changes/ params.json
  schema/            one JSON Schema per data kind
  requirements/      pinned packages for extraction and the schema tests
  src/paramlineage/  legal, cli, extract, translations, harness/, curated, changes, history, query, check
  web/               the upgrade check page
  tests/             unit tests, known history, firmware parameter lists
  docs/              DESIGN.md; later how to add a release
```

## Licensing

- **This project's code and curated data:** BSD-3-Clause, the license PX4
  uses, so either side can reuse the other's work.
- **Generated data:** it contains PX4's parameter descriptions, defaults and
  enum names. PX4 is BSD-3-Clause ("Copyright (c) 2012 - 2025, PX4
  Development Team"; the license text is the same in every tag from v1.12.0
  to v1.18.0-rc1). BSD-3 requires keeping that notice with redistributed
  source, so `LICENSE-THIRD-PARTY` carries it and the data files point to it.
- Checked for every tracked tag, by the extractor: the tag's `LICENSE` is the
  BSD-3-Clause text in `LICENSE-THIRD-PARTY` (only the copyright years differ,
  2021 to 2025, and each snapshot records its line), and every file the data
  can come from (configs with parameter sections, source files with
  parameter definitions, the generator scripts and templates) carries a
  BSD-3-Clause notice or none. A file with any other notice stops the
  extraction. Files without a notice fall under the repository's license.
  Submodules, which do carry other licenses, are not part of the extraction.
- **Translations:** the harness compiles PX4 source files on the machine
  that extracts and keeps no compiled code. The data holds what the code did
  (names, values, line numbers), not the code. The files compiled
  (`param_translation.cpp` and the headers it includes) go through the same
  per-tag license check. The stand-in header repeats three lines of PX4's
  `defines.h` (`PX4_ISFINITE` for float and double, `M_PI_PRECISE`), because
  the compiled code uses them by these names; they are marked as PX4's in the
  file and fall under `LICENSE-THIRD-PARTY`.
- **Dependencies:** none at runtime. PyYAML (MIT), Jinja2 and MarkupSafe
  (BSD-3) run PX4's generators during extraction; jsonschema and its
  dependencies (MIT, and PSF for typing-extensions) check the schemas in CI;
  the page's optional jsdom check uses jsdom (MIT). None is copied into the
  repository.
- The firmware parameter lists in `tests/fixtures/firmware` are PX4 data
  (names, types, defaults) and say so in their header.
- **Flight Review data:** only aggregate counts are used, as in the table
  above. No log, vehicle ID or description is stored or published.

## Trademarks

- Dronecode holds the PX4 trademarks (PX4 README). Dronecode's guidelines
  (dronecode.org/trademarks, 2017-04-24) say a mark should not be part of a
  product name or domain name, ask for a trademark notice even in fair use,
  and forbid implying endorsement.
- Strict rule: nothing in this project is named with "PX4": not the
  repository, package, module, command, a file name, a release asset, a
  heading, a page title, a domain or a logo. PX4's license text is in
  `LICENSE-THIRD-PARTY` for the same reason. "PX4" appears only in sentences
  that refer to PX4 itself ("parameter history for PX4"). Tests check file
  names, headings and titles.
- README, CLI output and page footer carry the notice, worded as in
  actuator-lint: "This project is not affiliated with or endorsed by the PX4
  project or the Dronecode Foundation. PX4 is a trademark of Dronecode
  Project, Inc. It is used here only to name the software this project
  describes." (The page ends with "this tool works with".)
- The same applies to "ArduPilot" if it is ever added.

## Terms of use

- Provided as-is, for information. It is not a safety assessment and does
  not tell anyone which values are safe to fly.
- Users decide whether to fly and are responsible for the result; the
  authors accept no liability for damage, injury or loss of any kind (as in
  actuator-lint).
- The code, data and documentation were mostly written by an AI assistant,
  and a person has not reviewed all of them. The terms say so, and that the
  authors accept no liability for their errors.
- These terms appear in the README, in CLI output and on the page, and they
  are never weakened (same rule as actuator-lint).

## Reputation safeguards

| Risk | Safeguard |
|---|---|
| Wrong data misleads a user | Provenance on every fact; `basis` on curated facts; transition status; tests on known history; the conversions run in SITL |
| Looks official | No PX4 in the name; trademark and non-affiliation notice |
| License breach | PX4 notice kept with derived data; nothing copied from submodules or other projects |
| AI-generated noise | AI help disclosed (`Assisted-by` trailer in commits); every fact checkable; announced once, with findings, not as an idea |
| Burden on maintainers | No upstream PR until v0.1 shows real findings; one PR at a time, within PX4's open-PR limit |
| Personal data | Flight Review used only for aggregate counts |

## Milestones

| | Milestone | Done when |
|---|---|---|
| M0 | Design and skeleton | This document is agreed; repo skeleton, licenses, notices, CI config exist. |
| M1 | Snapshots | All tracked tags extract; v1.17.0 archive equals worktree; reproducibility test passes. |
| M2 | Translations | The harness runs the translation code of every tracked tag; every call site and name literal is reported as reached or not; known cases tested (GNSS, heater, `COM_RC_OVERRIDE`, `CBRK_AIRSPD_CHK`, `MOT_POLE_COUNT`, v1.12 device IDs). |
| M3 | Changes + curation | Diff engine; completeness check; curated v1.17 → v1.18 and v1.16 → v1.17. |
| M4 | Histories + CLI | `params.json` built; `history`, `diff`, `check <file.params>` commands. |
| M5 | Upgrade checker | The page in `web/` reads this data. |
| M6 | SITL verification | Translation rules tested by in-place upgrade. |
| M7 | Release v0.1 | Announced with PX4 v1.18.0 final. |

## Open questions

1. Per-board availability: from each board's Kconfig, or from the
   `parameters.json.xz` that release builds embed? This also covers instance
   counts that depend on the board (`PWM_MAIN_FUNC9` and up) and the default
   ports of serial port parameters.
