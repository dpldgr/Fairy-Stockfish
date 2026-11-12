#!/usr/bin/env python3
"""Independent binary decoders, exact table targets, append and I/O failures."""
from collections import Counter
import itertools
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
import unittest

from mate_table_four import oracle
from uci_verbosity import Engine

ROOT = Path(__file__).parent
PREFIX = 'info string mate-table '
METAL_TYPES = ('p', 'q', 'r', 'b', 'n')


def records(path, size, width=8, height=None, names=METAL_TYPES):
    """Decode from the public formats without using the C++ export/codec code."""
    height = width if height is None else height
    cells = width * height
    with Path(path).open('rb') as stream:
        while raw := stream.read(size):
            assert len(raw) == size
            if size != 72:
                word = int.from_bytes(raw, 'little')
                cursor = 0
                def bits(n):
                    nonlocal cursor
                    value = (word >> cursor) & ((1 << n) - 1)
                    cursor += n
                    return value
                square_bits = max(6, (cells - 1).bit_length())
                type_bits = max(3, (len(names) - 1).bit_length())
                capacity = 0
                for n in range(1, size * 8 + 1):
                    if 2 * square_bits + n * (square_bits + type_bits + 1) + n.bit_length() + 20 > size * 8:
                        break
                    capacity = n
                supports = []
                bitmap = word >> (size * 8 - 1)
                if bitmap:
                    kings = [None, None]
                    occupied = bits(cells)
                    for sq in range(cells):
                        if occupied >> sq & 1:
                            kind, color = bits(len(names).bit_length()), bits(1)
                            if kind == len(names):
                                assert kings[color] is None
                                kings[color] = sq
                            else:
                                supports.append((sq, names[kind], color))
                    assert None not in kings
                    kings = tuple(kings)
                else:
                    kings = (bits(square_bits), bits(square_bits))
                    slots = [(bits(square_bits), bits(type_bits), bits(1)) for _ in range(capacity)]
                turn = bits(1)
                if not bitmap:
                    count = bits(capacity.bit_length())
                    assert count <= capacity
                    assert all(p == (0, 0, 0) for p in slots[count:])
                    supports = [(sq, names[kind], color) for sq, kind, color in slots[:count]]
                score = bits(16)
                score = score if score < 32768 else score - 65536
                result = bits(2) - 1
                assert cursor <= size * 8 - 1
                assert word >> cursor == bitmap << (size * 8 - 1 - cursor)
            else:
                payload = int.from_bytes(raw[:64], 'little')
                cursor = 0
                def bits(n):
                    nonlocal cursor
                    value = (payload >> cursor) & ((1 << n) - 1)
                    cursor += n
                    return value
                turn = bits(1)
                kings = (bits(7), bits(7))
                supports = []
                for rank in range(height - 1, -1, -1):
                    for file in range(width):
                        sq = rank * width + file
                        if sq in kings:
                            continue
                        if bits(1):
                            kind = bits(4)
                            supports.append((sq, names[kind], bits(1)))
                assert bits(10 * (len(names) + 1)) == 0  # Empty hands.
                assert bits(4) == 0 and bits(1) == 0    # No rights/EP.
                assert bits(6) == 0 and bits(16) == 1 and bits(1) == 0
                assert payload >> cursor == 0
                score, move, ply, result, padding = struct.unpack_from('<hHHbB', raw, 64)
                assert (move, ply, padding) == (0, 1, 0)
            supports.sort(key=lambda p: (p[2], names.index(p[1]), p[0]))
            squares = [*kings, *(p[0] for p in supports)]
            assert len(set(squares)) == len(squares) and all(0 <= s < cells for s in squares)
            assert result in (-1, 0, 1)
            assert score == 0 if result == 0 else 0 < result * score <= 32000
            yield kings, tuple(supports), turn, score, result


class Exports(unittest.TestCase):
    binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.config = cls.folder / 'export.ini'
        cls.config.write_text((ROOT / 'fixtures/metal-chess.ini').read_text() + '''
[export-tiny:metal-chess]
maxFile = 3
maxRank = 3
[export-small:metal-chess]
maxFile = 4
maxRank = 4
[export-alias:export-tiny]
piece = sb:<b>
[export-many:export-tiny]
''' + ''.join(f'customPiece{i} = x{chr(97 + i)}:K\n' for i in range(4, 18)) + '''
[export-16types:export-tiny]
''' + ''.join(f'customPiece{i} = x{chr(97 + i)}:K\n' for i in range(4, 15)))
        if int(os.environ.get('BOARD_SIZE', '8')) >= 16:
            with cls.config.open('a') as out:
                out.write('''
[export-128:chess]
maxFile = 16
maxRank = 8
piece = x:K
[export-256:chess]
maxFile = 16
maxRank = 16
piece = x:K
[export-high-slot:export-tiny]
customPiece40 = z:K
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def engine(self, variant='metal-chess', binary=None):
        engine = Engine(binary or self.binary, ('load', str(self.config)))
        engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value ' + variant)
        return engine

    def build(self, engine, material, path, size=None, options=''):
        size_option = '' if size is None else f' entrysize {size}'
        engine.send(f'mate-table pieces {material} format info export "{path}"{size_option} {options}')
        lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'complete ')
                                           or s.startswith(PREFIX + 'error '), timeout=180)]
        self.assertTrue(lines[-1].startswith(PREFIX + 'complete '), '\n'.join(lines))
        exported = next(s for s in lines if s.startswith(PREFIX + 'export complete records '))
        match = re.search(r'records (\d+) entrysize (\d+) bytes (\d+)', exported)
        count, entry_size, byte_count = map(int, match.groups())
        self.assertEqual(entry_size, size or 72)
        self.assertEqual(count * entry_size, byte_count)
        return count, lines

    def test_full_three_piece_metal_targets_and_both_formats(self):
        references = json.loads((ROOT / 'fixtures/mate-table-reference.json').read_text())['cases']
        for piece in ('r', 'b', 'n'):
            with self.subTest(piece=piece), self.engine() as engine:
                ordinary, compact = self.folder / f'{piece}-72.bin', self.folder / f'{piece}-8.bin'
                count, _ = self.build(engine, '{K,' + piece.upper() + ',k}', ordinary)
                compact_count, _ = self.build(engine, '{k,' + piece.upper() + ',K}', compact, 8)
                self.assertEqual(count, compact_count)
                self.assertEqual(count, sum(r['legal'] for r in references[piece]['summary']))
                histogram, summary = Counter(), Counter()
                seen = 0
                for entry, other in itertools.zip_longest(records(ordinary, 72), records(compact, 8)):
                    self.assertEqual(entry, other)
                    kings, supports, turn, score, result = entry
                    self.assertEqual(supports[0][1:], (piece, 0))
                    summary[(turn, result)] += 1
                    if result:
                        histogram[(32000 - abs(score), turn, result)] += 1
                    seen += 1
                self.assertEqual(seen, count)
                for turn, expected in enumerate(references[piece]['summary']):
                    for name, result in [('wins', 1), ('draws', 0), ('losses', -1)]:
                        self.assertEqual(summary[turn, result], expected[name])
                for plies, expected in references[piece]['histogram'].items():
                    self.assertEqual([histogram[int(plies), turn, result]
                                      for turn, result in [(0, 1), (0, -1), (1, 1), (1, -1)]], expected)
                ordinary.unlink(); compact.unlink()

    def test_small_four_five_and_interchangeable_piece_deduplication(self):
        cases = [(('b', 'n'), (0, 0)), (('b', 'n'), (0, 1)),
                 (('n', 'n'), (0, 0)), (('n', 'n'), (0, 1)),
                 (('b', 'n', 'n'), (0, 0, 0)), (('n', 'n', 'n'), (0, 0, 0))]
        for names, owners in cases:
            with self.subTest(names=names, owners=owners), self.engine('export-tiny') as engine:
                path = self.folder / 'multi.bin'
                path.unlink(missing_ok=True)
                material = '{K,' + ','.join(p.upper() if owner == 0 else p
                                           for p, owner in zip(names, owners)) + ',k}'
                count, _ = self.build(engine, material, path, 8)
                reference = oracle(3, names, owners, unordered=len(names) == 3, include_nodes=True)
                seen = set()
                for kings, supports, turn, score, result in records(path, 8, 3):
                    physical = (kings, supports, turn)
                    self.assertNotIn(physical, seen)
                    seen.add(physical)
                    # The oracle retains interchangeable labels, so compare a
                    # matching placement with the same canonical piece order.
                    placements = []
                    unused = list(supports)
                    for name, owner in zip(names, owners):
                        at = next(i for i, p in enumerate(unused) if p[1:] == (name, owner))
                        placements.append(unused.pop(at)[0])
                    node = reference['nodes'][(tuple((*kings, *placements)), turn)]
                    expected = {2: 0, 3: 1, 4: -1}[node['result']]
                    self.assertEqual(result, expected)
                    self.assertEqual(score, 0 if not result else result * (32000 - node['dtm']))
                expected_physical = set()
                for (p, turn), node in reference['nodes'].items():
                    if any(s < 0 for s in p):
                        continue
                    supports = tuple(sorted(((p[i + 2], name, owners[i]) for i, name in enumerate(names)),
                                            key=lambda s: (s[2], METAL_TYPES.index(s[1]), s[0])))
                    expected_physical.add((p[:2], supports, turn))
                self.assertEqual(seen, expected_physical)
                self.assertEqual(count, len(seen))

    def test_every_integer_width_matches_packed_and_bitmap(self):
        with self.engine('export-tiny') as engine:
            baseline = self.folder / 'all-widths-72.bin'
            count, _ = self.build(engine, '{K,B,N,N,k}', baseline)
            expected = list(records(baseline, 72, 3))
            for size in range(7, 145):
                if size == 72:
                    continue
                path = self.folder / f'all-widths-{size}.bin'
                with self.subTest(size=size):
                    actual, _ = self.build(engine, '{k,N,K,B,N}', path, size)
                    self.assertEqual(actual, count)
                    self.assertEqual(list(records(path, size, 3)), expected)
                path.unlink()

    def test_capacity_failure_preserves_destination(self):
        # Three supports on 8x8 need at least eight bytes in this profile.
        path = self.folder / 'too-small.bin'
        prefix = bytes(7)
        path.write_bytes(prefix)
        with self.engine() as engine:
            engine.send(f'mate-table pieces {{K,B,N,N,k}} export "{path}" entrysize 7')
            lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'error '))]
            self.assertIn('does not fit entrysize 7', lines[-1])
            self.assertEqual(path.read_bytes(), prefix)

    def test_expanded_compact_piece_schema(self):
        names = METAL_TYPES + tuple('x' + chr(97 + i) for i in range(4, 18))
        with self.engine('export-many') as engine:
            for size in (7, 8, 9, 73, 144):
                path = self.folder / f'many-types-{size}.bin'
                count, _ = self.build(engine, '{K,XR,k}', path, size)
                decoded = list(records(path, size, 3, names=names))
                self.assertEqual(len(decoded), count)
                self.assertTrue(all(row[1][0][1:] == ('xr', 0) for row in decoded))

    def test_append_paths_aliases_and_black_perspective(self):
        path = self.folder / 'quoted path.bin'
        with self.engine('export-alias') as engine:
            count, _ = self.build(engine, '{K,sb,k}', path)
            first = path.read_bytes()
            reference = oracle(3, ('b',), (1,), include_nodes=True)
            for kings, supports, turn, score, result in records(path, 72, 3, names=('p', 'q', 'r', 'sb', 'n')):
                self.assertEqual(supports[0][1:], ('sb', 1))
                node = reference['nodes'][(tuple((*kings, supports[0][0])), turn)]
                expected = {2: 0, 3: 1, 4: -1}[node['result']]
                self.assertEqual(result, expected)
                self.assertEqual(score, 0 if not result else result * (32000 - node['dtm']))
            again, _ = self.build(engine, '{k,K,sb}', path, 72)
            self.assertEqual(count, again)
            self.assertEqual(path.read_bytes(), first + first)
            # An explicit 72-byte setting and the default are byte-identical.
            self.assertEqual(len(first), count * 72)

    def test_standard_huffman_highest_piece_code(self):
        path = self.folder / 'sixteen-types.bin'
        names = METAL_TYPES + tuple('x' + chr(97 + i) for i in range(4, 15))
        self.assertEqual(len(names), 16)
        with self.engine('export-16types') as engine:
            count, _ = self.build(engine, '{K,XO,k}', path)
            decoded = list(records(path, 72, 3, names=names))
            self.assertEqual(len(decoded), count)
            self.assertTrue(all(row[1][0][1] == 'xo' for row in decoded))

    def test_invalid_options_and_destinations_preserve_cached_table(self):
        with self.engine('export-tiny') as engine:
            path = self.folder / 'valid.bin'
            path.unlink(missing_ok=True)
            self.build(engine, '{K,B,k}', path, 8)
            malformed = self.folder / 'misaligned.bin'
            malformed.write_bytes(b'x')
            for options in ['entrysize 8', 'export', 'export ""', 'export "unterminated',
                            'export "a"tail', 'export a export b', 'export a entrysize 6', 'export a entrysize 145', 'export a entrysize 7.5', 'export a entrysize -4294967289',
                            'export a entrysize 8 entrysize 72', f'export "{malformed}"',
                            f'export "{self.folder}"', f'export "{self.folder}/missing/data.bin"']:
                with self.subTest(options=options):
                    engine.send('mate-table pieces {K,B,k} ' + options)
                    engine.until(lambda s: s.startswith(PREFIX + 'error '))
                    status = [s for _, s in engine.ready('mate-table status')]
                    self.assertIn(PREFIX + 'status ready', status)
            self.assertEqual(malformed.read_bytes(), b'x')
        with self.engine('export-many') as engine:
            for size in (72,):
                path = self.folder / f'too-many-{size}.bin'
                engine.send(f'mate-table pieces {{K,B,k}} export "{path}" entrysize {size}')
                lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'error ')
                                                   or s.startswith(PREFIX + 'complete '))]
                self.assertIn('piece types', lines[-1])
                self.assertFalse(path.exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX file-size limit for deterministic write failure')
    def test_partial_write_preserves_prefix_and_record_boundary(self):
        wrapper = self.folder / 'limited-engine'
        wrapper.write_text('#!/usr/bin/env python3\nimport os, resource, signal, sys\n'
                           'signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n'
                           'resource.setrlimit(resource.RLIMIT_FSIZE, (65537, 65537))\n'
                           f'os.execv({self.binary!r}, [{self.binary!r}] + sys.argv[1:])\n')
        wrapper.chmod(0o755)
        path = self.folder / 'limited.bin'
        prefix = bytes(range(72))
        path.write_bytes(prefix)
        with self.engine(binary=str(wrapper)) as engine:
            engine.send(f'mate-table pieces {{K,B,k}} export "{path}"')
            lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'error '), timeout=120)]
            self.assertIn('export write failed', lines[-1])
            content = path.read_bytes()
            self.assertEqual(content[:72], prefix)
            self.assertEqual(len(content) % 72, 0)
            self.assertGreater(len(content), len(prefix))
            self.assertLessEqual(len(content), 65537)
            self.assertIn(PREFIX + 'status ready', [s for _, s in engine.ready('mate-table status')])

    def test_stop_during_export_keeps_complete_records_and_cached_table(self):
        path = self.folder / 'cancel.bin'
        with self.engine() as engine:
            engine.send(f'mate-table pieces {{K,B,k}} export "{path}"')
            engine.until(lambda s: s.startswith(PREFIX + 'building '))
            deadline = time.monotonic() + 20
            # A nonempty file proves generation finished and export has begun.
            while not path.exists() or not path.stat().st_size:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.001)
            engine.send('stop')
            lines = [s for _, s in engine.until(lambda s: s == PREFIX + 'cancelled'
                                               or s.startswith(PREFIX + 'complete '))]
            self.assertIn(PREFIX + 'cancelled', lines)
            progress = next(s for s in lines if s.startswith(PREFIX + 'export cancelled records '))
            count = int(progress.split('records ')[1].split()[0])
            self.assertGreater(count, 0)
            self.assertLess(count, 414084)
            self.assertEqual(path.stat().st_size, count * 72)
            self.assertIn(PREFIX + 'status ready', [s for _, s in engine.ready('mate-table status')])

    @unittest.skipUnless(int(os.environ.get('BOARD_SIZE', '8')) >= 16, 'large build')
    def test_board_encoding_limits(self):
        path = self.folder / 'board-limit.bin'
        for variant, size, limit in [('export-256', 72, 128)]:
            with self.subTest(variant=variant), self.engine(variant) as engine:
                engine.send(f'mate-table pieces {{K,X,k}} export "{path}" entrysize {size}')
                lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'error '))]
                self.assertIn(f'exceeds {limit} cells', lines[-1])
                self.assertFalse(path.exists())

    @unittest.skipUnless(int(os.environ.get('BOARD_SIZE', '8')) >= 16, '128-slot build')
    def test_raw_slot_above_63_uses_dense_variant_type_index(self):
        path = self.folder / 'high-slot.bin'
        with self.engine('export-high-slot') as engine:
            count, _ = self.build(engine, '{K,Z,k}', path, 8)
            decoded = list(records(path, 8, 3, names=METAL_TYPES + ('z',)))
            self.assertEqual(len(decoded), count)
            self.assertTrue(all(row[1][0][1:] == ('z', 0) for row in decoded))


if __name__ == '__main__':
    unittest.main()
