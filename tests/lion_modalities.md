# Lion modalities and promotion burning

Lion masks now use parentheses. The former `symbol:mask` syntax is rejected:

```ini
lionMovePieces = ln(FFFFFFFFFFFFFFFF) fe(m:AA00AA00AA00AA00,c:AA00AA00AA00AA00) ht(c:0804020180402010)
```

A bare mask enables both modalities. `m:` enables complete routes with no direct
captures; `c:` enables routes with at least one direct capture, on either or
both legs. Capturing on the first leg and returning to an empty origin is a
capture, so capture-only igui works. Burning does not change route modality.
Ordinary single moves remain entirely in the piece's Betza definition.

Each mask has exactly 16 hexadecimal digits, case-insensitive. Parentheses and
colons make qualifiers unambiguous even when a mask begins with lowercase c.
Whitespace is allowed around the symbol, mask and separators. Qualified modes
may appear in either order. Omitted modes are empty. Duplicate pieces, duplicate
modes, mixed bare/qualified masks and malformed entries reject the variant.
Each mentioned piece replaces its whole inherited Lion definition; other pieces
inherit unchanged. Lion Dog retains its existing 12-digit colon syntax and
both-mode behaviour. Shared Lion/Lion-Dog paths must agree in both modalities.

The engine reuses `MoveModality`, keeps the existing per-square geometry cache
as the union of both masks and adds only small per-type modality masks.
Neither move encoding nor Position, StateInfo, ExtMove or TTEntry storage changes.
Temporary hypothetical attack views additionally retain promotion provenance.

## Burning on promotion

```ini
burnActivePieceTypes = {fd}
burnPassivePieceTypes = {fd}
burnOnPromotePieces = {wb}
```

`burnOnPromotePieces` names the original piece type. It defaults to empty and
replaces an inherited set when specified (`{}` or `-` clears it). Every listed
active source must have a possible promotion target in `burnActivePieceTypes`;
otherwise variant registration fails. With multiple promotion choices, only
choosing an active-burning result grants the additional burn. Actual promotion
eligibility and target limits still apply. Already-promoted forms cannot promote
again through this option.

Passive burn retains priority and uses the original mover's immunity. A piece
killed on arrival cannot promote or burn back. If it survives, its existing
active burn, or the selected promotion's bonus burn, removes adjacent enemies
at the final destination, respecting burn immunity. Intermediate squares never
burn. Burned victims do not enter a hand or trigger capture-promotion policies.

These rules apply to normal, pawn-choice and multi-leg promotions. Direct
attack/check queries and hypothetical positions consider whether a promotion
burn is actually available, including victim provenance and promotion limits.

[tenjiku-shogi.ini](fixtures/tenjiku-shogi.ini) is a complete reference config
with HT capture-only igui and WB promotion burning. It requires at least 16x16
and 128 piece slots. Its fourfold-draw policy remains a simplification of the
article's conditional pursuit/check/pass repetition discussion.

## Regression commands

```sh
STOCKFISH=./src/stockfish BOARD_SIZE=16 python3 tests/lion_modalities.py -v
STOCKFISH=./src/stockfish BOARD_SIZE=16 python3 tests/tenjiku_burn_area.py -v
```

Use BOARD_SIZE=8 for the portable small build, or BOARD_SIZE=19 PIECE_SLOTS=512
for the large portable build. New cases include an independent randomized
whole-route oracle, both colours, every capture placement, igui/pass, ordinary
HT rays, inheritance, shared Dog conflicts, invalid syntax, passive precedence,
immunity, promotion choice/policy/limit, promoted victim state and path/area
promotion burning. `range_jump_state.cpp` additionally checks hypothetical attacks
against actual make/undo, fresh positions, hashes, pockets and provenance on all
three builds; see [range_jumps.md](range_jumps.md) for compilation commands.
