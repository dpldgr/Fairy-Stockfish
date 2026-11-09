# Multi-character hands

Variants with multi-character piece symbols use comma-separated whole-symbol
hands, consistently with board placement. `[RR]` is one RR piece; `[R,R]` is two
R pieces; `[RR,R,rh]` mixes types and colours. SFEN counts prefix an entire entry:
`2RR,R,3rh`. FEN repeats entries: `[RR,RR,R,rh,rh,rh]`. Whitespace is not allowed
inside the hand field. No prefix/longest-match splitting occurs in hands;
unknown entries are ignored as whole tokens. Single-character variants retain
compact FEN/SFEN notation, while accepting explicitly separated input too.

`hand_symbols.py` tests both formats, ambiguous/prefix-related names, counts,
empty and unknown entries, both colours, captures and demotion, promoted drops,
retaining a named promoted form with dropLoop, the highest ordinary custom slot,
and standard Crazyhouse/Shogi/Seirawan notation. Position keys and legal move
sets are compared across FEN/SFEN reloads. SFEN has no halfmove clock, so that
field is excluded from the cross-format FEN comparison.

The suite exercises root cloning through real `go perft` and `go depth` calls,
including the Dai Seireigi capture that previously turned a held RH into R.
The existing `range_jump_state.cpp` harness adds FEN/SFEN checks for board and
hand counts, keys, material, PSQT, promotion provenance and exact do/undo after
every legal move in mixed-hand fixtures. Link it using `range_jumps.md`.

```sh
STOCKFISH=./stockfish BOARD_SIZE=8 PIECE_SLOTS=64 python3 ../tests/hand_symbols.py
STOCKFISH=./stockfish BOARD_SIZE=16 PIECE_SLOTS=128 python3 ../tests/hand_symbols.py
STOCKFISH=./stockfish BOARD_SIZE=19 PIECE_SLOTS=512 GATING=no python3 ../tests/hand_symbols.py
```

The Dai Seireigi case needs at least 16x16/128 slots. The Seirawan case is skipped
when gating is disabled. The remaining cases work on an ordinary 8x8 build.
