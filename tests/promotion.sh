#!/bin/bash
# Verify promotion limits with optional and mandatory piece promotion.

set -euo pipefail

config=$(mktemp)
trap 'rm -f "$config"' EXIT

cat > "$config" <<'EOF'
[limited-piece:chess]
promotionPawnTypes = -
promotionPieceTypes = -
promotedPieceType = n:q
promotionRegionWhite = *7 *8
promotionRegionBlack = *1 *2
promotionLimit = q:1
mandatoryPiecePromotion = true

[optional-limited-piece:limited-piece]
mandatoryPiecePromotion = false

[capture-limited-piece:limited-piece]
piecePromotionOnCapture = true

[available-piece:limited-piece]
promotionLimit = q:2

[limited-pawn:chess]
promotionPieceTypes = q
promotionLimit = q:1

[limited-mapped-pawn:limited-pawn]
promotionPieceTypes = -
promotedPieceType = p:q

[available-mapped-pawn:limited-mapped-pawn]
promotionLimit = q:2

[empty-pawn:limited-pawn]
promotionPieceTypes = -

[available-pawn:limited-pawn]
promotionPieceTypes = qn
EOF

check_moves()
{
  local variant=$1 position=$2
  shift 2
  local output move expected
  # Perft also checks generated moves against pseudo_legal in debug builds.
  output=$(./stockfish load "$config" <<EOF
setoption name UCI_Variant value $variant
position fen $position
go perft 1
quit
EOF
)
  while (( $# )); do
    move=$1
    expected=$2
    shift 2
    if printf '%s\n' "$output" | grep -Fq "$move: "; then
      if [[ $expected != yes ]]; then
        echo "$variant unexpectedly generated $move" >&2
        exit 1
      fi
    elif [[ $expected == yes ]]; then
      echo "$variant did not generate $move" >&2
      exit 1
    fi
  done
}

quiet='4k3/8/2N5/8/8/8/8/Q3K3 w - - 0 1'
capture='1r2k3/8/2N5/8/8/8/8/Q3K3 w - - 0 1'

# At the limit, neither form of a mandatory promotion move may be generated.
check_moves limited-piece "$quiet" c6b8 no c6b8+ no c6a5 yes
check_moves limited-piece "$capture" c6b8 no c6b8+ no
check_moves limited-piece '5k2/2N5/8/8/8/8/8/Q3K3 w - - 0 1' \
  c7e8 no c7e8+ no c7b5 no c7b5+ no
check_moves limited-piece 'q3k3/8/8/8/8/2n5/8/4K3 b - - 0 1' \
  c3b1 no c3b1+ no c3a4 yes

# Optional promotions still permit the unpromoted move when at the limit.
check_moves optional-limited-piece "$quiet" c6b8 yes c6b8+ no
check_moves optional-limited-piece "$capture" c6b8 yes c6b8+ no

# Capture-only rules retain quiet moves but prohibit blocked mandatory captures.
check_moves capture-limited-piece "$quiet" c6b8 yes c6b8+ no
check_moves capture-limited-piece "$capture" c6b8 no c6b8+ no

# An available target still generates the mandatory promotion normally.
check_moves available-piece "$quiet" c6b8 no c6b8+ yes c6a5 yes
check_moves available-piece "$capture" c6b8 no c6b8+ yes

# Pawn-style promotions retain their existing target-limit behaviour.
check_moves limited-pawn '4k3/1P6/8/8/8/8/8/Q3K3 w - - 0 1' \
  b7b8 no b7b8q no
check_moves empty-pawn '4k3/1P6/8/8/8/8/8/Q3K3 w - - 0 1' \
  b7b8 no b7b8q no
check_moves available-pawn '4k3/1P6/8/8/8/8/8/Q3K3 w - - 0 1' \
  b7b8 no b7b8q no b7b8n yes

# The internal Pawn's fixed mapping must obey the target limit as well.
check_moves limited-mapped-pawn '4k3/1P6/8/8/8/8/8/Q3K3 w - - 0 1' \
  b7b8 no b7b8+ no
check_moves available-mapped-pawn '4k3/1P6/8/8/8/8/8/Q3K3 w - - 0 1' \
  b7b8 no b7b8+ yes

echo 'promotion limit testing OK'
