# Block-policy slider intervals

```ini
piece = x:Q[3..8]     # Quiet moves and captures at distances 3–8 inclusive
piece = y:mR[3]       # Quiet slide of exactly 3 squares
piece = z:cfB[2..5]   # Capture-only forward diagonals, distances 2–5
```

`Q[3]` equals `Q[3..3]`. Existing `Q3` still allows distances 1–3;
`Q`, `R`, `B` and their existing numeric suffixes keep their interpretation.
Directional qualifiers and the existing initial-move modifier work normally.
Every intervening piece or wall blocks, including before the minimum distance.
There are no captures of intermediate pieces. Captures occur only at the final
square, and ordinary promotion, hands, immunity and other rules apply.

Bounds must be positive integers not exceeding INT_MAX, in ascending order.
Off-board distances produce no destinations. Malformed bounds, sets, open-ended
intervals and combinations with j/p/g/n on the same atom are rejected. Separate
atoms can combine those moves with interval sliders, for example R[3..5]cpR.
Repeated/overlapping terms give the union of their moves without duplicates.

Run the square-walk and integration tests:

```sh
STOCKFISH=/path/to/stockfish python3 tests/slider_intervals.py -v
BOARD_SIZE=19 STOCKFISH=/path/to/stockfish \
    python3 tests/slider_intervals.py IntervalSliders.test_large_board -v
```

The suite checks both colours, directional/modal terms, empty and blocked
prefixes, upper/lower boundaries, exact-distance shorthand, legacy suffixes,
combined movement masks, walls, freezing, burning, mobility, prohibited captures,
royal check/evasions/pins/castling, promotion and immobility, initial moves,
invalid syntax, and multiword board geometry. The independent oracle walks
rays using square coordinates.

The C++ range_jump_state.cpp harness additionally checks all compiled squares
and every single-blocker position, fast-path rider flags, material estimates,
fresh state/hash reconstruction, check prediction, notation and exact undo.
Build/link it as described in range_jumps.md.

Only initialization metadata and precomputed masks are added. Simple block
intervals use the existing ordinary slider lookup and destination mask. Mixed
occupancy-dependent terms use the existing special-rider dispatcher and separate
masks. The blocker policy is separate initialization metadata, compiled into
prefix occupancy masks; no configurable policy option is exposed. Existing
attack helpers, magic/PEXT tables, move encoding and Position/StateInfo fields
are unchanged.
