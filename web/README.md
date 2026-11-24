# Upgrade check page

A single offline HTML page that checks a QGroundControl `.params` file saved on PX4 v1.17.0
before it is loaded on v1.18.0, and writes a corrected copy. It started as a separate local
project (px4-param-upgrade, never published) and moved here on 2026-10-23, and is now built from
the project's data (see [../docs/DESIGN.md](../docs/DESIGN.md)).

PX4 converts renamed parameters (`param_translation.cpp`) only when it upgrades the parameters
stored on the vehicle. Loading a saved file in QGroundControl sets parameters one by one, so values
under old names are dropped and old defaults come back. The page lists:

- values lost when the file is loaded as it is, and writes them the way PX4 converts them;
- `RC*_REV`, now int32: QGroundControl cannot read the saved `-1.000000` into the integer parameter
  and sends 0, which PX4 treats as not reversed;
- removed parameters PX4 does not convert, with what replaced them and the commit;
- old defaults (parameter and airframe) the file would set again;
- values outside a range the new release narrowed (QGroundControl does not check ranges when it
  loads a file).

The page stays on the computer and makes no network requests. The terms in the repository
[README](../README.md#safety-and-liability) apply, and the page shows them under every check.

## Build

From this folder, with a clone of PX4 that has the release tags (it is read only for the startup
scripts of the airframes):

```sh
python3 tools/build_data.py <PX4 git repo> v1.17.0 v1.18.0 data/v1.17.0_to_v1.18.0.json
python3 tools/build_page.py data/v1.17.0_to_v1.18.0.json dist/param-lineage-upgrade-check-v1.17.0-to-v1.18.0.html
node --test test/*.test.js
```

`build_data.py` reads the repository's data: the snapshots of both tags (`../data/snapshots`), the
curated facts and the changes of the pair (`../data/curated`, `../data/changes`), and the page's
own rules in `tools/hints_v1_17_to_v1_18.py`. The notes the page shows are the curated entries as
they are. The rules are the page's behaviour, not facts: how it converts a `migrated` value in the
corrected file, and what it suggests setting by hand for the others. The build stops unless the
curated facts cover exactly the removed parameters, every `migrated` entry and only those has a
conversion rule writing exactly the entry's successors, the type rules match the type changes, and
the PX4 clone has each tag at the commit its snapshot was made from.

## Verification

- `test/fixtures/v1.17.0_sihsim_quadx_custom.params` was saved from v1.17.0 SIH SITL with nine
  settings changed. `test/fixtures/v1.18.0_inplace_upgrade.params` is v1.18.0 SITL after an
  in-place upgrade of that vehicle's storage. Loading the corrected file into a fresh v1.18.0
  SITL (`tools/sitl/mavparams.py load`) gave the same parameters as the in-place upgrade; the only
  differences were `_HASH_CHECK`, three unused `CAL_BAROn_ID` slots listed with 0, and the last
  float bit of `EKF2_MAG_DECL`, which the estimator saves while it runs. `CAL_BARO0_OFF`, the baro
  offset PX4 works out again at boot (`SENS_BAR_AUTOCAL`), differs between runs.
  Loading the original file instead differed in 10 values: 6 conversions lost and 4 old defaults
  set again.
- Five files saved on v1.17.0 hardware and published on GitHub (four complete, one partial) were
  checked with the page. Two had reversed RC channels, one GPS antenna offsets that would be lost.
- QGroundControl v5.1.5 (release DMG) and master (95680219f), each connected to a fresh
  v1.18.0-rc1 SITL (not repeated on v1.18.0, whose `RC*_REV` metadata is the same): loading a v1.17 file with `RC1_REV` and `RC3_REV` at `-1.000000` set all
  `RC*_REV` on the vehicle to 0. The corrected file set them to -1, 1, -1.
- `node --test test/*.test.js`: the analysis and the corrected file, and the terms. Every conversion
  rule and the `RC*_REV` fix are checked against every probe value in
  `../data/translations/v1.18.0.json`: the corrected file writes what PX4 stores on an in-place
  upgrade, no more and no less.
- `test/page_check.js`: the built page with jsdom (rendering, download, no markup injection from a
  file). It needs jsdom; see the comment at its top.

## Not covered

Defaults from board files (`rc.board_defaults`) or set inside conditions in startup scripts, and
parameters that kept their name but changed meaning.
