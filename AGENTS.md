# Fairy-Stockfish Agent Guide

## Purpose

This file is a working guide for AI coding agents contributing to Fairy-Stockfish. It should capture durable repo-specific workflow, build, testing, and performance expectations that help agents avoid repeating known mistakes.

Fairy-Stockfish is a C++17 chess-variant engine derived from Stockfish. It supports many protocols and variant families, including orthodox chess, regional variants, shogi-family variants, large boards, and bindings for Python and JavaScript.

## Scope and precedence

- This root `AGENTS.md` applies to the whole repository.
- More deeply nested `AGENTS.md` files, if added later, should describe only the subtree they live in and take precedence for that subtree.
- Direct user/developer instructions in the conversation take precedence over this file.
- Keep this file durable. Do not add one-off PR notes, temporary TODOs, or branch-specific assumptions.

## Repository layout

- `src/`: core C++ engine, Makefile, protocols, move generation, search, evaluation, variant parsing, and bindings source.
- `src/variants.ini`: variant configuration examples and documentation of variant properties.
- `tests/`: shell-based regression, protocol, perft, reproducibility, signature, and JavaScript binding tests.
- `.github/workflows/`: CI definitions for engine, release, Python wheels, and JavaScript bindings.
- `setup.py`: Python package build configuration.

## Command location

Unless a command explicitly targets the repository root, run engine build/test commands from `src/` or use `make -C src ...` from the repository root.

Examples:

```bash
make -C src -j2 ARCH=x86-64 build
./src/stockfish bench
```

or:

```bash
cd src
make -j2 ARCH=x86-64 build
./stockfish bench
```

## Build-system guidance

### Common builds

```bash
# Standard release build
make -C src -j2 ARCH=x86-64 build

# Debug build
make -C src -j2 ARCH=x86-64 debug=yes build

# Existing largeboard/all-variant style build
make -C src -j2 ARCH=x86-64 largeboards=yes all=yes build

# Fast PEXT/BMI2 build, used for known-fast PEXT targets
make -C src -j2 ARCH=x86-64-bmi2 build
```

### Architecture and PEXT policy

- Treat PEXT as a build/architecture feature, not as an automatic consequence of board size.
- `ARCH=x86-64-bmi2` is the fast hardware-PEXT target.
- Do not assume all CPUs with the PEXT instruction should use a PEXT build; some microarchitectures have slow PEXT.
- Non-PEXT builds must remain possible for portable targets such as WebAssembly, mobile, and non-BMI2 x86.
- Do not add or remove Makefile feature flags without checking how they interact with `ARCH`, `pext`, board size, `PRECOMPUTED_MAGICS`, and JavaScript/WebAssembly builds.

### Board-size policy

The engine has historically used separate compile-time board dimensions. Prefer compile-time board-size-specific executables over runtime-remapping board geometry unless explicitly asked otherwise.

When changing board representation, test representative capacities rather than only the target that motivated the change:

```bash
# 8x8 baseline
make -C src clean && make -C src -j2 ARCH=x86-64 build

# 16x16 fast PEXT/BMI2 baseline
make -C src clean && make -C src -j2 ARCH=x86-64-bmi2 board_files=16 board_ranks=16 build

# Example non-PEXT multiword build
make -C src clean && make -C src -j2 ARCH=x86-64 board_files=12 board_ranks=16 build

# Example maximum-capacity build if supported by the branch
make -C src clean && make -C src -j2 ARCH=x86-64 board_files=32 board_ranks=12 build
```

## Testing expectations

### Basic checks

For most engine changes, run:

```bash
./stockfish bench
./stockfish check variants.ini
```

From the repository root, use:

```bash
./src/stockfish bench
./src/stockfish check src/variants.ini
```

### Full or targeted test suite

The test scripts live under `tests/` and are usually run from `src/`:

```bash
../tests/regression.sh
../tests/reprosearch.sh
../tests/signature.sh
../tests/protocol.sh
../tests/perft.sh all
../tests/perft.sh chess
../tests/perft.sh largeboard
```

Some tests require `expect`. If `expect` is unavailable and cannot be installed, report that explicitly as an environment limitation rather than silently skipping the tests.

### Test selection by change type

- **Move generation, attacks, piece movement, or board geometry:** run relevant builds plus `./stockfish check variants.ini`; run relevant perft tests when available.
- **Bitboard, move encoding, square encoding, or TT layout:** test 8x8, a 16x16 BMI2 build, and at least one non-PEXT multiword/large-board build when supported.
- **Variant parser/config changes:** run `./stockfish check variants.ini` in a build that can represent the relevant board sizes.
- **Protocol changes:** run protocol tests if `expect` is available.
- **JavaScript binding changes:** consult `tests/js/README.md` and use `make -f src/Makefile_js build` or the documented JS test flow.
- **Python binding changes:** build or install through `setup.py` as appropriate.

## Performance-sensitive areas

The following files and concepts are hot or layout-sensitive. Treat changes here as performance-sensitive even when correctness tests pass:

- `src/types.h`: `Bitboard`, `Square`, `Move`, `MoveType`, `MoveStorage`, `SQUARE_BITS`, board-size constants, piece/square encoding.
- `src/bitboard.h` and `src/bitboard.cpp`: attack generation, `popcount`, `lsb`, `msb`, PEXT/magic/ray paths, attack tables.
- `src/movegen.cpp` and `src/movegen.h`: move generation and `ExtMove` layout.
- `src/movepick.cpp`: move ordering and move-list traversal.
- `src/search.cpp`: search hot path and node-count-sensitive logic.
- `src/tt.h` and `src/tt.cpp`: TT entry layout, cluster size, replacement behavior, move storage.
- `src/position.cpp` and `src/position.h`: board state, occupancy, repetition/cuckoo tables, move do/undo.

Before changing these areas, consider:

- Does this alter object size, cache-line layout, or move-list size?
- Does this change generated code for 8x8 or 16x16 builds?
- Does this preserve fast PEXT builds and non-PEXT portable builds?
- Does this change node counts, or only NPS?
- Is a performance comparison needed against the prior implementation?

## Large-board and bitboard guidance

- Keep 8x8 and existing largeboard performance in mind when adding support for larger boards.
- Do not widen hot structures globally if only larger board sizes require it. Prefer conditional storage, e.g. 32-bit moves for boards that fit and 64-bit moves only when necessary.
- Bitboard word count is performance-critical. Generic loops over words may be acceptable for correctness, but benchmark hot paths against fixed-size/unrolled implementations where 16x16 performance matters.
- For 16x16, preserve existing behavior and benchmark against the prior 16x16 BMI2 build when touching bitboard, move, or attack code.
- For non-PEXT large-board support, distinguish clearly between:
  - relevant blocker masks,
  - blocker extraction/indexing,
  - attack lookup tables,
  - ray-based attack generation.
- Avoid terminology such as “PEXT magics.” PEXT and magic multiplication are different blocker-indexing/extraction mechanisms.
- Tiled bitboards/magic-indexed fallback work should be introduced as a fallback for non-PEXT/slow-PEXT targets, not as an unbenchmarked replacement for known-fast PEXT builds.

## Build and benchmark comparisons

When comparing two implementations:

- Use the same compiler, Makefile flags, `ARCH`, board dimensions, NNUE/classical settings, and bench/search command.
- Compare correctness first: node counts, best moves, evals, and variant validation.
- Compare speed second: NPS and elapsed time can be noisy; use repeated runs if the conclusion matters.
- Be clear whether a change affects correctness, node count, or only speed.

Useful examples:

```bash
make -C src clean && make -C src -j2 ARCH=x86-64-bmi2 board_files=16 board_ranks=16 build
./src/stockfish bench 16 1 5 default depth

make -C src clean && make -C src -j2 ARCH=x86-64 board_files=12 board_ranks=16 build
./src/stockfish check src/variants.ini
```

## Coding practices

- Keep changes minimal and focused on the user’s task.
- Do not stage unrelated files. Avoid `git add .` unless every changed file is intentionally part of the task.
- Use `git diff --check` before committing.
- Prefer `rg` over recursive `grep`; do not use `ls -R` or `grep -R` in this repo.
- Do not put try/catch blocks around imports.
- Preserve existing style unless a broader refactor is explicitly requested.
- For generated or repetitive code, explain how it was produced if that matters for maintainability.

## Documentation and terminology

- Be precise about build features: `ARCH`, `USE_PEXT`, `PRECOMPUTED_MAGICS`, board dimensions, and protocol are separate concerns.
- Use “PEXT blocker extraction/indexing” or “PEXT-indexed lookup,” not “PEXT magics.”
- Use “magic multiplication” or “magic-indexed lookup” for traditional magic bitboard indexing.
- Use “ray-based attack generation” for the precomputed-ray plus first-blocker approach.
- If changing public protocol output, test UCI/USI/XBoard implications where relevant.

## PR and final-response expectations for agents

When making code changes:

- Summarize what changed and cite changed files in the final response.
- List exact test commands run and whether they passed or were blocked by environment limitations.
- If a required test cannot run because of missing tools such as `expect`, say so explicitly.
- Mention benchmark caveats if timings are noisy or only short-depth checks were run.
- Commit only the intended changes on the current branch.

## External references for variant rules

When rule research is needed, useful starting points include:

- <https://en.wikipedia.org/wiki/List_of_chess_variants>
- <https://www.chessvariants.com/>
- <https://boardgamegeek.com/boardgamefamily/4024/traditional-games-chess>
- <https://www.pychess.org/variants>
- <https://ludii.games/library.php>
- <https://lichess.org/variant>
- <https://greenchess.net/variants.php>
- <https://www.chess.com/variants>
