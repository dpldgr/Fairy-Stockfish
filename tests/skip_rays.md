# Initial ray skips

Custom Betza definitions accept `j<count><R|B|Q><range>`:

| Component | Meaning |
| --- | --- |
| `jR` | Skip the first square; slide from the second onward. |
| `j2R5` | Skip two squares; allow destinations at distances 3–5 from the origin. |
| `cj2B` | Capture-only diagonal skip of two squares. |
| `mjQ4` | Quiet-only queen rays, at distances 2–4. |
| `jfbR` | Forward/backward rook rays, skipping one square. |
| `j0R` | Ordinary rook movement. |

Omitted skip counts default to one. An omitted range, or range zero, means
unlimited. Counts and ranges accept multiple decimal digits. Direction and
`c`/`m` qualifiers use the existing Betza rules, relative to the moving colour;
for example, `cmj2R` permits both captures and quiet moves.

The skipped prefix ignores friendly and enemy pieces and leaves them intact.
It provides no landing or capturing squares. Walls remain opaque throughout
the ray. Beyond the prefix, normal sliding applies: stop at the first piece,
capturing it only when permitted. Mobility regions and capture restrictions
still apply. These are ordinary from/to moves and require no new encoding.

The Heavenly Tetrarch's ray component is `jBjfbRjrlR3`. Its adjacent igui
remains a separate `lionMovePieces` configuration. `j` cannot combine with
`p`, `g`, or `n`, or apply to other atoms. Variants using it are omitted from
XBoard's advertised list because that protocol cannot describe these moves.
The engine's existing initial-move modifier supports quiet moves only.

The implementation precomputes skipped-prefix and destination masks, then
reuses existing rook/bishop attack lookups with prefix pieces removed from
occupancy. Ordinary variants allocate no skip profiles. Attacks on a target
are verified from the source, so ignored prefixes remain beside the attacker
in checks, evasions, castling, and pin detection.

Run the independent square-walk oracle and integration cases:

```sh
STOCKFISH=./src/stockfish BOARD_SIZE=16 python3 tests/skip_rays.py -v
```

Use `BOARD_SIZE=19` for the multi-digit count/range case. Tests cover both
colours, directions, modalities, overlapping components, walls, mobility,
prohibited captures, igui, promotions, drops, burn, freeze, king safety,
castling and en passant. Invalid syntax must fail variant registration.

`range_jump_state.cpp` also exercises skipped rays, comparing hypothetical
attacks with the position after every legal move, FEN reloads, hashes,
promotion provenance and exact undo. Dedicated pin cases distinguish ignored
prefix pieces from actual blockers. See [range_jumps.md](range_jumps.md) for
matching-build compilation commands.
