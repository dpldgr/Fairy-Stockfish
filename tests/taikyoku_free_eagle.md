# Coordinate atoms and Taikyoku Free Eagle

Run the integration suite against an 8x8 engine (including 32-bit move builds):

```sh
STOCKFISH=/path/to/stockfish python3 tests/taikyoku_free_eagle.py -v
```

Run the long-leap/high-slot test against larger builds:

```sh
BOARD_SIZE=19 PIECE_SLOTS=512 STOCKFISH=/path/to/stockfish \
    python3 tests/taikyoku_free_eagle.py FreeEagle.test_wide_board_high_slot_and_long_leaps -v
BOARD_SIZE=36 PIECE_SLOTS=512 STOCKFISH=/path/to/stockfish \
    python3 tests/taikyoku_free_eagle.py FreeEagle.test_wide_board_high_slot_and_long_leaps -v
```

The independent oracle walks rays square by square, checking compulsory prefix
length, intermediate captures, friendly/prohibited blockers and the ordinary
tail. Cases cover both colours, empty prefix squares, five captures, quiet
endpoints, capture-based promotion and promoted-victim policies, transformation
order/choices, trading restrictions on all five victims, hands, passive/active
burn, transformation-triggered burn, freezing, mobility, native royal safety,
extinction search and reset/invalid configuration. Distinct compound paths and
jumps/sweeps with the same endpoint remain distinguishable; identical paths and
equivalent ordinary moves are suppressed.

Coordinate cases check symmetry, direction/modality, swapped components, large
and impossible offsets, and syntax errors. Wide tests use the highest custom
slot, file labels beyond z, a 35-square leap and a sweep across the full board.
`fixtures/taikyoku-free-eagle.ini` contains an isolated complete definition.

The C++ `range_jump_state.cpp` harness also exercises the new ability. Link it
against matching engine objects and architecture/board/type defines as described
in `range_jumps.md`. It checks every legal move against hypothetical attack
overlays and fresh FEN/SFEN reconstruction, including material, pockets, PSQT,
hashes, promotion provenance, checkers, exact undo and UCI/USI/TT round trips.
It covers promoted movers/demotion and native pawn promotion, as well as all five
victims. Coordinate tables are checked on every compiled-board square in both
colours, and `(2,1)`/`N`/`N(2,1)` must have equal material estimates.

The Free Eagle uses a reserved double-move payload whose first landing equals
its origin; ordinary double moves never have that first landing. Endpoints and
mover colour determine the compulsory ray prefix. Existing promotion payloads
and bycatch restoration storage are reused, without widening Move, Position or
StateInfo. Prefix victims nevertheless follow genuine-capture rules, including
hands and capture ordering. UCI/USI emits the full deterministic route, with up
to five destinations. Callers of `move_path()` must provide `MAX_PATH_SQUARES`
entries unless the move is known to be an existing shorter route.
