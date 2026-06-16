#!/bin/bash
# Compare generated magics, precomputed magics, and PEXT for equivalent
# horizontal/vertical board configurations.
#
# Configure the tested positions through environment variables, for example:
#   H_FILES=12 H_RANKS=10 H_VARIANT=my12x10 H_POSITION='startpos' \
#   V_FILES=10 V_RANKS=12 V_VARIANT=my10x12 V_POSITION='startpos' \
#   DEPTH=3 ./tests/magic_parity.sh
#
# H_VARIANT_FILE and V_VARIANT_FILE can point to separate ini files when the
# two orientations cannot be checked from a single variants.ini.
# Set PERFT_JSONL=/path/to/file.jsonl to save one generic JSON record per
# build with the UCI position, depth, and all root move node counts. Use
# {label} in the path to write one named file per build configuration.

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SRC_DIR="$ROOT_DIR/src"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

H_FILES=${H_FILES:-8}
H_RANKS=${H_RANKS:-8}
V_FILES=${V_FILES:-8}
V_RANKS=${V_RANKS:-8}
H_VARIANT=${H_VARIANT:-chess}
V_VARIANT=${V_VARIANT:-chess}
H_POSITION=${H_POSITION:-startpos}
V_POSITION=${V_POSITION:-startpos}
H_VARIANT_FILE=${H_VARIANT_FILE:-}
V_VARIANT_FILE=${V_VARIANT_FILE:-}
DEPTH=${DEPTH:-1}
JOBS=${JOBS:-2}
BASE_ARCH=${BASE_ARCH:-x86-64}
PEXT_ARCH=${PEXT_ARCH:-x86-64-bmi2}
OPTIMIZE=${OPTIMIZE:-no}
PERFT_JSONL=${PERFT_JSONL:-}

if [[ -n $PERFT_JSONL && $PERFT_JSONL != *'{label}'* ]]; then
  : > "$PERFT_JSONL"
fi

build_engine() {
  local label=$1 files=$2 ranks=$3 arch=$4 precomputed=$5

  make -C "$SRC_DIR" objclean >/dev/null
  make -C "$SRC_DIR" -j"$JOBS" ARCH="$arch" board_files="$files" board_ranks="$ranks" \
    precomputedmagics="$precomputed" optimize="$OPTIMIZE" build >/dev/null
  cp "$SRC_DIR/stockfish" "$TMP_DIR/stockfish-$label"
}

write_perft_json() {
  local label=$1 position=$2 depth=$3 jsonl=$4

  jsonl=${jsonl//\{label\}/$label}
  mkdir -p "$(dirname "$jsonl")"

  python3 - "$position" "$depth" "$jsonl" <<'PY'
import json
import os
import re
import sys

position, depth, jsonl = sys.argv[1:]
output = os.environ["PERFT_OUTPUT"].splitlines()
moves = {}

for line in output:
    match = re.fullmatch(r"([^:\s]+):\s+([0-9]+)", line.strip())
    if match:
        moves[match.group(1)] = match.group(2)

record = {
    "uci-pos": f"position {position}",
    "depth": depth,
    "moves": moves,
}

with open(jsonl, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
PY
}

run_perft() {
  local binary=$1 label=$2 variant=$3 position=$4 depth=$5 variant_file=$6
  local output nodes

  output=$( {
    if [[ -n $variant_file ]]; then
      printf 'load %s\n' "$variant_file"
    fi
    printf 'setoption name UCI_Variant value %s\n' "$variant"
    printf 'position %s\n' "$position"
    printf 'go perft %s\n' "$depth"
    printf 'quit\n'
  } | "$binary" )

  if [[ -n $PERFT_JSONL ]]; then
    PERFT_OUTPUT="$output" write_perft_json "$label" "$position" "$depth" "$PERFT_JSONL"
  fi

  nodes=$(sed -n 's/.*Nodes searched[^0-9]*\([0-9][0-9]*\).*/\1/p' <<< "$output" | tail -n 1)

  if [[ -z $nodes ]]; then
    echo "Unable to read perft nodes from $binary" >&2
    echo "$output" >&2
    return 1
  fi

  printf '%s' "$nodes"
}

configs=(
  "horizontal-generated:$H_FILES:$H_RANKS:$BASE_ARCH:no:$H_VARIANT:$H_POSITION:$H_VARIANT_FILE"
  "horizontal-precomputed:$H_FILES:$H_RANKS:$BASE_ARCH:yes:$H_VARIANT:$H_POSITION:$H_VARIANT_FILE"
  "horizontal-pext:$H_FILES:$H_RANKS:$PEXT_ARCH:no:$H_VARIANT:$H_POSITION:$H_VARIANT_FILE"
  "vertical-generated:$V_FILES:$V_RANKS:$BASE_ARCH:no:$V_VARIANT:$V_POSITION:$V_VARIANT_FILE"
  "vertical-precomputed:$V_FILES:$V_RANKS:$BASE_ARCH:yes:$V_VARIANT:$V_POSITION:$V_VARIANT_FILE"
  "vertical-pext:$V_FILES:$V_RANKS:$PEXT_ARCH:no:$V_VARIANT:$V_POSITION:$V_VARIANT_FILE"
)

expected_nodes=

for config in "${configs[@]}"; do
  IFS=: read -r label files ranks arch precomputed variant position variant_file <<< "$config"

  echo "Building $label ($files x $ranks, ARCH=$arch, precomputedmagics=$precomputed, optimize=$OPTIMIZE)"
  build_engine "$label" "$files" "$ranks" "$arch" "$precomputed"

  nodes=$(run_perft "$TMP_DIR/stockfish-$label" "$label" "$variant" "$position" "$DEPTH" "$variant_file")
  echo "$label nodes: $nodes"

  if [[ -z $expected_nodes ]]; then
    expected_nodes=$nodes
  elif [[ $nodes != "$expected_nodes" ]]; then
    echo "Magic parity check failed: $label produced $nodes nodes, expected $expected_nodes" >&2
    exit 1
  fi
done

echo "Magic parity check passed: all configurations produced $expected_nodes nodes."
