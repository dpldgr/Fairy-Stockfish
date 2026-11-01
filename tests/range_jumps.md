# Range-jumping regressions

The Python tests use the engine's parser, legal move lists, search, notation and
perft. A separate square-by-square oracle checks both colours and all four
capture-only Tenjiku General configurations on randomized boards. Other cases cover
independent blocker sets and directions, inheritance, Shields, terrain,
mobility, promotions, trading, native kings and pseudo royals. In particular,
they check two same-ray checks that can both be stopped by one blocker, and
captures/promotions that change the type of an intervening piece.

```sh
make -C src clean
make -C src -j2 ARCH=x86-64 debug=yes build
STOCKFISH=./src/stockfish python3 tests/range_jumps.py

make -C src clean
make -C src -j2 ARCH=x86-64-bmi2 board_files=16 board_ranks=16 debug=yes build
STOCKFISH=./src/stockfish BOARD_SIZE=16 python3 tests/range_jumps.py

make -C src clean
make -C src -j2 ARCH=x86-64 board_files=19 board_ranks=19 piece_slots=512 gating=no debug=yes build
STOCKFISH=./src/stockfish BOARD_SIZE=19 PIECE_SLOTS=512 python3 tests/range_jumps.py
```

The last command also exercises the two highest custom slots and rays spanning
all six bitboard words on the full 19×19 board.

With at least 16×16 and 128 piece slots, the suite also searches the Tenjiku
fixture in `fixtures/tenjiku-range-search.ini`. It verifies that the ordinary
quiet GG move `i13h14` is searched after White's GG is passively burned on h14:
the preceding `h4h14` must score mate -2 at depth 4, and Black must select
`i13h14` with mate 2 at depth 3. Smaller builds skip this fixture.

`range_jump_state.cpp` compares typed hypothetical attack queries with queries
after actually making every legal move. It checks promotion provenance,
material, pockets, PSQT, hashes and exact undo against fresh positions, and
round-trips UCI/USI capture notation. Cases include drops of a source type absent
from the board, castling, en passant, explosions, petrification, gating and
moving walls. Existing Seirawan full/material hash discrepancies on FEN reload
are excluded from the fresh-hash comparison only; geometry, counts, attack
queries and exact undo remain checked for gating.

Link against matching engine objects, excluding `main.o`. For the 16×16 build:

```sh
g++ -std=c++17 -O2 -g -DIS_64BIT -DUSE_SSE2 -DUSE_PEXT -DUSE_POPCNT \
    -msse2 -mbmi2 -mpopcnt -DBOARD_FILES=16 -DBOARD_RANKS=16 \
    -DPIECE_TYPE_CAPACITY=64 -DENABLE_GATING=1 tests/range_jump_state.cpp \
    $(find src -maxdepth 1 -name '*.o' ! -name main.o -print) \
    -lpthread -o /workspace/range-jump-state
/workspace/range-jump-state
```

For 8×8, change both board dimensions to 8 and omit PEXT/POPCNT defines and
flags. For the 19×19 portable build, also use `PIECE_TYPE_CAPACITY=512` and
`ENABLE_GATING=0`.

Jump rows now require an actual intervening piece. Use `cR/cB/cQ` for
Tenjiku captures only; `R/B/Q` includes quiet jumps, while `mR/mB/mQ`
permits quiet jumps only. Base piece movement remains independent.
