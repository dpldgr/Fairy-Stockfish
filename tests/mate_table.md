# Retrograde mate tables

Select a variant and specify every piece, including both Kings:

```text
setoption name UCI_Variant value metal-chess
mate-table pieces {K,B,k} format table
mate-table pieces {K,B,k,n} format table
mate-table pieces {K,B,N,N,k,} memory 8192 format table
```

Uppercase symbols belong to White; lowercase symbols belong to Black. The
braced material list is order-independent and preserves repeated entries:
`{k,N,B,K,N}` selects exactly the same material as `{K,B,N,N,k}`. A trailing
comma and spaces around entries are accepted. Internally, the engine sorts
resolved piece types by army and slot, so aliases and input ordering do not
change the material. Repeated `N` entries represent separate pieces.

Symbols must be configured by the selected variant. Multi-character symbols
use uppercase or lowercase throughout, e.g. `{CK,SB,IN,IN,ck}`. Promoted-form
symbols such as `+N` are accepted when their configured type is eligible.
Each list must contain exactly one ordinary King of each color and three to
five pieces in total. Empty entries inside the list, ambiguous symbols and
mixed-case symbols are errors. `color`, `partner` and `opponent` options cannot
be combined with `pieces`; the list already specifies that information.

`mate-table build pieces ...` and `api mate-table pieces ...` are also accepted.
The original piece/partner/opponent commands remain available as aliases.
The existing three-piece solver supports rectangular 3x3 through 16x16 boards;
the experimental four-piece solver is capped at 81 cells and five-piece at
64 cells. Five-piece jobs allow memory budgets up to 32768 MiB. The movement
and adjudication restrictions below apply to all material sizes. Four/five-piece
captures consult smaller material tables and include their remaining DTM.

The following three-piece details and applet counting conventions describe
K+piece versus K. Four/five-piece statistics give one mate/mated table per army,
with totals counting legal decisive positions rather than applet percentages.

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

Builds and `mate-table stats` print an aligned table and elapsed time, with
every line prefixed by `info string mate-table` by default (`format info-table`):

```text
Statistics
+--------+--------+-----+
|   mate |  mated |  in |
+--------+--------+-----+
|        |     14 |   0 |
|     76 |     18 |   1 |
...
|     76 |    218 |  35 |
+--------+--------+-----+
|  59844 |    King capt |
| 100.0% |  80.7% | tot |
+--------+--------+-----+
Done in 34 ms
```

Select an output format for a build or a cached statistics display:

```text
mate-table piece b format info-table
mate-table piece b format table
mate-table piece b format info
mate-table stats format info
```

- `info-table`: the existing aligned table with `info string mate-table` prefixes.
- `table`: the same output without those prefixes, including build/completion lines.
- `info`: prefixed fields instead of table decorations, one line per distance:

```text
info string mate-table mate 0 mated 14 in 0
info string mate-table mate 76 mated 18 in 1
...
info string mate-table mate 76 mated 218 in 35
info string mate-table king_captures 59844
info string mate-table mate 100.0% mated 80.7% tot
info string mate-table time 34
```

All formats include variant context. `info` also retains the prefixed building
and completion messages. Formats apply to the current command only; omitted
`format` always means `info-table`. `mate-table stats format ...` reuses the
cached result and original elapsed time. The `raw` diagnostic view remains
`mate-table stats raw`; it is separate from the three presentation formats.

This example is Metal Chess's Silver Bishop. `mate` counts strong-to-move
winning positions; `mated` counts weak-to-move losing positions. `in` is the
number of **attacking moves**, rather than plies. Initial checkmates appear
in row zero. Row widths grow with the counts. The footer records the original
build time, including when displaying a cached table.

To match the applet exactly, `King capt` counts distinct three-piece placements
with an immediately capturable nonmoving king, including adjacent kings. These
are not legal engine positions. The `tot` row uses all `N*(N-1)*(N-2)` distinct
placements: `(mate + King capt)/placements` and `mated/placements`. Therefore
these percentages differ from percentages among legal positions. The detailed
legal WDL summaries in `mate-table stats raw` exclude those positions.

`mate-table stats raw` retains the legal WDL summaries and complete per-ply
histogram, including strong-side losses and weak-side wins under nonstandard
stalemate outcomes. **Probe DTM, raw summary maxima and raw histogram distances
remain plies**; for example, 23 plies from the attacking side's turn needs
12 attacking moves.

Allocation counts, memory use and the deterministic WDL/DTM signature appear
only in the raw diagnostics. These distinguish `index_slots` (the allocated
`2*N^3` dense slots), `distinct_states` (`2*N*(N-1)*(N-2)`, without overlapping
pieces), and `legal_states` (both legal side-to-move summaries combined). An
8x8 Silver Bishop table has 524,288 slots, 499,968 distinct-square states and
414,084 legal states. None of these implementation counts appear in the normal
statistics table or completion line.

```text
mate-table stats
mate-table stats raw
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
