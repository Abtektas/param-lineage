# Contributing

Issues and pull requests are welcome. Everything in this repository is written
in English.

## Before you start

- Read the "Safety and liability" section of the [README](README.md) and the
  [design](docs/DESIGN.md). Wrong data that looks right is worse than no data.
- For a new kind of data or a new command, open an issue first.

## Facts need evidence

- Generated files (snapshots, translations, built views) are never edited by
  hand. Change the extractor and rebuild them.
- A curated fact names its evidence: the PX4 commit (required), the pull
  request when known, and its basis (`code-inspection`, `release-notes` or
  `sitl-tested`). Only claim `sitl-tested` for what was run.
- Do not mark a transition `complete` until every removed parameter in it has
  an entry.

## Running the tests

```
python3 -m unittest discover -s tests -t .
node --test web/test/
```

This needs Python 3.11 or newer and Node.js 18 or newer, and nothing else.
The schema tests run when `jsonschema` is installed
(`pip install --require-hashes -r requirements/schema.txt`); CI requires them.

To extract every tracked release again and compare it with `data/snapshots`,
you need a git repository of PX4 with the tags and a Python with
`requirements/extract.txt`:

```
python -m paramlineage.extract --repo <PX4 repository> --python <that python> --check --all
```

Run it from the repository root, with `PYTHONPATH=src` or after `pip install .`.
Only extract from PX4's official repository: the extractor runs scripts from
the tag.

The translations need a C++17 compiler (`$CXX`, or `c++`); their tests are
skipped without one. To run every tracked release's translation code again
and compare it with `data/translations`:

```
python -m paramlineage.translations --repo <PX4 repository> --check --all
```

This compiles and runs code from the tag, so the same rule applies.

The changes are built from the snapshots and the curated facts; the tests
fail when they are out of date. To build them again:

```
python -m paramlineage.changes --all
```

## Adding a release

1. Add the tag to `TRACKED` in `src/paramlineage/extract.py` (a release
   candidate replaces the previous one; a final release replaces its
   candidates) and write its snapshot with
   `python -m paramlineage.extract --repo <PX4 repository> --python <python> <tag>`.
2. If PX4 changed how its generators are called, adapt `Generators` so that
   the snapshots of older tags stay the same (`--check --all`). If they cannot
   stay the same, raise `EXTRACTOR` and extract them all again.
3. Add the firmware parameter lists of the release's fmu-v5 and fmu-v6x builds
   with `tests/fixtures/firmware/make_list.py`, and update the known counts in
   `tests/test_snapshots.py`.
4. Write its translations with
   `python -m paramlineage.translations --repo <PX4 repository> <tag>`. If the
   extractor stops because the import code is new, read
   `param_import_callback()` in the release's `parameters.cpp` and
   `flashparams.cpp`, and add it to `IMPORT_CODE` in
   `src/paramlineage/translations.py` with the model it follows. If the
   release's translation code no longer builds with the harness, adapt the
   harness so that the files of older tags stay the same (`--check --all`).
5. Build the changes (`python -m paramlineage.changes --all`).
6. Curate the parameters it removed in `data/curated/<previous>..<tag>.json`:
   for each one, find the commit that deletes its definition
   (`git log -S <NAME> <previous>..<tag>`), read it and the new release's
   source, and choose the kind. Every entry needs the full commit hash and a
   note that a user of the previous release can act on. Set the status to
   `complete` only when every removed parameter is listed.

## What a change needs

- Tests.
- No copy of PX4's source code, apart from the three lines of
  `src/paramlineage/harness/platform.h` that the compiled code needs by name
  (marked there). The extractor runs PX4's own generators from the release
  tag; where the project has to repeat PX4 logic, the code names the PX4 file
  it follows.
- An entry in [CHANGELOG.md](CHANGELOG.md).

## Names and terms

- "PX4" is a trademark of Dronecode Project, Inc. Nothing in this project is
  named with it: not the repository, package, module, command, a file name,
  a release asset, a heading, a page title, a domain or a logo. It appears only
  in sentences that refer to PX4 itself, such as "parameter history for PX4",
  with the trademark notice. The tests check file names, headings and titles.
- The terms in the README, in `--version` and on the page are part of the
  program. A change must not weaken or remove them.

## Commits

- Sign off your commits (`git commit -s`). The sign-off certifies the
  [Developer Certificate of Origin](https://developercertificate.org/).
- If an AI assistant helped with a change, say so with an `Assisted-by:`
  trailer in the commit message. Do not add an AI as co-author. You are
  responsible for everything you submit.
