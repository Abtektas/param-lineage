#!/bin/sh
# Generate the complete parameter metadata of a PX4 source tree with PX4's own generators.
# Same steps as the metadata_parameters target (cmake/metadata.cmake), but it reads every module
# config under src/, including the ones that target skips (src/modules/spacecraft, src/systemcmds).
# usage: gen_params_json.sh <px4 source tree> <output parameters.json> [python]
set -e
SRC=$(cd "$1" && pwd -P); OUT=$2; PY=${3:-python3}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cd "$SRC"
find src -name '*.yaml' | grep -v -e '/pwm_out_sim/' -e '/linux_pwm_out/' | sort > "$TMP/yaml.txt"
"$PY" Tools/serial/generate_config.py --all-ports --ethernet --params-file "$TMP/serial_params.c" \
	--config-files $(cat "$TMP/yaml.txt") > /dev/null
"$PY" Tools/module_config/generate_params.py --params-file "$TMP/module_params.c" \
	--timer-config boards/px4/fmu-v5/src/timer_config.cpp --board-with-io --ethernet \
	--config-files $(cat "$TMP/yaml.txt") > /dev/null
"$PY" src/lib/parameters/px_process_params.py --src-path $(find src -type d) "$TMP" --json "$OUT"
