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
EOF

check_perft()
{
  position=$1
  expected=$2
  output=$(printf 'setoption name UCI_Variant value queen-anti-trade\nposition fen %s\ngo perft 1\nquit\n' "$position" \
           | ./stockfish load "$trading_rules" 2>/dev/null)
  printf '%s\n' "$output" | rg -q "Nodes searched: $expected"
}

# A distant queen capture is forbidden when the capturing queen is attacked.
check_perft "7k/q6r/8/8/8/8/Q7/K7 w - - 0 1" 6

# Adjacent queen captures remain legal even when the capturing queen is attacked.
check_perft "7k/q6r/Q7/8/8/8/8/K7 w - - 0 1" 8

# A distant queen capture remains legal when the capturing queen is not attacked.
check_perft "7k/q7/8/8/8/8/Q7/K7 w - - 0 1" 7

# Conflicting duplicate rules are diagnosed by variant validation.
invalid_rules=$(mktemp)
cat > "$invalid_rules" << 'EOF'
[invalid-trading:chess]
tradingRule = q(dist!, q) q(dist, q)
EOF
output=$(./stockfish check "$invalid_rules" 2>&1)
printf '%s\n' "$output" | rg -q "tradingRule - Invalid or conflicting rule"

echo "trading rule testing OK"
