#!/bin/bash
# Verify configurable capture-trading restrictions.

error()
{
  echo "trading rule testing failed on line $1"
  exit 1
}
trap 'error ${LINENO}' ERR

cleanup()
{
  rm -f "${trading_rules:-}" "${invalid_rules:-}"
}
trap cleanup EXIT

echo "trading rule testing started"

trading_rules=$(mktemp)
cat > "$trading_rules" << 'EOF'
[queen-anti-trade:chess]
tradingRule = q(dist!, q)

[cub-anti-trade:chess]
customPiece1 = c:KNAD
tradingRule = c(dist, c)

[lion-anti-trade:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l(dist!, l)

[lion-exception:lion-anti-trade]
tradingRuleMultiCaptureExceptions = l(p)

[lion-no-multi:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l(mc, l)

[lion-no-multi-exception:lion-no-multi]
tradingRuleMultiCaptureExceptions = l(p)

[lion-multi-protected:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l(mc!, l)
EOF

check_perft()
{
  variant=$1
  position=$2
  expected=$3
  output=$(printf 'setoption name UCI_Variant value %s\nposition fen %s\ngo perft 1\nquit\n' "$variant" "$position" \
           | ./stockfish load "$trading_rules" 2>/dev/null)
  printf '%s\n' "$output" | rg -q "Nodes searched: $expected"
}

# A distant queen capture is forbidden when the capturing queen is attacked.
check_perft queen-anti-trade "7k/q6r/8/8/8/8/Q7/K7 w - - 0 1" 6

# Adjacent queen captures remain legal even when the capturing queen is attacked.
check_perft queen-anti-trade "7k/q6r/Q7/8/8/8/8/K7 w - - 0 1" 8

# A distant queen capture remains legal when the capturing queen is not attacked.
check_perft queen-anti-trade "7k/q7/8/8/8/8/Q7/K7 w - - 0 1" 7

# A Cub may capture another Cub only when it is adjacent.
check_perft cub-anti-trade "7k/8/8/8/8/8/8/C1c4K w - - 0 1" 10
check_perft cub-anti-trade "7k/8/8/8/8/8/8/Cc5K w - - 0 1" 11

# A protected distant Lion requires a qualifying intermediate capture.
check_perft lion-anti-trade "7k/2r5/8/8/8/8/8/L1l4K w - - 0 1" 26
check_perft lion-anti-trade "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 27
check_perft lion-anti-trade "7k/8/8/8/8/8/8/L1l4K w - - 0 1" 29

# Lions moved out from behind their pawns retain their two-leg quiet moves.
check_perft lion-anti-trade "rnb1kbnr/pppppppp/3l4/8/8/3L4/PPPPPPPP/RNB1KBNR w KQkq - 2 2" 68

# Excepted intermediate pieces do not qualify, and mc restrictions are enforced.
check_perft lion-exception "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 26
check_perft lion-no-multi "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 28
check_perft lion-no-multi-exception "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 28
check_perft lion-multi-protected "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 28
check_perft lion-multi-protected "7k/8/8/8/8/8/8/Lpl4K w - - 0 1" 29

# Conflicting duplicate rules are diagnosed by variant validation.
invalid_rules=$(mktemp)
cat > "$invalid_rules" << 'EOF'
[invalid-trading:chess]
tradingRule = q(dist!, q) q(dist, q)
EOF
output=$(./stockfish check "$invalid_rules" 2>&1)
printf '%s\n' "$output" | rg -q "tradingRule - Invalid or conflicting rule"

echo "trading rule testing OK"
