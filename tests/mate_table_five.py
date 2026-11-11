#!/usr/bin/env python3
"""Local five-piece experiment: independent references, native moves and timings."""
import argparse
import json
from pathlib import Path
import re
import threading
import time

from mate_table_four import build, fields, native_checks, oracle, PREFIX
from uci_verbosity import Engine


def command(names, owners, memory=8192, format='info'):
    result = 'mate-table piece ' + names[0]
    for name, owner in zip(names[1:], owners[1:]):
        result += (' partner ' if owner == owners[0] else ' opponent ') + name
    if owners[0]:
        result += ' color black'
    return result + f' memory {memory} format {format}'


def small_references(args, config, out):
    cases = [(3, ('b', 'n', 'n'), (0, 0, 0), 0),
             (3, ('n', 'n', 'b'), (0, 0, 0), 0),
             (3, ('b', 'n', 'b'), (0, 0, 0), 0),
             (3, ('b', 'n', 'r'), (0, 0, 0), 0),
             (3, ('b', 'n', 'n'), (0, 0, 1), 0),
             (3, ('b', 'n', 'n'), (0, 0, 0), -1),
             (3, ('b', 'n', 'n'), (0, 0, 0), 1),
             (4, ('b', 'n', 'n'), (0, 0, 0), 0)]
    results = []
    for width, names, owners, stale in cases:
        print('Independent five-piece oracle:', width, names, owners, stale, flush=True)
        reference = oracle(width, names, owners, stale, unordered=True)
        variant = 'metal-small' if width == 4 else 'metal-tiny'
        if stale:
            variant = 'metal-stale-loss' if stale < 0 else 'metal-stale-win'
        with Engine(args.binary, ('load', str(config))) as engine:
            engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value ' + variant)
            actual, lines, raw = build(engine, command(names, owners), timeout=600)
            assert actual['summary'] == reference['summary'], (actual, reference)
            assert actual['signature'] == reference['signature'], (actual, reference)
            actual['native'] = native_checks(engine, 100, width, names, owners)
        results.append({'width': width, 'names': names, 'owners': owners, 'stalemate': stale,
                        'actual': actual, 'reference': reference})
        out.joinpath('small-references.json').write_text(json.dumps(results, indent=2) + '\n')
    print('PASS: all five-piece references and native probes', flush=True)


def large_run(args, config, out):
    print('Starting 8x8 Metal Chess KBNN versus K', flush=True)
    with Engine(args.binary, ('load', str(config))) as engine:
        engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value metal-chess')
        samples, finished = [], threading.Event()
        started = time.monotonic()

        def memory():
            while not finished.is_set():
                status = Path(f'/proc/{engine.proc.pid}/status').read_text()
                samples.append({'seconds': time.monotonic() - started,
                                'rss_kib': int(re.search(r'VmRSS:\s+(\d+)', status)[1]),
                                'peak_kib': int(re.search(r'VmHWM:\s+(\d+)', status)[1])})
                if len(samples) % 10 == 0:
                    out.joinpath('memory-samples.json').write_text(json.dumps(samples, indent=2) + '\n')
                finished.wait(1)

        thread = threading.Thread(target=memory, daemon=True)
        thread.start()
        try:
            engine.send(command(('b', 'n', 'n'), (0, 0, 0), format='table'))
            with out.joinpath('large-run.log').open('w') as log:
                def report(line):
                    log.write(line + '\n')
                    log.flush()
                    return line.startswith(('complete ', 'error ', PREFIX + 'error '))
                lines = [s for _, s in engine.until(report, timeout=7200)]
            assert lines[-1].startswith('complete '), '\n'.join(lines[-20:])
            wall = time.monotonic() - started
            raw = [s for _, s in engine.ready('mate-table stats raw') if s != 'readyok']
            out.joinpath('large-raw.log').write_text('\n'.join(raw) + '\n')
            summary = [fields('legal ' + s.split(' legal ')[1]) for s in raw if s.startswith(PREFIX + 'summary stm ')]
            result = {'summary': summary, 'wall_seconds': wall}
            for key in ('diagnostics', 'storage_header', 'indexing', 'timing'):
                line = next(s for s in raw if s.startswith(PREFIX + key + ' '))
                result[key] = fields(line[len(PREFIX + key + ' '):])
            assert result['storage_header']['record_bytes'] == 2
            assert result['diagnostics']['table_bytes'] == 2016 * 1048576
            assert result['diagnostics']['counter_bytes'] == 0
            assert result['diagnostics']['construction_peak_bytes'] == 3024 * 1048576
            assert result['indexing']['interchangeable_pair'] == 1
            assert summary[0]['losses'] == 0 and summary[1]['wins'] == 0
            result['native'] = native_checks(engine, args.samples, 8, ('b', 'n', 'n'), (0, 0, 0))
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
            for side, army in enumerate(('white', 'black')):
                rows = [list(map(int, match.groups())) for line in views['info']
                        if (match := re.fullmatch(PREFIX + 'army ' + army + r' mate (\d+) mated (\d+) in (\d+)', line))]
                assert rows == table[army]
                assert sum(row[0] for row in rows) == summary[side]['wins']
                assert sum(row[1] for row in rows) == summary[1 - side]['losses']
            result['tables'] = table
            status = Path(f'/proc/{engine.proc.pid}/status').read_text()
            result['peak_rss_kib'] = int(re.search(r'VmHWM:\s+(\d+)', status)[1])
            result['retained_rss_kib'] = int(re.search(r'VmRSS:\s+(\d+)', status)[1])
            out.joinpath('output-tables.txt').write_text('\n'.join(views['table']) + '\n')
            out.joinpath('results.json').write_text(json.dumps(result, indent=2) + '\n')
            print('PASS: 8x8 KBNN/K, full verification, native move probes and matching output formats', flush=True)
            print(json.dumps(result), flush=True)
        finally:
            finished.set()
            thread.join()
            out.joinpath('memory-samples.json').write_text(json.dumps(samples, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--large', action='store_true')
    parser.add_argument('--skip-small', action='store_true')
    parser.add_argument('--samples', type=int, default=2000)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    config = out / 'test-variants.ini'
    config.write_text((Path(__file__).parent / 'fixtures/metal-chess.ini').read_text()
                      + '\n[metal-small:metal-chess]\nmaxFile = 4\nmaxRank = 4\n'
                      + '\n[metal-tiny:metal-chess]\nmaxFile = 3\nmaxRank = 3\n'
                      + '\n[metal-stale-loss:metal-tiny]\nstalemateValue = loss\n'
                      + '\n[metal-stale-win:metal-tiny]\nstalemateValue = win\n')
    if not args.skip_small:
        small_references(args, config, out)
    if args.large:
        large_run(args, config, out)


if __name__ == '__main__':
    main()
