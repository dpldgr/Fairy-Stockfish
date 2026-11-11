#!/usr/bin/env python3
"""Local four-piece prototype: independent Metal oracle and native move checks."""
import argparse
from collections import Counter
import heapq
import itertools
import json
from pathlib import Path
import random
import re
import statistics
import time

from uci_verbosity import Engine

PREFIX = 'info string mate-table '
DRAW, WIN, LOSS = 2, 3, 4


def fields(text):
    tokens = text.split()
    return {tokens[i]: int(tokens[i + 1]) for i in range(0, len(tokens), 2)}


def oracle(width, names, owners, stalemate=0, unordered=False):
    """Explicit full graph, including captures, without any engine table code."""
    cells = range(width * width)
    supports = len(names)
    piece_count = supports + 2
    pair = next(((a, b) for a in range(supports) for b in range(a + 1, supports)
                 if names[a] == names[b] and owners[a] == owners[b]), None) if unordered else None

    def canonicalize(p):
        if pair:
            a, b = pair[0] + 2, pair[1] + 2
            if p[a] >= 0 and p[b] >= 0 and p[a] > p[b]:
                p = list(p)
                p[a], p[b] = p[b], p[a]
                p = tuple(p)
        return p
    king = [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if x or y]
    knight = [(x, y) for x, y in itertools.product((-2, -1, 1, 2), repeat=2) if abs(x) != abs(y)]

    def destinations(p, mover):
        square = p[mover]
        x, y = square % width, square // width
        if mover < 2:
            steps, rays = king, []
        elif names[mover - 2] == 'b':
            steps = [(0, 1 if owners[mover - 2] == 0 else -1)]
            rays = [(a, b) for a, b in king if a and b]
        elif names[mover - 2] == 'r':
            forward = 1 if owners[mover - 2] == 0 else -1
            steps = [(-1, forward), (1, forward)]
            rays = [(a, b) for a, b in king if not (a and b)]
        else:
            forward = 1 if owners[mover - 2] == 0 else -1
            steps, rays = knight + [(a, forward) for a in (-1, 0, 1)], []
        result = []
        for dx, dy in steps:
            xx, yy = x + dx, y + dy
            if 0 <= xx < width and 0 <= yy < width:
                result.append(yy * width + xx)
        for dx, dy in rays:
            xx, yy = x + dx, y + dy
            while 0 <= xx < width and 0 <= yy < width:
                sq = yy * width + xx
                result.append(sq)
                if sq in p:
                    break
                xx, yy = xx + dx, yy + dy
        return result

    def checked(p, side):
        return any(p[side] in destinations(p, mover)
                   for mover in range(piece_count) if p[mover] >= 0
                   and (mover if mover < 2 else owners[mover - 2]) != side)

    def moves(p, side):
        for mover in range(piece_count):
            if p[mover] < 0 or (mover if mover < 2 else owners[mover - 2]) != side:
                continue
            for to in destinations(p, mover):
                if any(to == sq and (j if j < 2 else owners[j - 2]) == side for j, sq in enumerate(p)):
                    continue
                if to == p[1 - side]:
                    continue
                child = list(p)
                for j in range(2, piece_count):
                    if child[j] == to:
                        child[j] = -1
                child[mover] = to
                child = tuple(child)
                if not checked(child, side):
                    yield canonicalize(child), 1 - side

    states, index = [], {}
    subsets = [subset for count in range(supports + 1)
               for subset in itertools.combinations(range(2, piece_count), count)]
    for present in subsets:
        for squares in itertools.permutations(cells, len(present) + 2):
            p = [squares[0], squares[1]] + [-1] * supports
            for j, sq in zip(present, squares[2:]):
                p[j] = sq
            p = tuple(p)
            if canonicalize(p) != p:
                continue
            if p[1] in destinations(p, 0):
                continue
            for side in (0, 1):
                if not checked(p, 1 - side):
                    key = (p, side)
                    index[key] = len(states)
                    states.append(key)
    parents = [[] for _ in states]
    remaining, result, distance = [0] * len(states), [0] * len(states), [0] * len(states)
    queue = []
    for i, (p, side) in enumerate(states):
        successors = list(moves(p, side))
        remaining[i] = len(successors)
        for child in successors:
            parents[index[child]].append(i)
        if not successors:
            result[i] = LOSS if checked(p, side) or stalemate < 0 else WIN if stalemate > 0 else DRAW
            if result[i] in (WIN, LOSS):
                heapq.heappush(queue, (0, i))
    while queue:
        d, child = heapq.heappop(queue)
        for parent in parents[child]:
            if result[parent]:
                continue
            if result[child] == LOSS:
                result[parent], distance[parent] = WIN, d + 1
            else:
                remaining[parent] -= 1
                if remaining[parent]:
                    continue
                result[parent], distance[parent] = LOSS, d + 1
            heapq.heappush(queue, (distance[parent], parent))
    summaries = [Counter({k: 0 for k in ('legal', 'wins', 'draws', 'losses', 'checkmates', 'max_dtm_plies')})
                 for _ in range(2)]
    signature = 14695981039346656037
    # Same public raw checksum encoding, independently computed results.
    def placements():
        if pair:
            a, b = pair
            single = next(i for i in range(supports) if i not in pair)
            for wk, bk, x in itertools.product(cells, repeat=3):
                for hi in range(1, width * width):
                    for lo in range(hi):
                        p = [wk, bk] + [-1] * supports
                        p[single + 2], p[a + 2], p[b + 2] = x, lo, hi
                        yield tuple(p)
        else:
            yield from itertools.product(cells, repeat=piece_count)

    for p in placements():
        for side in (0, 1):
            i = index.get((p, side))
            r, d = (result[i] or DRAW, distance[i]) if i is not None else (0, 0)
            for byte in [r, *(d >> shift & 255 for shift in (0, 8, 16, 24))]:
                signature = (signature ^ byte) * 1099511628211 & (2**64 - 1)
            if r:
                row = summaries[side]
                row['legal'] += 1
                row[{WIN: 'wins', LOSS: 'losses', DRAW: 'draws'}[r]] += 1
                row['checkmates'] += r == LOSS and d == 0 and checked(p, side)
                row['max_dtm_plies'] = max(row['max_dtm_plies'], d)
    return {'summary': [dict(s) for s in summaries], 'signature': signature, 'graph_states': len(states)}


def position(p, side, width, names, owners):
    symbols = {p[0]: 'K', p[1]: 'k'}
    symbols.update({p[j + 2]: names[j].upper() if owners[j] == 0 else names[j] for j in range(len(names))})
    rows = [','.join(symbols.get(y * width + x, '1') for x in range(width))
            for y in range(width - 1, -1, -1)]
    return '/'.join(rows) + (' w' if side == 0 else ' b') + ' - - 0 1'


def build(engine, command, timeout=300):
    started = time.monotonic()
    engine.send(command)
    prefix = '' if re.search(r'\bformat table\b', command) else PREFIX
    lines = [s for _, s in engine.until(lambda s: s.startswith(prefix + 'complete')
                                        or s.startswith(prefix + 'error')
                                        or s.startswith(PREFIX + 'error'), timeout=timeout)]
    assert lines[-1].startswith(prefix + 'complete'), '\n'.join(lines)
    wall = time.monotonic() - started
    raw = [s for _, s in engine.ready('mate-table stats raw') if s != 'readyok']
    summary = []
    for line in raw:
        if line.startswith(PREFIX + 'summary stm '):
            summary.append(fields('legal ' + line.split(' legal ')[1]))
    diagnostic = fields(next(s for s in raw if s.startswith(PREFIX + 'diagnostics '))[len(PREFIX + 'diagnostics '):])
    timing_rows = [s for s in raw if s.startswith(PREFIX + 'timing ')]
    timing = fields(timing_rows[0][len(PREFIX + 'timing '):]) if timing_rows else {'total': diagnostic['time']}
    actual = {'summary': summary, **diagnostic, 'timing_ms': timing, 'wall_seconds': wall}
    headers = [s for s in raw if s.startswith(PREFIX + 'storage_header ')]
    if headers:
        actual['storage_header'] = fields(headers[0][len(PREFIX + 'storage_header '):])
        assert actual['storage_header']['version'] == 1 and actual['storage_header']['status_bits'] == 2
        bits, size = actual['storage_header']['dtm_bits'], actual['storage_header']['record_bytes']
        assert (bits, size) in ((14, 2), (30, 4))
        assert actual['counter_bytes'] == 0
        assert actual['construction_peak_bytes'] == actual['table_bytes'] * (3 if size == 2 else 7) // size
    return actual, lines, raw


def native_checks(engine, samples, width, names=('b', 'n'), owners=(0, 1)):
    rng = random.Random(7019)
    tested = attempts = captures = edges = mates = 0
    outcomes = Counter()
    examples = {}
    while tested < samples:
        p, side = tuple(rng.sample(range(width * width), len(names) + 2)), rng.randrange(2)
        fen = position(p, side, width, names, owners)
        probe = [s for _, s in engine.ready('position fen ' + fen + '\nmate-table probe')]
        attempts += 1
        if any(s.startswith(PREFIX + 'error ') for s in probe):
            continue
        root = next(s for s in probe if s.startswith(PREFIX + 'probe result '))
        result = root.split(' result ')[1].split()[0]
        children = {}
        for line in probe:
            if line.startswith(PREFIX + 'edge move '):
                m = re.fullmatch(PREFIX + r'edge move (\S+) result (win|loss|draw)(?: dtm_plies (\d+))?', line)
                assert m, line
                move, child, dtm = m.groups()
                assert move not in children
                children[move] = (child, int(dtm) if dtm else None)
        engine.send('go perft 1')
        perft = [s for _, s in engine.until(lambda s: s.startswith('Nodes searched:'))]
        native = {s.split(':')[0] for s in perft if re.fullmatch(r'[a-z]\d+[a-z]\d+: 1', s)}
        assert set(children) == native, (fen, children, perft)
        assert int(perft[-1].split(':')[1]) == len(children)
        if children:
            losing = [d for r, d in children.values() if r == 'loss']
            if losing:
                assert result == 'win' and int(root.split('dtm_plies ')[1]) == min(losing) + 1, (fen, probe)
            elif all(r == 'win' for r, _ in children.values()):
                assert result == 'loss' and int(root.split('dtm_plies ')[1]) == max(d for _, d in children.values()) + 1, (fen, probe)
            else:
                assert result == 'draw', (fen, probe)
        else:
            mates += 1
        for move in children:
            to = (int(move[3]) - 1) * width + ord(move[2]) - ord('a')
            captures += to in p[2:]
        outcomes[result] += 1
        examples.setdefault(result, {'fen': fen, 'probe': root})
        edges += len(children)
        tested += 1
    return {'positions': tested, 'random_candidates': attempts, 'legal_edges': edges,
            'capture_edges': captures, 'terminal_positions': mates, 'outcomes': dict(outcomes), 'examples': examples}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--samples', type=int, default=2000)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    config = out / 'test-variants.ini'
    config.write_text((Path(__file__).parent / 'fixtures/metal-chess.ini').read_text()
                      + '\n[metal-small:metal-chess]\nmaxFile = 4\nmaxRank = 4\n'
                      + '\n[metal-tiny:metal-chess]\nmaxFile = 3\nmaxRank = 3\n'
                      + '\n[metal-stale-loss:metal-tiny]\nstalemateValue = loss\n'
                      + '\n[metal-stale-win:metal-tiny]\nstalemateValue = win\n')
    report = {'oracle_cases': [], 'runs': []}
    for width, names, owners, stale in [(4, ('b', 'n'), (0, 1), 0), (3, ('b', 'n'), (0, 0), 0),
                                       (3, ('b', 'b'), (0, 0), 0), (3, ('b', 'n'), (0, 1), -1),
                                       (3, ('b', 'n'), (0, 1), 1)]:
        print('Independent oracle', width, names, owners, 'stalemate', stale, flush=True)
        reference = oracle(width, names, owners, stale)
        variant = 'metal-small' if width == 4 else 'metal-tiny' if not stale else 'metal-stale-loss' if stale < 0 else 'metal-stale-win'
        option = 'opponent' if owners[0] != owners[1] else 'partner'
        with Engine(args.binary, ('load', str(config))) as engine:
            engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value ' + variant)
            actual, lines, raw = build(engine, f'mate-table piece {names[0]} {option} {names[1]} format info')
            assert actual['summary'] == reference['summary'], (actual, reference)
            assert actual['signature'] == reference['signature'], (actual, reference)
            native = native_checks(engine, min(args.samples, 200), width, names, owners)
        report['oracle_cases'].append({'width': width, 'pieces': names, 'owners': owners, 'stalemate': stale, 'reference': reference,
                                       'actual': actual, 'native': native})
    for run in range(args.runs):
        print('8x8 Metal KB versus KN run', run + 1, flush=True)
        with Engine(args.binary, ('load', str(config))) as engine:
            engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value metal-chess')
            actual, lines, raw = build(engine, 'mate-table piece b opponent n format info')
            out.joinpath(f'run{run + 1}.log').write_text('\n'.join(lines + raw) + '\n')
            status = Path(f'/proc/{engine.proc.pid}/status').read_text()
            actual['peak_rss_kib'] = int(re.search(r'VmHWM:\s+(\d+)', status)[1])
            actual['retained_rss_kib'] = int(re.search(r'VmRSS:\s+(\d+)', status)[1])
            if run == 0:
                if 'storage_header' in actual:
                    assert actual['table_bytes'] == 64 * 1048576
                actual['native'] = native_checks(engine, args.samples, 8)
                # Compare all three views and retain the requested plain tables.
                views = {fmt: [s for _, s in engine.ready('mate-table stats format ' + fmt) if s and s != 'readyok']
                         for fmt in ('table', 'info-table', 'info')}
                assert views['table'] == [s.removeprefix(PREFIX) for s in views['info-table']]
                table, army = {}, None
                for line in views['table']:
                    if line.startswith('Statistics '):
                        army = line.split()[1]
                        table[army] = []
                    elif line.startswith('|'):
                        cells = [s.strip() for s in line.strip('|').split('|')]
                        if cells[2] not in ('in', 'tot'):
                            table[army].append([int(cells[0] or 0), int(cells[1]), int(cells[2])])
                for army in ('white', 'black'):
                    rows = [list(map(int, m.groups())) for line in views['info']
                            if (m := re.fullmatch(PREFIX + 'army ' + army + r' mate (\d+) mated (\d+) in (\d+)', line))]
                    assert rows == table[army]
                out.joinpath('output-tables.txt').write_text('\n'.join(views['table']) + '\n')
                actual['tables'] = table
            if run:
                assert actual['signature'] == report['runs'][0]['signature']
            print(json.dumps(actual), flush=True)
            report['runs'].append(actual)
    report['median_generation_ms'] = statistics.median(r['timing_ms']['total'] for r in report['runs'])
    report['median_verify_ms'] = statistics.median(r['timing_ms']['verify'] for r in report['runs'])
    out.joinpath('results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS; median generation', report['median_generation_ms'], 'ms; verification', report['median_verify_ms'], 'ms', flush=True)


if __name__ == '__main__':
    main()
