#!/bin/bash
# Verify that UCI drop piece symbols are emitted in uppercase.

set -euo pipefail

output=$(./stockfish <<'EOF'
setoption name UCI_Variant value dragon
position fen 4k3/8/8/8/8/8/8/4K3[D] w - - 0 1
go depth 1 searchmoves D@a1
quit
EOF
)

printf '%s\n' "$output" | grep -Fqx "bestmove D@a1"

echo "UCI drop notation testing OK"
