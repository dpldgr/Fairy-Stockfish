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
tradingRule = q:[dist!,{q}]

[cub-anti-trade:chess]
customPiece1 = c:KNAD
tradingRule = c:[dist,{c}]

[cub-no-capture:chess]
customPiece1 = c:KNAD
tradingRule = c:[any,{c}]

[lion-anti-trade:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l:[dist!,{l}]

[lion-ineligible:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l:[dist!,{l}] l:[dist2c!,{l},{p}]

[lion-no-dist2c:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l:[dist2c,{l}]

[lion-no-adj2c:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l:[adj2c,{l}]

[lion-no-adj2c-p:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l:[adj2c,{l},{p}]

[lion-dist2c-protected:chess]
customPiece1 = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
tradingRule = l:[dist2c!,{l}]

[lion-counterstrike:chess]
customPiece1 = l:KNAD
tradingRuleCounterstrike = {l}

[lion-counterstrike-promotion:chess]
customPiece1 = c:N
customPiece2 = l:KNAD
promotedPieceType = c:l
promotionRegionWhite = *6
tradingRuleCounterstrike = {l}
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

check_move()
{
  variant=$1
  position=$2
  moves=$3
  move=$4
  expected=$5
  output=$(printf 'setoption name UCI_Variant value %s\nposition fen %s moves %s\ngo perft 1\nquit\n' \
           "$variant" "$position" "$moves" | ./stockfish load "$trading_rules" 2>/dev/null)
  if [ "$expected" = present ]; then
    printf '%s\n' "$output" | rg -q "^$move:"
  else
    ! printf '%s\n' "$output" | rg -q "^$move:"
  fi
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
check_perft cub-no-capture "7k/8/8/8/8/8/8/Cc5K w - - 0 1" 10

# A protected distant Lion requires a qualifying intermediate capture.
check_perft lion-anti-trade "7k/2r5/8/8/8/8/8/L1l4K w - - 0 1" 26
check_perft lion-anti-trade "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 27
check_perft lion-anti-trade "7k/8/8/8/8/8/8/L1l4K w - - 0 1" 29

# Lions moved out from behind their pawns retain their two-leg quiet moves.
check_perft lion-anti-trade "rnb1kbnr/pppppppp/3l4/8/8/3L4/PPPPPPPP/RNB1KBNR w KQkq - 2 2" 68

# Distant two-capture restrictions are independent and may filter connector types.
check_perft lion-ineligible "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 26
check_perft lion-ineligible "7k/8/8/8/8/8/8/Lpl4K w - - 0 1" 29
check_perft lion-ineligible "7k/2r5/8/8/8/8/8/Lnl4K w - - 0 1" 27
check_perft lion-no-dist2c "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 28
check_perft lion-dist2c-protected "7k/2r5/8/8/8/8/8/Lpl4K w - - 0 1" 28
check_perft lion-dist2c-protected "7k/8/8/8/8/8/8/Lpl4K w - - 0 1" 29

# An adjacent second target is adj2c rather than dist2c.
check_perft lion-no-adj2c "7k/8/8/8/8/8/1p6/Ll5K w - - 0 1" 28
check_perft lion-no-adj2c-p "7k/8/8/8/8/8/1p6/Ll5K w - - 0 1" 28
check_perft lion-no-adj2c-p "7k/8/8/8/8/8/1n6/Ll5K w - - 0 1" 29

# A non-Lion counter-strike on another square is forbidden when recapturable.
check_move lion-counterstrike "3r3k/8/1l1L4/2B5/N7/8/8/7K w - - 0 1" a4b6 d8d6 absent

# The Okazaki rule permits the counter-strike when its attacker is unrecapturable.
check_move lion-counterstrike "3r3k/8/1l1L4/8/N7/8/8/7K w - - 0 1" a4b6 d8d6 present

# A preceding Lion capture does not activate the non-Lion counter-strike restriction.
check_move lion-counterstrike "3r3k/8/1l1L4/2B5/L7/8/8/7K w - - 0 1" a4b6 d8d6 present

# A Kirin-like piece is recorded before promotion: the fresh Lion may be captured
# on the same square, but a recapturable Lion on another square may not be captured.
check_move lion-counterstrike-promotion "1r5k/8/1l6/2B5/C7/8/8/7K w - - 0 1" a4b6+ b8b6 present
check_move lion-counterstrike-promotion "3r3k/8/1l1L4/2B5/C7/8/8/7K w - - 0 1" a4b6+ d8d6 absent

# Conflicting duplicate rules are diagnosed by variant validation.
invalid_rules=$(mktemp)
cat > "$invalid_rules" << 'EOF'
[invalid-trading:chess]
tradingRule = q:[dist!,{q}] q:[dist!,{q}]
EOF
output=$(./stockfish check "$invalid_rules" 2>&1)
printf '%s\n' "$output" | rg -q "tradingRule - Invalid or conflicting rule"

# Subsumed clauses produce a warning only when their scopes match exactly.
cat > "$invalid_rules" << 'EOF'
[subsumed-trading:chess]
tradingRule = q:[any,{q}] q:[dist!,{q}]
EOF
output=$(./stockfish check "$invalid_rules" 2>&1)
printf '%s\n' "$output" | rg -q "tradingRule - Warning: subsumed clause"

# Target/restrictor lists and restrictor placement are validated exactly.
cat > "$invalid_rules" << 'EOF'
[invalid-trading-target:chess]
tradingRule = q:[dist!,{q,missing}]

[invalid-trading-restrictor:chess]
tradingRule = q:[dist!,{q},{p}]

[invalid-trading-overlap:chess]
tradingRule = q:[dist!,{q,r}] q:[dist,{q}]

[invalid-trading-counterstrike:chess]
tradingRuleCounterstrike = {missing}
EOF
output=$(./stockfish check "$invalid_rules" 2>&1)
test "$(printf '%s\n' "$output" | rg -c "tradingRule - Invalid or conflicting rule")" -eq 3
printf '%s\n' "$output" | rg -q "tradingRuleCounterstrike - Invalid target set"

echo "trading rule testing OK"
