# Fairy-Stockfish

## Overview

[![Build Status](https://github.com/fairy-stockfish/Fairy-Stockfish/actions/workflows/release.yml/badge.svg?branch=master)](https://github.com/fairy-stockfish/Fairy-Stockfish/actions?query=workflow%3ARelease)
[![Build Status](https://github.com/fairy-stockfish/Fairy-Stockfish/actions/workflows/fairy.yml/badge.svg?branch=master)](https://github.com/fairy-stockfish/Fairy-Stockfish/actions?query=workflow%3Afairy)
[![Build Status](https://ci.appveyor.com/api/projects/status/github/fairy-stockfish/Fairy-Stockfish?branch=master&svg=true)](https://ci.appveyor.com/project/ianfab/Fairy-Stockfish/branch/master)
[![PyPI version](https://badge.fury.io/py/pyffish.svg)](https://badge.fury.io/py/pyffish)
[![NPM version](https://img.shields.io/npm/v/ffish.svg?sanitize=true)](https://www.npmjs.com/package/ffish)

Fairy-Stockfish is a chess variant engine derived from [Stockfish](https://github.com/official-stockfish/Stockfish/) designed for the support of fairy chess variants and easy extensibility with more games. It can play various regional, historical, and modern chess variants as well as [games with user-defined rules](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Variant-configuration). For [compatibility with graphical user interfaces](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Graphical-user-interfaces) it supports the UCI, UCCI, USI, UCI-cyclone, and CECP/XBoard protocols.

The goal of the project is to create an engine supporting a large variety of chess-like games, equipped with the powerful search of Stockfish. Despite its generality the [playing strength](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Playing-strength) is on a very high level in almost all supported variants. Due to its multi-protocol support Fairy-Stockfish works with almost any chess variant GUI.

## Installation
You can download the [Windows executable](https://github.com/fairy-stockfish/Fairy-Stockfish/releases/latest/download/fairy-stockfish-largeboard_x86-64.exe) or [Linux binary](https://github.com/fairy-stockfish/Fairy-Stockfish/releases/latest/download/fairy-stockfish-largeboard_x86-64) from the [latest release](https://github.com/fairy-stockfish/Fairy-Stockfish/releases/latest) or [compile the program from source](https://github.com/fairy-stockfish/Fairy-Stockfish#compiling-stockfish-yourself-from-the-sources). The program comes without a graphical user interface, so you perhaps want to use it together with a [compatible GUI](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Graphical-user-interfaces), or [play against it online](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Online) at [pychess](https://www.pychess.org/), [lishogi](https://lishogi.org/@/Fairy-Stockfish), or [lichess](https://lichess.org/@/Fairy-Stockfish). Read more about [how to use](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Usage) Fairy-Stockfish in the wiki.

If you want to preview the functionality of Fairy-Stockfish before downloading, you can try it out on the [Fairy-Stockfish playground](https://fairyground.vercel.app/) in the browser.

Optional NNUE evaluation parameter files to improve playing strength for many variants are in the [list of NNUE networks](https://fairy-stockfish.github.io/nnue/#current-best-nnue-networks).
For the regional variants Xiangqi, Janggi, and Makruk [dedicated releases with built-in NNUE networks](https://github.com/fairy-stockfish/Fairy-Stockfish-NNUE) are available. See the [wiki](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/NNUE) for more details on NNUE.

## Contributing

If you like this project, please support its development via [patreon](https://www.patreon.com/ianfab), [paypal](https://paypal.me/FairyStockfish), or [github](https://github.com/sponsors/ianfab), or by [contributing to the code](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Contributing) or documentation. An [introduction to the code base](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Understanding-the-code) can be found in the wiki.

## Supported games

The games currently supported besides chess are listed below. Fairy-Stockfish can also play user-defined variants loaded via a variant configuration file, see the file [`src/variants.ini`](https://github.com/ianfab/Fairy-Stockfish/blob/master/src/variants.ini) and the [wiki](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki/Variant-configuration).

### Regional and historical games
- [Xiangqi](https://en.wikipedia.org/wiki/Xiangqi), [Manchu](https://en.wikipedia.org/wiki/Manchu_chess), [Minixiangqi](https://www.pychess.org/variants/minixiangqi), [Supply chess](https://en.wikipedia.org/wiki/Xiangqi#Variations)
- [Shogi](https://en.wikipedia.org/wiki/Shogi), [Shogi variants](https://github.com/fairy-stockfish/Fairy-Stockfish#shogi-variants)
- [Janggi](https://en.wikipedia.org/wiki/Janggi)
- [Makruk](https://en.wikipedia.org/wiki/Makruk), [ASEAN](http://hgm.nubati.net/rules/ASEAN.html), Makpong, Ai-Wok
- [Ouk Chatrang](https://en.wikipedia.org/wiki/Makruk#Cambodian_chess), [Kar Ouk](https://en.wikipedia.org/wiki/Makruk#Cambodian_chess)
- [Sittuyin](https://en.wikipedia.org/wiki/Sittuyin)
- [Shatar](https://en.wikipedia.org/wiki/Shatar), [Jeson Mor](https://en.wikipedia.org/wiki/Jeson_Mor)
- [Shatranj](https://en.wikipedia.org/wiki/Shatranj), [Courier](https://en.wikipedia.org/wiki/Courier_chess)
- [Raazuvaa](https://www.reddit.com/r/chess/comments/sj7y3n/raazuvaa_the_chess_of_the_maldives)

### Chess variants
- [Capablanca](https://en.wikipedia.org/wiki/Capablanca_Chess), [Janus](https://en.wikipedia.org/wiki/Janus_Chess), [Modern](https://en.wikipedia.org/wiki/Modern_Chess_(chess_variant)), [Chancellor](https://en.wikipedia.org/wiki/Chancellor_Chess), [Embassy](https://en.wikipedia.org/wiki/Embassy_Chess), [Gothic](https://www.chessvariants.com/large.dir/gothicchess.html), [Capablanca random chess](https://en.wikipedia.org/wiki/Capablanca_Random_Chess)
- [Grand](https://en.wikipedia.org/wiki/Grand_Chess), [Shako](https://www.chessvariants.com/large.dir/shako.html), [Centaur](https://www.chessvariants.com/large.dir/contest/royalcourt.html), [Tencubed](https://www.chessvariants.com/contests/10/tencubedchess.html), [Opulent](https://www.chessvariants.com/rules/opulent-chess)
- [Chess960](https://en.wikipedia.org/wiki/Chess960), [Placement/Pre-Chess](https://www.chessvariants.com/link/placement-chess)
- [Crazyhouse](https://en.wikipedia.org/wiki/Crazyhouse), [Loop](https://en.wikipedia.org/wiki/Crazyhouse#Variations), [Chessgi](https://en.wikipedia.org/wiki/Crazyhouse#Variations), [Pocket Knight](http://www.chessvariants.com/other.dir/pocket.html), Capablanca-Crazyhouse
- [Bughouse](https://en.wikipedia.org/wiki/Bughouse_chess), [Koedem](http://schachclub-oetigheim.de/wp-content/uploads/2016/04/Koedem-rules.pdf)
- [Seirawan](https://en.wikipedia.org/wiki/Seirawan_chess), Seirawan-Crazyhouse, [Dragon Chess](https://www.edami.com/dragonchess/)
- [Amazon](https://www.chessvariants.com/diffmove.dir/amazone.html), [Chigorin](https://www.chessvariants.com/diffsetup.dir/chigorin.html), [Almost chess](https://en.wikipedia.org/wiki/Almost_Chess)
- [Hoppel-Poppel](http://www.chessvariants.com/diffmove.dir/hoppel-poppel.html), New Zealand
- [Antichess](https://lichess.org/variant/antichess), [Giveaway](http://www.chessvariants.com/diffobjective.dir/giveaway.old.html), [Suicide](https://www.freechess.org/Help/HelpFiles/suicide_chess.html), [Losers](https://www.chessclub.com/help/Wild17), [Codrus](http://www.binnewirtz.com/Schlagschach1.htm)
- [Extinction](https://en.wikipedia.org/wiki/Extinction_chess), [Kinglet](https://en.wikipedia.org/wiki/V._R._Parton#Kinglet_chess), Three Kings, [Coregal](https://www.chessvariants.com/winning.dir/coregal.html)
- [King of the Hill](https://en.wikipedia.org/wiki/King_of_the_Hill_(chess)), [Racing Kings](https://en.wikipedia.org/wiki/V._R._Parton#Racing_Kings)
- [Three-check](https://en.wikipedia.org/wiki/Three-check_chess), Five-check
- [Los Alamos](https://en.wikipedia.org/wiki/Los_Alamos_chess), [Gardner's Minichess](https://en.wikipedia.org/wiki/Minichess#5%C3%975_chess)
- [Atomic](https://en.wikipedia.org/wiki/Atomic_chess)
- [Horde](https://en.wikipedia.org/wiki/Dunsany%27s_Chess#Horde_Chess), [Maharajah and the Sepoys](https://en.wikipedia.org/wiki/Maharajah_and_the_Sepoys)
- [Knightmate](https://www.chessvariants.com/diffobjective.dir/knightmate.html), [Nightrider](https://en.wikipedia.org/wiki/Nightrider_(chess)), [Grasshopper](https://en.wikipedia.org/wiki/Grasshopper_chess)
- [Duck chess](https://duckchess.com/), [Omicron](http://www.eglebbk.dds.nl/program/chess-omicron.html), [Gustav III](https://www.chessvariants.com/play/gustav-iiis-chess)
- [Berolina Chess](https://en.wikipedia.org/wiki/Berolina_pawn#Berolina_chess), [Pawn-Sideways](https://arxiv.org/abs/2009.04374), [Pawn-Back](https://arxiv.org/abs/2009.04374), [Torpedo](https://arxiv.org/abs/2009.04374), [Legan Chess](https://en.wikipedia.org/wiki/Legan_chess)
- [Spartan Chess](https://www.chessvariants.com/rules/spartan-chess)
- [Wolf Chess](https://en.wikipedia.org/wiki/Wolf_chess)
- [Troitzky Chess](https://www.chessvariants.com/play/troitzky-chess)

### Shogi variants
- [Minishogi](https://en.wikipedia.org/wiki/Minishogi), [EuroShogi](https://en.wikipedia.org/wiki/EuroShogi), [Judkins shogi](https://en.wikipedia.org/wiki/Judkins_shogi)
- [Kyoto shogi](https://en.wikipedia.org/wiki/Kyoto_shogi), [Microshogi](https://en.wikipedia.org/wiki/Micro_shogi)
- [Dobutsu shogi](https://en.wikipedia.org/wiki/Dōbutsu_shōgi), [Goro goro shogi](https://en.wikipedia.org/wiki/D%C5%8Dbutsu_sh%C5%8Dgi#Variation)
- [Tori shogi](https://en.wikipedia.org/wiki/Tori_shogi)
- [Yari shogi](https://en.wikipedia.org/wiki/Yari_shogi)
- [Okisaki shogi](https://en.wikipedia.org/wiki/Okisaki_shogi)
- [Sho shogi](https://en.wikipedia.org/wiki/Sho_shogi)

### Related games
- [Amazons](https://en.wikipedia.org/wiki/Game_of_the_Amazons)
- [Ataxx](https://en.wikipedia.org/wiki/Ataxx)
- [Breakthrough](https://en.wikipedia.org/wiki/Breakthrough_(board_game))
- [Clobber](https://en.wikipedia.org/wiki/Clobber)
- [Cfour](https://en.wikipedia.org/wiki/Connect_Four), [Tic-tac-toe](https://en.wikipedia.org/wiki/Tic-tac-toe)
- [Five Field Kono](https://en.wikipedia.org/wiki/Five_Field_Kono)
- [Flipersi](https://en.wikipedia.org/wiki/Reversi), [Flipello](https://en.wikipedia.org/wiki/Reversi#Othello)
- [Fox and Hounds](https://boardgamegeek.com/boardgame/148180/fox-and-hounds)
- [Isolation](https://boardgamegeek.com/boardgame/1875/isolation)
- [Joust](https://www.chessvariants.com/programs.dir/joust.html)
- [Snailtrail](https://boardgamegeek.com/boardgame/37135/snailtrail)


## Help

See the [Fairy-Stockfish Wiki](https://github.com/fairy-stockfish/Fairy-Stockfish/wiki) for more info, or if the required information is not available, open an [issue](https://github.com/fairy-stockfish/Fairy-Stockfish/issues) or join our [discord server](https://discord.gg/FYUGgmCFB4).

## Configurable builds

Board dimensions are compile-time settings, with a maximum area of 384 cells.
For example, a portable 19x19 executable with 128 total piece-type slots:

```sh
make -C src -j2 ARCH=x86-64 board_files=19 board_ranks=19 \
  piece_slots=128 gating=yes precomputedmagics=no all=yes build
```

`piece_slots` defaults to 64. Requests must be integers from 64 through 512
and are rounded upward to a multiple of 64 (`129` selects `192`). The total
includes native and reserved slots; ordinary custom slots number `piece_slots - 39`.
Piece sets use exactly one 64-bit word per 64 slots. Non-power-of-two capacities
use padding in colour encodings, while type-indexed storage uses the selected
capacity. Larger capacities increase memory use, including per-worker histories.

`gating=yes|no` defaults to `yes` and controls Seirawan-style extra-piece
placement during a move. With `no`, built-in variants requiring it are omitted
and incompatible external variants are rejected. Drops and their regions,
walling, and Cambodian initial-move rules remain available.

Moves widen to 64 bits when any retained payload needs it, including walling
and promoted drops. Every 19x19 build uses 64-bit moves. Native Make builds
automatically rebuild objects when compiler flags change.
Wider-slot builds also reserve larger move lists for drop choices and store the
search move buffer on the heap; the 64-slot build retains its existing bound.

The JavaScript Makefile accepts the same two options. Python builds use the
environment variables `PIECE_SLOTS` and `GATING`; force recompilation when
changing them, for example `PIECE_SLOTS=192 GATING=no python3 setup.py build_ext --force`.
Larger games use classical evaluation when they exceed NNUE feature limits.

Capacity and encoding checks:

```sh
python3 tests/build_features.py
python3 tests/piece_slots_matrix.py
# Run from src/ after building the desired engine:
PIECE_SLOTS=128 BOARD_SIZE=19 GATING=yes python3 ../tests/piece_slots.py
```

## Promotion capture policies

Capture triggers can distinguish whether the victim was promoted before capture:
`oicu/oicp`, `iicu/iicp`, `iocu/iocp`, and optional-only `lastcu/lastcp`.
The `u` suffix means unpromoted and `p` means promoted. This uses the stored
promoted flag, independently of the victim's movement or ability to promote.
Existing `oic`, `iic`, `ioc` and `lastc` include both states; quiet triggers and
the `oi`, `ii`, `io`, `all`, `last` and `inherit` aliases retain their meaning.

For optional promotion on capturing an unpromoted piece and compulsory promotion
on capturing a promoted piece, anywhere on the board:

```ini
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{iicu} mandatory:{iicp}
```

Every victim on a multi-capture route is considered. Capturing any promoted
piece makes promotion mandatory in this example, even if another victim is
unpromoted or the final landing is empty. Promotion occurs at the end of the
whole move. Lion, Lion Dog, Hook and generic double moves use the same resolver.
`lastcu`/`lastcp` remain restricted to the optional section and optional region.
When these policies distinguish victim states, FEN retains promoted markers
and position hashes distinguish promoted from unpromoted instances.

Run `STOCKFISH=src/stockfish python3 tests/promotion_victims.py` from the repository
root for victim-state policy and multi-capture promotion regressions.

## Universal leaper

Custom piece definitions support `U` to leap directly to any other square on the
board, ignoring intervening pieces. `mU` allows only quiet universal moves and
`cU` only universal captures. These atoms can be combined with other movement,
e.g. `mUcK` gives universal quiet moves and king-step captures.

Friendly pieces, walls and mobility regions restrict destinations as usual.
Prohibited captures and trading restrictions apply to universal captures through
the ordinary move legality checks. For a Maka Dai Dai Shogi Emperor, with `k`
and `pr` defined as the King and Prince symbols:

```ini
piece = em:U
tradingRule = em:[any!,{k,pr,em}]
```

This blocks captures of a protected King, Prince or opposing Emperor, including
adjacent captures. Protection uses geometric attacks in the resulting position.
The variant's royal/extinction settings remain separately configurable. The
default material estimate is approximate; explicit piece values can tune it.

Run `STOCKFISH=src/stockfish python3 tests/universal_leaper.py` to test movement
and capture restrictions. Set `BOARD_SIZE=17` to exercise a full 17x17 board in a
large-board build.

## Hook movement capture modes

Hook moves use `hookMovePieces = <piece>:<firstLeg>-<secondLeg>[:1|:2|:1!]`.
The default `:1` allows at most one capture, including a capture on the first leg
followed by a quiet second leg. `:2` allows captures on both legs. `:1!` ends the
move immediately upon capture, so a two-leg route must have a quiet first leg.
A capture on the second leg always ends the move in every mode.

For Dai Dai Shogi's Hook Mover and Long-Nosed Goblin:

```ini
piece = hm:<rook>
piece = lo:WB
hookMovePieces = hm:R-sR:1! lo:B-sB:1!
```

First-leg-only quiet moves and captures are supplied by the regular piece
definition. The hook option adds two-leg routes. Run
`STOCKFISH=src/stockfish python3 tests/hook_moves.py` from the repository root
to test the capture modes.

## Lion Dog multi-leg movement

`lionDogMovePieces` follows the Lion-powered interpretation described by
[Dr Eric Silverman](https://drericsilverman.com/2021/04/22/shogi-variants-translation-notes-i/).
Ordinary steps and jumps remain exclusively in the regular piece definition:

```ini
piece = ld:KADGH
lionDogMovePieces = ld:FFFFFFFFFFFF
```

The option takes the same whitespace-separated `symbol:hex-mask` entries as
`lionMovePieces`, with **12 hexadecimal digits (48 bits)** per mask. It neither
grants nor disables ordinary moves. A zero mask leaves the piece's ordinary
movement intact. The same notation can identify promoted piece symbols.

Each direction has six consecutive bits, starting at the least significant bit.
Direction groups are N, NE, E, SE, S, SW, W, NW for White, rotated 180 degrees
for Black. Relative to the starting square `0`, with squares `1`, `2`, `3`
along that ray:

| Bit within direction | Route | Implementation |
|---:|---|---|
| 0 | `0→1→2` | Existing Lion path |
| 1 | `0→1→0` | Existing Lion path (igui/pass) |
| 2 | `0→1→2→3` | Three outward steps |
| 3 | `0→1→2→1` | Two outward steps, retreat |
| 4 | `0⇢2→3` | Initial jump, outward step |
| 5 | `0⇢2→1` | Initial jump, backward step |

`⇢` means a jump. Jumps bypass intervening pieces; each actual landing captures
an enemy there. The two routes ending on square 1 remain distinct, including
their capture order. Step-then-jump and routes passing backward beyond square 0
are excluded. For example, `00000000003F` enables the six North paths for White
and South paths for Black; `000000000004` selects only three outward North steps.

A Furious Fiend can combine the complete Lion and Lion Dog masks:

```ini
piece = ff:KNADGH
lionMovePieces = ff:FFFFFFFFFFFFFFFF
lionDogMovePieces = ff:FFFFFFFFFFFF
```

Shared paths are generated once. When both masks are explicitly configured
(including inherited settings), their bits must agree on the 16 shared ordered
paths. A disagreement rejects the variant with a diagnostic; Lion-only paths
are independent. An absent mask is distinct from an explicitly supplied zero.

Coordinate notation retains every landing, for example `d4d5d6d7`,
`d4d5d6d5`, `d4d6d7`, and `d4d6d5`. Promotion suffixes follow the complete route.
Capture-based promotion considers captures on every leg and occurs at turn end.
Gating, walling, blast, petrification and enclosure-rule combinations are currently rejected
when Lion Dog movement is enabled.

Run `STOCKFISH=src/stockfish python3 tests/lion_dog.py` from the repository root
for parser, mask, movement, capture, promotion and state-restoration regressions.

## Bindings

Besides the C++ engine, this project also includes bindings for other programming languages in order to be able to use it as a library for chess variants. They support move, SAN, and FEN generation, as well as checking of game end conditions for all variants supported by Fairy-Stockfish. Since the bindings are using the C++ code, they are very performant compared to libraries directly written in the respective target language.

### Python

The python binding [pyffish](https://pypi.org/project/pyffish/) contributed by [@gbtami](https://github.com/gbtami) is implemented in [pyffish.cpp](https://github.com/fairy-stockfish/Fairy-Stockfish/blob/master/src/pyffish.cpp). It is e.g. used in the backend for the [pychess server](https://github.com/gbtami/pychess-variants).

### Javascript

The javascript binding [ffish.js](https://www.npmjs.com/package/ffish) contributed by [@QueensGambit](https://github.com/QueensGambit) is implemented in [ffishjs.cpp](https://github.com/fairy-stockfish/Fairy-Stockfish/blob/master/src/ffishjs.cpp). The compilation/binding to javascript is done using emscripten, see the [readme](https://github.com/fairy-stockfish/Fairy-Stockfish/tree/master/tests/js).

## Ports

### WebAssembly

For in-browser use a [port of Fairy-Stockfish to WebAssembly](https://github.com/fairy-stockfish/fairy-stockfish.wasm) is available at [npm](https://www.npmjs.com/package/fairy-stockfish-nnue.wasm). It is e.g. used for local analysis on [pychess.org](https://www.pychess.org/analysis/chess). Also see the [Fairy-Stockfish WASM demo](https://github.com/ianfab/fairy-stockfish-nnue-wasm-demo) available at https://fairy-stockfish-nnue-wasm.vercel.app/.

## Terms of use

Fairy-Stockfish is free, and distributed under the **GNU General Public License version 3**
(GPL v3). Essentially, this means you are free to do almost exactly
what you want with the program, including distributing it among your
friends, making it available for download from your website, selling
it (either by itself or as part of some bigger software package), or
using it as the starting point for a software project of your own.

The only real limitation is that whenever you distribute Fairy-Stockfish in
some way, you MUST always include the full source code, or a pointer
to where the source code can be found, to generate the exact binary
you are distributing. If you make any changes to the source code,
these changes must also be made available under the GPL.

For full details, read the copy of the GPL v3 found in the file named
[*Copying.txt*](https://github.com/fairy-stockfish/Fairy-Stockfish/blob/master/Copying.txt).
