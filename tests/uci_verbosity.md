# UCI progress verbosity

The engine advertises:

```text
option name UCI_Verbosity type spin default 3 min 1 max 3
```

Set the option before `go`; the value is captured for that search.
Levels 1 and 2 both retain the existing output. Level 3 adds live counters to
existing current-root-move reports (which still begin after three seconds):

```text
info depth 2 currmove e2e4 currmovenumber 1 nodes 133845 nps 586 hashfull 123 tbhits 0 time 228113
```

After more than 15 wall-clock seconds without a PV, current-move or heartbeat
report, level 3 emits:

```text
info nodes 133845 nps 586 hashfull 123 tbhits 0 time 228113
```

The heartbeat uses the existing throttled search time checks (normally every
1024 calls), including the existing quiescence checks on builds above 384 cells.
It does not wait for a completed root move/iteration. Timing is best effort at
those checks; a long operation between checks can delay output. It also works
while terminal/max-depth infinite or ponder searches wait for `stop`.

PV formatting and bestmove remain unchanged. Every emitted PV/current-move/
heartbeat resets the wall-clock silence timer, which resets on each search.
Statistics use the same elapsed-time convention, aggregate node/tablebase
counters and root-tablebase hit adjustment as PV reporting; hashfull is always
included in the new progress lines. Silence timing uses wall time even with
`nodestime`. UCI/USI/UCCI/Cyclone receive the new progress; XBoard output keeps
its existing format. USI advertises the option as `USI_Verbosity`, following
the existing protocol name conversion. Perft output is unchanged.

Run protocol integration tests against a matching build:

```sh
STOCKFISH=/path/to/stockfish python3 tests/uci_verbosity.py -v
BOARD_SIZE=16 STOCKFISH=/path/to/stockfish python3 tests/uci_verbosity.py -v
```

The real heartbeat/reset case takes about 35 seconds; current-move and SMP/
MultiPV cases take another 15 seconds. It requires no external Python packages.

`uci_verbosity.cpp` provides deterministic checks with an explicitly aged
report timestamp: level-1/2 exact current-move lines, option bounds, detailed
format, suppression before/after the silence interval, reset on PV/current
reports, nodestime independence, root-tablebase hits, protocol guards and stop.
Link it with matching engine object files except main.o, using the same board,
piece-capacity, gating and architecture defines as the engine (see the linking
approach in range_jumps.md). Its assertions must remain enabled.

No new polling, options-map lookup or statistics formatting is added to the
per-node fast path. Verbosity is cached per search and extra formatting runs
only when a report is actually emitted.
