# Transform on capture

```ini
transformOnCapturePieces = {tk,bs,dv:tk,ds:bs}
transformOnCaptureImmunePieces = {k,e}
transformOnCapturePolicy = choose
```

Bare entries map a victim to itself. Explicit entries map a victim to a result.
The surviving capturer becomes that result in its own colour after completing
the route, replacing ordinary promotion. Immunity uses the original mover's
actual type. Direct victims are considered in chronological capture order;
screens and burn/blast bycatch are excluded. Revisited squares are not captured
again. `first` and `last` select the first/last qualifying victim; `choose`
(default) offers each distinct result once.

Mappings and immunity sets inherit when absent, replace the parent value when
specified, and accept `{}` or `-` to clear. Existing promotion limits filter
results; first/last never fall back to another victim. Same-type replacement
does not increase the count and remains possible at the limit.

Replacements use existing target suffixes in UCI/USI and `=target` in SAN.
Compound moves retain their full route. FEN stores the resulting piece as
`target~`, without an original base mapping. This preserves promoted-victim
classification on reload, permits later capture transformations, and follows
existing variable-promotion capture-to-hand semantics. It does not create a
reverse demotion mapping to the original capturer.

The native checkmate King is not a supported result. Use an extinction royal
with commoner movement instead. Runtime gating, wall placement and enclosure
combinations are rejected. Static walls are supported. These variants use
classical evaluation and do not advertise XBoard or probe existing tablebases
or specialised endgames.

## Protocol and move-generation tests

Run from `src/`, selecting a binary built with the indicated board/slot capacity:

```sh
STOCKFISH=./stockfish python3 ../tests/transform_on_capture.py
BOARD_SIZE=16 STOCKFISH=./stockfish python3 ../tests/transform_on_capture.py
BOARD_SIZE=19 PIECE_SLOTS=512 STOCKFISH=./stockfish python3 ../tests/transform_on_capture.py
```

The suite covers mapping/inheritance, both colours, normal-promotion precedence,
immunity, first/last/choose, duplicate results, capture order and revisits,
already-promoted sources, igui, hooks, generic double moves, Lion Dog routes,
area routes, screened range jumps, promotion limits, prohibited captures,
trading rules, en passant, burn/freeze, atomic capture, pawn results, high IDs,
notation, undo and shallow search. Capacity-dependent cases skip smaller builds.

## Internal state tests

`transform_capture_state.cpp` checks every legal move in the supplied positions:
UCI/USI round trips, SAN result suffixes, TT move preservation, pseudo-legality,
post-move attack overlays, check detection, promotion provenance, material,
pawn/full hashes, FEN reload, and exact undo. It also checks capture-to-hand with
single-character pocket symbols; the existing multi-character pocket FEN parser
limitation is outside this change.

Example for matching 8x8 `ARCH=x86-64 debug=yes nnue=no` engine objects, from
`src/` using Bash:

```sh
STOCKFISH=./stockfish python3 ../tests/transform_on_capture.py --fixture /tmp/transform.ini
objects=()
for object in ./*.o; do
    if [[ "$object" != ./main.o ]]; then objects+=("$object"); fi
done
g++ -std=c++17 -O1 -g -pthread -DIS_64BIT -DUSE_SSE2 \
    -DBOARD_FILES=8 -DBOARD_RANKS=8 -DPIECE_TYPE_CAPACITY=64 -DENABLE_GATING=1 \
    ../tests/transform_capture_state.cpp "${objects[@]}" -o /tmp/transform-state
/tmp/transform-state /tmp/transform.ini
```

Use the matching board, piece-slot, gating, architecture and precomputed-magic
defines when linking against other builds. Set `BOARD_SIZE` and `PIECE_SLOTS`
when generating their fixtures, too. Sanitized engine objects require the same
sanitizer flags on the harness link command.
