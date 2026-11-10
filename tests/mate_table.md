# K+piece versus K mate tables

Select a variant, then select the **configured symbol** of the supporting piece:

```text
setoption name UCI_Variant value metal-chess
mate-table piece r
```

Wait for `info string mate-table complete ...`, then run `mate-table piece b`
or `mate-table piece n` for the next table.
`api mate-table ...` is an alias; `mate-table build piece r` and `mate-table r`
also build a table. Multi-character and promoted-form symbols are accepted when
they identify an eligible nonroyal slot.

The table enumerates all placements of an ordinary king and the selected piece
against a bare ordinary king. It uses the selected variant's board dimensions,
piece movements (including asymmetric and separate quiet/capture moves), the
supporting piece's mobility region, and stalemate result. It does not use the
variant's starting army. Castling rights, promotions and move-count clocks are
not part of the table. Cycles unresolved by retrograde propagation are draws.

The default supporting army is White. To use Black's movement orientation:

```text
mate-table piece b color black
```

Output includes legal positions, wins/draws/losses for each side to move,
initial checkmates, maximum distance to termination, a DTM histogram, build
time, table bytes and a deterministic WDL/DTM signature. **Distances are plies**;
for example, a forced mate requiring 23 plies from the attacking side's turn
needs 12 attacking moves. Counts exclude overlapping pieces, adjacent kings
and positions where the nonmoving king is already in check. The applet's
display also counts immediate king-capture placements, so its raw percentage
denominator differs; its legal WDL/DTM results agree.

```text
mate-table stats
position fen 7k/8/8/8/8/8/8/KR6 w - - 0 1
mate-table probe
mate-table clear
mate-table status
```

`probe` requires exactly the table's material, selected color and variant,
without castling rights or walls. It reports the side-to-move result, exact
distance for wins/losses, and an optimal legal move. Winning moves minimize
DTM; losing moves maximize it. Draws select a drawing continuation. Already
terminal positions return `bestmove 0000`. Capturing an unprotected supporting
piece is a drawing exit to ordinary K/K.

Only one table is retained. Switching variants makes an old table unavailable
until returning to its original variant or rebuilding; `clear` frees it.
Builds run asynchronously. `isready` and `mate-table status` remain responsive;
`stop`/`quit`, a new build, or other commands that could alter shared variant
tables stop and join the worker. A build also stops outstanding normal/TDS
search before reading those tables. No calculations or lookups are added to
ordinary search, evaluation or insufficient-material adjudication.

Current scope: rectangular 3x3 through 16x16 boards, ordinary checkmating
kings, and fixed nonroyal leapers/riders. Unsupported variants/pieces produce
an explicit error: extinction/baring or additional winning rules, promotions,
drops/gating, walls, nonstandard king movement, hoppers/skipped rays,
multi-leg moves, capture effects, trading/prohibited-capture restrictions and
decisive repetition rules are excluded from this version. Extinction is a
separate planned extension. The algorithm follows the Checkmating Applet's
retrograde principle; explicit turns and 32-bit DTM avoid its byte-distance
overflow limitation.

The estimated working-memory budget defaults to 512 MiB and can be specified
as `mate-table piece r memory 128` (range 1–4096 MiB). An 8x8 table retains
4 MiB of nodes and uses roughly 2 MiB for the temporary queue, plus geometry
and metadata. The 16x16 upper bound uses 256 MiB of nodes and a 128 MiB queue.
Budgets are checked before those allocations, which also handle allocation
failure. Metadata is included through an allowance in the estimate.

Run tests from the repository root:

```sh
STOCKFISH=/path/to/stockfish python3 tests/mate_table.py -v
BOARD_SIZE=16 STOCKFISH=/path/to/16x16-stockfish python3 tests/mate_table.py -v
```

The reference fixture was generated independently from the inline JavaScript at
<https://www.chessvariants.com/rules/checkmating-applet>. It contains complete
canonical WDL/DTM signatures, summary counts, distance histograms and sample
positions for Metal Chess's RfF/BfW/NfK and orthodox R/B/N. Each signature covers
all 524,288 indexed placement/turn records, including invalid records. Tests
also compare probe choices to native legal moves, check DTM-decreasing replies,
Black orientation, multi-character symbols, modality, stalemate rules, cache
lifetime, cancellation, errors, command-line completion and subsequent search.

The large-build run also checks a 14x14 K+nonroyal-K/K table with 15,059,072
indexed records, responsive `isready`, and distances through 124 plies.
