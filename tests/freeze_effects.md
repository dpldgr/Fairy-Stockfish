# Freeze effects and burn immunity

Run the integration suite against an assertion-enabled engine:

```sh
make -C src -j2 ARCH=x86-64 debug=yes build
STOCKFISH=./src/stockfish python3 tests/freeze_effects.py
```

Repeat on 16x16 BMI2 and on a portable 19x19/512-slot build:

```sh
make -C src clean
make -C src -j2 ARCH=x86-64-bmi2 board_files=16 board_ranks=16 debug=yes build
STOCKFISH=./src/stockfish python3 tests/freeze_effects.py
make -C src clean
make -C src -j2 ARCH=x86-64 board_files=19 board_ranks=19 piece_slots=512 gating=no debug=yes build
STOCKFISH=./src/stockfish BOARD_SIZE=19 PIECE_SLOTS=512 python3 tests/freeze_effects.py
```

The high-slot case is enabled only on the latter build. The generic suite checks
all eight aura directions and both colours, immunity and inheritance, frozen
sources, retained blocker identity, thawing, passive burners, direct captures
versus elemental/blast immunity, drops, trading protection, native king safety,
castling and both quiet-freezing and direct-royal-capture search wins.

The shared C++ `range_jump_state.cpp` test now also checks freeze-only and
combined range-jump/burn/freeze positions, mutually frozen emitters, native
royals, promotion into an emitter, drops, fresh-position freeze masks and exact
hypothetical/actual attack agreement for every legal move. Link it against
matching objects using the commands in `range_jumps.md`.

`fixtures/fire-ice.ini` is a playable asymmetric chess-army test variant with
explicit extinction and immunity settings. White has an active-burning Fire
King; Black has a freeze-emitting Ice King. Both resist freezing, and Ice King
resists burning. They can still directly capture each other. Castling is
explicitly disabled; optional baring settings are supplied as comments.

Freezing uses completed-turn semantics for compound moves: source legality is
checked before movement; all legs, burns and promotion resolve; then the final
position determines who is frozen. Passive effects remain active on frozen
pieces, including freeze auras and passive burning. Emitters have no implicit
immunity. The frozen mask is local derived geometry, not extra persisted state.
