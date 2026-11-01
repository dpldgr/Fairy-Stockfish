# Missile effects and colour-relative range blockers

```sh
make -C src clean
make -C src -j2 ARCH=x86-64 debug=yes build
STOCKFISH=./src/stockfish python3 tests/missile_effects.py
```

Repeat on 16x16 BMI2, then portable 19x19 with 512 slots:

```sh
make -C src clean
make -C src -j2 ARCH=x86-64-bmi2 board_files=16 board_ranks=16 debug=yes build
STOCKFISH=./src/stockfish BOARD_SIZE=16 python3 tests/missile_effects.py
make -C src clean
make -C src -j2 ARCH=x86-64 board_files=19 board_ranks=19 piece_slots=512 gating=no debug=yes build
STOCKFISH=./src/stockfish BOARD_SIZE=19 PIECE_SLOTS=512 python3 tests/missile_effects.py
```

The Python suite includes an independent ray-walking oracle on randomized boards,
both colours and friend/enemy/both/mixed blocker sets. Reverse attack queries are
also tested with directional rays, so blocker allegiance is tied to the attacker
rather than the reversed lookup direction. Other cases cover ordinary/strike
choices, hard endpoints, uncapturable Shields, terrain, mobility, all-colour and
pawn bycatch, passive burning precedence, elemental immunity, freezing/thawing,
promotion, no chain reactions, native king safety, simultaneous extinction,
search, parser validation, inheritance and high piece slots.

The shared `range_jump_state.cpp` C++ integration test additionally checks missile
strikes with holdings, mapped promoted movers/victims, combined elemental effects,
castling-right destruction and typed blocker replacement. Every move is checked
against fresh hashes, counts, holdings and promotion provenance, its hypothetical
attack map is compared with the real resulting position, and exact undo is
verified. Missile UCI/USI and SAN notation and TT move storage are checked explicitly.
Compile/link against matching engine objects using `range_jumps.md`.

`piece_slots_matrix.py` checks the new move type and existing encodings on all
40 board/capacity combinations, including 32-bit and 64-bit move builds. The new
MISSILE type uses the previously unused value 15 and adds no payload bits.

`fixtures/missile-chess.ini` supplies the requested 8x10 example. It uses
capture-the-royals rules, enemy-only pawn Shields, shifted castling, double steps
and en-passant regions, and mandatory promotion upon entry into either of the
last two ranks. An ordinary adjacent capture is e.g. `d4e4`; a strike with the
same endpoints is `d4e4!`. Interfaces must preserve the exclamation mark as part
of the move, not discard it as an annotation.
