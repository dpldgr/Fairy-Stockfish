# Burning and Tenjiku area regressions

Build the engine with assertions enabled. The Python tests use its actual
parser, legal moves, notation, search and perft interfaces.

```sh
make -C src clean
make -C src -j2 ARCH=x86-64-bmi2 board_files=16 board_ranks=16 debug=yes build
STOCKFISH=./src/stockfish python3 tests/tenjiku_burn_area.py
```

For 19x19 and the largest piece catalogue:

```sh
make -C src clean
make -C src -j2 ARCH=x86-64 board_files=19 board_ranks=19 piece_slots=512 gating=no debug=yes build
STOCKFISH=./src/stockfish BOARD_SIZE=19 PIECE_SLOTS=512 python3 tests/tenjiku_burn_area.py
```

The 19x19-specific case exercises a high piece slot and four explicit route
squares on the full board, including promotion, burning and fresh-position hash
comparison. The generic cases test all 584 open-board area routes, both colours,
returns, capture stopping, blockers, terrain, mobility, capture restrictions,
trading, promotion timing, inheritance, extinction, search and large move lists.

A standard 8x8 build keeps 32-bit moves. Run its burning-only subset and verify
that the parser rejects the area option with a rebuild diagnostic:

```sh
make -C src clean
make -C src -j2 ARCH=x86-64 debug=yes build
STOCKFISH=./src/stockfish TENJIKU_BURN_ONLY=1 python3 tests/tenjiku_burn_area.py
```

The C++ integration test also compares material/pawn/full hashes, PSQT totals,
counts, pockets, promotion provenance and checkers with a fresh position after
every generated route and a reply, then checks exact undo. It verifies UCI/USI
round trips and the general TRIPLE_MOVE encoding's three capture slots.
Link it against engine objects **from the same build**, excluding `main.o`.
For the 16x16 BMI2 build above:

```sh
g++ -std=c++17 -O2 -g -DIS_64BIT -DUSE_SSE2 -DUSE_PEXT -DUSE_POPCNT \
    -msse2 -mbmi2 -mpopcnt -DBOARD_FILES=16 -DBOARD_RANKS=16 \
    -DPIECE_TYPE_CAPACITY=64 -DENABLE_GATING=1 tests/tenjiku_state.cpp \
    $(find src -maxdepth 1 -name '*.o' ! -name main.o -print) \
    -lpthread -o /tmp/tenjiku-state
/tmp/tenjiku-state
```

For 19x19 use `BOARD_FILES=19`, `BOARD_RANKS=19`,
`PIECE_TYPE_CAPACITY=512`, `ENABLE_GATING=0`, and omit the PEXT/POPCNT defines and
architecture flags for the non-PEXT build. The encoding matrix checks all slot
capacities on five representative board geometries independently:

```sh
python3 tests/piece_slots_matrix.py
```
