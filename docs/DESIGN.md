# param-lineage: design

Status: draft 3, 2026-10-23. M0 (skeleton) is in place; the data is not built yet.
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
2. **Every fact is traceable.** Tag, commit SHA and source file for generated
   facts. Commit, PR and basis for curated facts.
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
2. translations/   generated   rules parsed from that tag's param_translation.cpp
3. curated/        human       what happened to each removed parameter, with evidence
   │  build (deterministic)
   ▼
4. params/         derived     history of one parameter across all tags
   changes/        derived     everything that changed between two tags
```

### 1. Snapshots (generated)

`data/snapshots/<tag>.json`: the normalized parameter metadata of one tag.

- Produced by PX4's own generators from that tag's source:
  `Tools/serial/generate_config.py`, `Tools/module_config/generate_params.py`
  and `src/lib/parameters/px_process_params.py`. Every module config under
  `src/` is read, including the ones the `metadata_parameters` target skips
  (`src/modules/spacecraft`, `src/systemcmds`).
- The source comes from `git archive <tag>`: no build, no submodules.
  Checked on 2026-10-23: for v1.17.0 the archive gives exactly the same
  2784 parameters, field by field, as a full worktree.
- The generators' command lines differ between releases (v1.12 has no
  `Tools/module_config`; v1.13 to v1.16 each failed differently with the
  v1.17 command line). The extractor keeps one small recipe per generator
  interface. The recipe is chosen by the interface, not by the version
  number, so a new release that keeps the interface needs no change.
- PX4's generator scripts are run from the archived tag. They are not copied
  into this repository.
- Provenance is stored in the file: tag, commit SHA, extractor version,
  recipe, and the Python, PyYAML and Jinja2 versions used.

### 2. Translations (generated)

`data/translations/<tag>.json`: the rules in that tag's
`src/lib/parameters/param_translation.cpp`, parsed into data.

- Kinds: `rename` (A becomes B, value copied) and `conversion` (A becomes B
  with a value rule, such as `COM_RC_OVERRIDE=0` → `MAN_OVERRIDE_SPD=-1`).
- Each rule keeps its source line, so a reviewer can check it against the code.
- A rule the parser cannot classify is recorded as `unparsed` with its source
  text. It is never dropped.
- PX4 applies these rules only when the stored parameters of a vehicle are
  upgraded in place. Loading a `.params` file by name does not run them
  (verified in SITL on 2026-10-20). The data says this explicitly.

### 3. Curated facts (human)

`data/curated/<from>..<to>.json`: one entry for every parameter that exists in
`<from>` and not in `<to>`.

| kind | meaning |
|---|---|
| `migrated` | PX4 converts the value on in-place upgrade (must match a translation rule). |
| `renamed` | A successor exists, but PX4 does not convert the value. |
| `replaced` | Newer parameters do the job in a different way; no one-to-one mapping. |
| `fixed` | The behaviour is now fixed in code; `fixed_value` when it matches an old setting. |
| `removed` | The feature or setting is gone. |

- Each entry has `commit` (required), `pr` (when known), `successors` (for
  `migrated`, `renamed`, `replaced`), `note` and `basis`: `code-inspection`,
  `release-notes` or `sitl-tested`.
- A family that changed together, such as the mixer-to-control-allocation
  move in v1.14, can be curated as one group rule with a name pattern. The
  build expands it, and the built files list every matched name.
- Each transition has a status: `complete`, `partial` or `not-started`.
  Only `complete` transitions are enforced by the completeness check, and
  consumers see the status next to the data.
- The v1.17.0 → v1.18.0-rc1 notes in `web/tools/notes_v1_17_to_v1_18.py`
  (60 removals, each checked against its commit) become the first curated file.

### 4. Built views (derived)

- `data/params/<NAME>.json`: the history of one parameter. A list of states,
  each valid over a range of tags, plus `renamed_from` / `renamed_to` links.
- `data/changes/<from>..<to>.json`: added, removed (with curated kind),
  renamed, and changes to type, default, min, max, units, enum values, bitmask
  bits and reboot-required.

Floats are compared as IEEE-754 float32, the way PX4 stores them, so a
default written as `0.1` in one release and `0.100000001` in another is not
reported as a change.

## Integrity checks (CI)

1. **Schema:** every data file validates against its JSON Schema.
2. **Reproducible:** re-extracting a tag gives a byte-identical snapshot.
3. **Complete:** in a `complete` transition, every removed parameter has
   exactly one curated entry.
4. **Consistent:**
   - a `migrated` entry must match a translation rule in the newer tag;
   - every translation target must exist in that tag's snapshot;
   - a `renamed` entry with no translation rule is reported, because that is
     where users lose values.

   Check 4 would have caught the heater (#29354) and EKF2_AGP (#29351) gaps
   before release.

## Behaviour verification (later milestone)

Optional checks that run PX4 SITL:

- For each translation rule: store the old parameter in the older release,
  upgrade in place to the newer one, and read the new parameter back.
- An entry that passes gets `basis: sitl-tested`.

The manual version of this was done for v1.17.0 → v1.18.0-rc1 on 2026-10-20.

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
  Node's built-in `node:test`. How the JSON Schemas are checked in CI
  (a pinned `jsonschema`, or a small checker of our own) is decided in M1.
- Extraction runs PX4's generators. They need PyYAML and Jinja2; the versions
  used are recorded in each snapshot's provenance.

```
param-lineage/
  data/              snapshots/ translations/ curated/ params/ changes/
  schema/            one JSON Schema per data kind
  src/paramlineage/  legal, cli; later extract, translations, curate, build, check
  web/               the upgrade check page
  tests/             unit tests + known-history fixtures
  docs/              DESIGN.md; later how to add a release
```

## Licensing

- **This project's code and curated data:** BSD-3-Clause, the license PX4
  uses, so either side can reuse the other's work.
- **Generated data:** it contains PX4's parameter descriptions, defaults and
  enum names. PX4 is BSD-3-Clause ("Copyright (c) 2012 - 2025, PX4
  Development Team"; the license text is the same in every tag from v1.14.0
  to v1.18.0-rc1). BSD-3 requires keeping that notice with redistributed
  source, so `LICENSE-THIRD-PARTY` carries it and the data files point to it.
- Checked on 2026-10-23: no parameter-defining source file in v1.14.0 or
  v1.18.0-rc1 carries a different license. Seven files in v1.14.0 have no
  header at all and fall under the repository's BSD-3 license. Submodules
  (which do carry other licenses) are not part of the extraction.
- **Dependencies:** none at runtime. PyYAML (MIT) and Jinja2 (BSD-3) run
  PX4's generators during extraction; the page's optional jsdom check uses
  jsdom (MIT). None is copied into the repository.
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
- README, CLI output, page footer and package metadata carry the notice
  actuator-lint uses: "This project is not affiliated with or endorsed by the
  PX4 project or the Dronecode Foundation. PX4 is a trademark of Dronecode
  Project, Inc. It is used here only to name the software this tool works
  with."
- The same applies to "ArduPilot" if it is ever added.

## Terms of use

- Provided as-is, for information. It is not a safety assessment and does
  not tell anyone which values are safe to fly.
- Users decide whether to fly and are responsible for the result; the
  authors accept no liability for damage, injury or loss of any kind (as in
  actuator-lint).
- These terms appear in the README, in CLI output and on the page, and they
  are never weakened (same rule as actuator-lint).

## Reputation safeguards

| Risk | Safeguard |
|---|---|
| Wrong data misleads a user | Provenance on every fact; `basis` on curated facts; transition status; tests on known history; SITL checks later |
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
| M2 | Translations | Parser covers every rule in all tracked tags; known cases tested (GNSS, heater, COM_RC_OVERRIDE). |
| M3 | Changes + curation | Diff engine; completeness check; curated v1.17 → v1.18 and v1.16 → v1.17. |
| M4 | Histories + CLI | `params/` built; `history`, `diff`, `check <file.params>` commands. |
| M5 | Upgrade checker | The page in `web/` reads this data. |
| M6 | SITL verification | Translation rules tested by in-place upgrade. |
| M7 | Release v0.1 | Announced with PX4 v1.18.0 final. |

## Open questions

1. Per-board availability: from each board's Kconfig, or from the
   `parameters.json.xz` that release builds embed?
