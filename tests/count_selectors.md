# Counted hoppers and skip selectors

`count_selectors.py` tests exact counts and mixed selectors in the real parser,
move generator and legality code. Commas select alternatives and `..` selects
an inclusive integer range: `p[1,3..4]` means 1, 3 or 4 screens. The same grammar
applies to `j`, which counts initial squares instead of pieces.

The independent coordinate oracle enumerates each square on each ray, counting
occupied intervening squares before considering a landing. It covers 28 movement
definitions, both colours and 12 seeded random boards per definition/colour,
including opaque walls, captures, quiets, initial moves, ranges, exact and mixed
selectors, zero, duplicate selectors, large counts and overlapping movement terms.
Additional tests exercise native-King checks from adding/removing screens,
non-King double-check evasion via igui, promotions, drops, future-screen
immobility, search/root restoration, and long rays across six bitboard words on
19x19.

```sh
STOCKFISH=./stockfish BOARD_SIZE=8 python3 ../tests/count_selectors.py
STOCKFISH=./stockfish BOARD_SIZE=16 python3 ../tests/count_selectors.py
STOCKFISH=./stockfish BOARD_SIZE=19 PIECE_SLOTS=512 python3 ../tests/count_selectors.py
```

The existing `skip_rays.py` suite covers legacy scalar `j` syntax and the Heavenly
Tetrarch. `range_jump_state.cpp` additionally checks hypothetical versus actual
attacks, FEN reload, hashes, material, pockets, promotion provenance, and exact
undo for counted rays, native Kings, drops, promotion, castling and en passant.
Build/link that harness as described in `range_jumps.md`.

Legacy implicit single-screen `p`, repeated `p` and grasshoppers retain their
existing path. Explicit numeric/bracket `p` terms use the generalized path,
including opaque walls and the existing typed-attack safety policy. Suffix 1
retains grasshopper-style landing immediately after the required screen; larger
distance limits bound the destination from the original square.

This does not add the Dai Seireigi restriction against jumping to capture/check
a King; generalized hopper attacks are ordinary attacks unless separately
restricted. Screens are not captured and move encoding is unchanged.
