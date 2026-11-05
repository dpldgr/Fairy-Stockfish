# Initial boards through 36×36

Native builds now accept up to 36 files, 48 ranks and 1,296 cells in total.
Use separate executables for each geometry. Examples, from `src/`:

```sh
make -j2 ARCH=x86-64 board_files=25 board_ranks=25 piece_slots=512 gating=no build
# Clean before changing dimensions or use separate build directories.
make clean
make -j2 ARCH=x86-64 board_files=36 board_ranks=36 piece_slots=512 gating=no build
```

25×25 uses ten 64-bit bitboard words and ten-bit square fields. 36×36 uses
21 words and eleven-bit square fields. Existing 64-bit move/TT storage can
represent four-square routes and promotion in both profiles. Multiword builds
retain their directional-ray slider backend; no huge occupancy lookup tables
are introduced.

## Compile-time resource policy

Through 640 compiled cells, continuation-history allocation, initialization,
sentinels, updates, move ordering, pruning and reduction contributions remain
unchanged. Existing profiles through 384 cells also retain their bitboard/move
storage, score types, dense capture histories and Lion caches.

Above 384 cells:

- Classical evaluation uses 32-bit middle/endgame components in a 64-bit Score,
  with wider interpolation and a clamp before returning to search value storage.
  The 25×25 profile needs this for universal-leaper mobility and large material
  imbalances; intermediate products can exceed 16 bits before division.
- Capture history stores exact destination rows per attacker/victim pair,
  allocating a row on its first update. Untouched reads return the fill value
  without allocation. Clearing releases the rows; no statistics are merged or
  evicted. The original dense history remains through 384 cells.
- Lion paths combine per-colour/type modality masks with a per-square geometry
  mask. This gives the same paths as the old dense cache, reducing its size
  independently of how many piece slots are compiled in.
- Quiescence polls the search limits and stop flag, as main search already does.
  Large capture trees must respect node/time limits even before the first
  iteration completes. Interrupted children unwind without updating PVs or
  storing incomplete results in the transposition table.
- Recursive search/perft state is heap allocated. At 512 piece slots the
  check-square arrays make each state too large for a deep search on an 8 MiB
  worker stack, including the 25×25 profile.

Above 640 cells:

- Continuation histories are absent from `Thread`. Their ordering/reduction
  contributions and updates are omitted. Continuation pruning and the futility
  branch that depends on a continuation-history veto are disabled, including
  the continuation pruning in quiescence. Other histories remain available.
- The speculative cuckoo cycle accelerator and its initialization are disabled.
  Normal position-key repetition adjudication is retained.
- Position and evaluation storage still consume substantial memory; this is
  an initial desktop build.
- NNUE and its unsupported feature-metadata construction are disabled.

New geometries above the previous 384-cell limit also use larger heap-backed
move-picker buffers even with the default 64-slot catalogue. Existing catalogue
capacity options still control the piece/drop bound. The buffers and capture
histories remain deliberately generous and are candidates for later work.

At 25×25 / 512 slots, the worker object is about 779 MiB, down from 1,400 MiB;
763 MiB is the unchanged continuation history. A comparable portable one-worker
Tai load/perft run fell from 2.53 GiB to 1.37 GiB peak RSS. Native BMI2 also
passed loading, generation, evaluation and bounded Tai searches under a 2 GiB
Linux address-space limit. Node/time/stop limits are checked in quiescence,
but move generation and legality probes can still overshoot a node request.

At 36×36 and 512 slots, continuation-history removal saves about 3.20 GiB per
worker. Lazy capture history removes the former 1.27 GiB startup allocation:
the worker object is now about 45 MiB, with approximately 2.5 KiB added for each
updated attacker/victim pair. Search memory can grow as more pairs are updated.
Dense global attack and line/between tables are retained initially. A native
BMI2 one-worker Taikyoku load/perft run measured about 2.28 GiB peak RSS; the
same previous build measured 4.71 GiB. The new build also passed that run under
a 3 GiB process address-space limit, where the old build failed at startup
under 4 GiB. These are Linux measurements, not a Windows RAM guarantee.
Search strength and evaluation tuning on armies of hundreds of pieces are
separate work. Supporting the board does not implement Taikyoku's remaining
ray-clearing or disputed piece abilities.

## Validation

Run layout/encoding checks across capacities and the 384/385 and 640/648-cell boundaries:

```sh
python3 tests/piece_slots_matrix.py
```

Use the matching executable for full-board coordinate/ray/promotion/compound
move/perft-undo and depth-4 search tests:

```sh
STOCKFISH=/path/to/25x25/stockfish BOARD_SIZE=25 python3 tests/large_boards.py
STOCKFISH=/path/to/36x36/stockfish BOARD_SIZE=36 python3 tests/large_boards.py
```

`large_board_state.cpp` links against matching engine object files except
`main.o`. Use the same dimensions, piece capacity, gating, architecture and debug
defines as the executable. It verifies make/undo against rebuilt positions for
normal, promoting, Lion, Lion Dog, hook and triple-area moves near the far board
corner, repetition adjudication, and (above 384 cells) a material imbalance that
exceeds the old score-component range. It also checks factored Lion masks against
an independent coordinate oracle for both colours, asymmetric modalities and
smaller embedded boards. The encoding matrix compares lazy capture-history
updates with the original stats entries, including clearing and reads that
must not allocate. For an x86-64 portable 36×36 debug build:

```sh
g++ -std=c++17 -O1 -g -pthread -DIS_64BIT -DBOARD_FILES=36 -DBOARD_RANKS=36 \
  -DPIECE_TYPE_CAPACITY=512 -DENABLE_GATING=0 tests/large_board_state.cpp \
  $(find /path/to/build/src -name '*.o' ! -name main.o) -o /path/to/state-check
/path/to/state-check
```

Also run the existing variant checks and relevant regression tests on 8×8,
16×16 BMI2 and portable 19×19 builds. Compare fixed-depth single-thread search
scores, PVs, node counts and best moves with the unchanged source baseline;
elapsed times and NPS alone do not establish preserved behaviour.
