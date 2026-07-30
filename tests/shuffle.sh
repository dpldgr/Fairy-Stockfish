#!/bin/bash
# Verify deterministic shuffled-position generation and startpos isolation.

set -euo pipefail

config=$(mktemp)
trap 'rm -f "$config"' EXIT

cat > "$config" <<'EOF'
[shufflechess:chess]
chess960 = true
shuffleSquaresFenTemplate = bbqnnrkr/pppppppp/8/8/8/8/PPPPPPPP/BBQNNRKR w KQkq - 0 1
shuffleSquaresMethod = bb*rkr mirror
EOF

output=$(FAIRY_STOCKFISH_VARIANT_PATH="$config" ./stockfish <<'EOF'
setoption name UCI_Variant value shufflechess
shuffle-position seed 12345
shuffle-position seed 12345
position startpos
d fen
quit
EOF
)

expected="info string startFen bbrnnkqr/pppppppp/8/8/8/8/PPPPPPPP/BBRNNKQR w HChc - 0 1"
test "$(printf '%s\n' "$output" | grep -Fxc "$expected")" -eq 2
printf '%s\n' "$output" | grep -Fq "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"

echo "shuffle-position testing OK"
