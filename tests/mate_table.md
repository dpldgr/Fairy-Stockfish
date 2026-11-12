# Retrograde mate tables

Select a variant and specify every piece, including both Kings:

```text
setoption name UCI_Variant value metal-chess
mate-table pieces {K,k} format table
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
Each list must contain exactly one ordinary King of each color and two to
five pieces in total. Empty entries inside the list, ambiguous symbols and
mixed-case symbols are errors. `color`, `partner` and `opponent` options cannot
be combined with `pieces`; the list already specifies that information.

`mate-table build pieces ...` and `api mate-table pieces ...` are also accepted.
The original piece/partner/opponent commands remain available as aliases.
The two- and three-piece solvers support rectangular 3x3 through 16x16 boards;
the experimental four-piece solver is capped at 81 cells and five-piece at
64 cells. Five-piece jobs allow memory budgets up to 32768 MiB. The movement
and adjudication restrictions below apply to all material sizes. Four/five-piece
captures consult smaller material tables and include their remaining DTM.

`{K,k}` enumerates bare ordinary Kings: every legal nonoverlapping,
nonadjacent placement is a draw. On 8x8 this gives **7,224 states**, including
both sides to move (3,612 each). Generation needs no retrograde propagation or
result array. Statistics report legal/draw counts, and cached probes return a
legal drawing move with no DTM field. The same variant restrictions below
apply, including the exclusion of baring/extinction and other winning rules.

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
STOCKFISH=/path/to/stockfish python3 tests/mate_table_two.py -v
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

## Binary training-data export

Add `export <filename>` to append every legal position from the requested
material table to a binary training file:

```text
mate-table pieces {K,B,k} export silver-bishop.bin
mate-table pieces {K,k} export metal-training.bin
mate-table pieces {K,R,k} export gold-rook.bin entrysize 72
mate-table pieces {K,N,k} export "C:/training/iron knight.bin" entrysize 8
mate-table pieces {K,B,N,N,k} memory 8192 export metal-five.bin entrysize 8
```

`entrysize` accepts every integer **7 through 144**; the default remains **72**. It requires `export`, and
applies only to that command. Quoted paths preserve Windows backslashes.
Omitting export preserves the existing table calculation and output. All
formats are headerless, fixed-size, little-endian records; the variant-specific
reader supplies the schema. **Do not mix entry sizes or variant schemas in one
file.** File-size alignment is checked, but a headerless file cannot identify
its schema. Concurrent writers to the same path are not supported.

Appending `{K,k}` uses the selected variant's full piece-index schema, just as
larger materials do. Its records contain score 0 and result 0; draws have no
DTM. Compact records use support count 0 and zero unused support words. The
8x8 output sizes are **520,128 bytes** at entrysize 72 and **57,792 bytes** at
entrysize 8. The existing 8-byte and 72-byte layouts are unchanged. The compact codec also accepts
zero configured non-king identities for a variant containing only Kings.

Export starts after successful calculation (and the four/five-piece verification).
It includes legal checks, checkmates and stalemates, skips invalid array cells,
and emits interchangeable-piece placements only once. Capture-dependency tables
are not exported automatically. Both sides to move are included. Repeating a
command appends another copy; there is no deduplication against existing files.
Output is buffered, with bounded additional memory, and is independent of search.

Score and result are from the side-to-move perspective:

- Win in d **plies**: score `32000-d`, result `+1`.
- Loss in d plies: score `-32000+d`, result `-1`.
- Draw: score `0`, result `0`.

Already terminal decisive positions have d=0. DTM values >=32000 are rejected
rather than silently changing the sign of the score. These are the existing
mate-table results: move-count draw rules are ignored. All formats reset
history and carry no castling or en-passant rights.

An export reports `export complete records N entrysize S bytes B time T file P`
before the usual `complete` message. Progress is reported during long exports.
`stop` during export retains a valid prefix of complete records and reports
`export cancelled`. The completed table remains cached if export fails or is
cancelled after calculation. Write errors attempt to remove any incomplete
trailing record while preserving the existing file prefix, and report failure
to restore that boundary if necessary. File/schema errors are checked before
starting the expensive table calculation.

### Standard 72-byte format

Compatible with `variant-nnue-tools`' default `PackedSfenValue` and the matching
variant NNUE training DLL:

| Offset | Bytes | Value |
|---:|---:|---|
| 0 | 64 | Upstream packed position |
| 64 | 2 | Signed score |
| 66 | 2 | Zero move (`MOVE_NONE`) |
| 68 | 2 | Placeholder game ply 1 |
| 70 | 1 | Signed result (-1, 0, +1) |
| 71 | 1 | Zero padding |

The packed position has fullmove 1, rule50 0 and empty hands. Zero move is
unused by the current value-training loader, including for terminal positions;
tools that require a PV move need a separate adaptation. Use the ordinary
512-bit/default data-size DLL, not the 136-byte `largedata` format.

This encoding requires at most 128 board cells, the variant's unique NNUE King,
at most 16 configured non-king piece identities, and a payload that fits 512
bits. The upstream engine tools may impose narrower build geometry. Dense type
indices enumerate every configured non-king type in increasing engine-slot
order, followed by King; material selection does not change that ordering.
Raw engine slot numbers, build board stride and piece-slot capacity are not
written. Multi-character symbols therefore need no special record notation.

### Original compact 8-byte profile

For at most 64 board cells and eight configured non-king identities, the 8-byte
layout remains byte identical and supports three pieces in addition to the Kings. It requires an
adapted DLL. `src/mate_table_bin.h` is a standalone C++17 encoder/decoder with
no engine dependencies, suitable for inclusion in that DLL. There is no
automatic detection of record size; select 8-byte records in the reader too.

The little-endian 64-bit word contains:

| Bits (least significant = 0) | Value |
|---|---|
| 0–5 | White King square |
| 6–11 | Black King square |
| 12–21 | Support 0 |
| 22–31 | Support 1 |
| 32–41 | Support 2 |
| 42 | Side to move (White 0, Black 1) |
| 43–44 | Number of supports (0–3) |
| 45–60 | Two's-complement signed score |
| 61–62 | Result + 1 (loss 0, draw 1, win 2; 3 invalid) |
| 63 | Reserved zero |

Each support uses six square bits, three dense type-index bits and one color
bit, in that order from least significant to most significant. Unused support
words are zero. Squares are rank-major within the **variant**, a1=0 and
`square=rank*files+file`, independent of the executable's build dimensions.
Supports are ordered by color, type index and square. Types use the same
configured non-king ordering as the 72-byte format. For the supplied Metal
Chess definition this is `p,q,r,b,n`, not orthodox `p,n,b,r,q`.

Decoder integration:

```cpp
#include "mate_table_bin.h"

Stockfish::MateTableBin::Entry entry;
if (!Stockfish::MateTableBin::decode8(bytes, entry, 64, 5))
    /* reject malformed record */;
// Place entry.kings as White/Black Kings. Map entry.pieces[i].type through
// the DLL's configured non-king index table. Use entry.turn, entry.score and
// entry.result for the existing training targets. No move or ply is stored.
```

The decoder checks field ranges, overlapping squares, unused words and reserved
bits; variant move legality comes from the generator. It does not change the
trainer's loss function. Near-mate scores saturate the current sigmoid loss,
so storing DTM exactly does not itself make the trainer learn mate distance.

### Variable-width compact records (7..144 bytes, excluding 72)

`src/compact_training_record.h` provides a standalone encoder/decoder shared
with the PRP Trainer. The width, variant geometry and dense non-King type order
are external schema. Width **72 is reserved for PackedSfen**, as described above.
Use `--record-bytes N` in the matching Trainer, for both sequential and PRP reads.
No additional DLL is introduced, but the existing library must be rebuilt.

```text
mate-table pieces {K,N,k} export iron-knight-7.bin entrysize 7
mate-table pieces {K,B,N,k} export four-piece-9.bin entrysize 9
```

The highest bit selects sparse (0) or bitmap (1) placement encoding. All fields
are little-endian, including bit fields. Unused fields/padding must be zero.

For sparse records, let S=max(6,ceil(log2(cells))) and
T=max(3,ceil(log2(nonKingTypes))). Choose the largest support capacity C fitting
`2*S + C*(S+T+1) + ceil(log2(C+1)) + 20 <= 8*entrysize`. Fields are: two King
squares (S bits each), C support slots (S square bits, T type bits, one color
bit), side to move (one bit), support count (ceil(log2(C+1)) bits), signed score
(16 bits), WDL+1 (two bits), zero padding and the zero mode bit. Minimum field
widths retain compatibility with the original 8-byte profile above.

If the material exceeds sparse capacity, bitmap mode is used when it fits:
`cells + (supports+2)*(ceil(log2(nonKingTypes+1))+1) + 20 <= 8*entrysize`.
Fields are: occupancy bitmap (one bit per cell), then type/color for each
occupied square in increasing square order, side to move, score, WDL+1, zero
padding and mode bit 1. King uses dense type code `nonKingTypes`; exactly one
King of each color is required. The occupancy count supplies the piece count.

Seven bytes hold all 2–4-piece Metal Chess positions on 8x8. On a 4x3 chess
schema, bitmap encoding also fits six total pieces in seven bytes; the table
solver itself still supports only two through five pieces. Other compact widths
can accommodate larger geometry/type schemas, subject to available bits. There
is no longer a global 64-cell/eight-type limit for compact exports. The requested
material's capacity is checked before opening the destination or calculating a
table. Too-small widths fail without appending data.

The exporter writes canonical support order; bitmap readers recover square order
and may reorder it. No move, ply, rights or history is stored. Decoder defaults
match the original compact profile. Record widths must match throughout a file.
Converting an existing file requires decoding/re-encoding, not truncation or
padding. `src/mate_table_bin.h` remains a decoder for the original 8-byte profile;
use `compact_training_record.h` for the expanded schemas and other widths.

Additional checks from the repository root:

```sh
g++ -std=c++17 -O2 tests/mate_table_bin.cpp -o /tmp/mate-table-codec
/tmp/mate-table-codec
STOCKFISH=/path/to/stockfish python3 tests/mate_table_export.py -v
BOARD_SIZE=16 STOCKFISH=/path/to/16x16-stockfish python3 tests/mate_table_export.py -v
```
