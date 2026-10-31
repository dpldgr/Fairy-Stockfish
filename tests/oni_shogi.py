#!/usr/bin/env python3
"""Validate the Oni configuration against independently described piece moves."""
import os
from pathlib import Path
import re
import subprocess
import unittest

CONFIG = Path(__file__).parent / 'fixtures' / 'oni-shogi.ini'
ORTH = [(0, 1), (0, -1), (1, 0), (-1, 0)]
DIAG = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
KING = ORTH + DIAG
GOLD = ORTH + [(1, 1), (-1, 1)]
SILVER = DIAG + [(0, 1)]
# Each entry contains (step offsets, unlimited sliding directions).
MOVES = {'k': (KING, []), 'g': (GOLD, []), 's': (SILVER, []),
         're': (DIAG, []), 'n': ([(1, 2), (-1, 2)], []),
         'l': ([], [(0, 1)]), 'b': ([], DIAG), 'r': ([], ORTH),
         'sh': (ORTH, []), 'hy': ([], [(1, 1), (-1, 1)]),
         'ky': ([(0, 1), (0, -1)], []), 'p': ([(0, 1)], [])}
PROMOTED = {'s': (GOLD, []), 're': ([], DIAG), 'n': (GOLD, []),
            'l': (GOLD, []), 'b': (ORTH, DIAG), 'r': (DIAG, ORTH),
            'sh': ([], KING), 'hy': (SILVER, []), 'ky': (SILVER, []),
            'p': (GOLD, [])}


def fen(pieces, side='w'):
    rows = []
    for rank in range(11, 0, -1):
        cells, empty = [], 0
        for file in 'abcdefghijk':
            piece = pieces.get(f'{file}{rank}')
            if piece:
                if empty:
                    cells.append(str(empty))
                    empty = 0
                cells.append(piece)
            else:
                empty += 1
        if empty:
            cells.append(str(empty))
        rows.append(','.join(cells))
    return '/'.join(rows) + f' {side} - - 0 1'


def reference_moves(pieces, source, side, description):
    x, y = ord(source[0]) - ord('a'), int(source[1:])
    result = set()
    for vectors, sliding in ((description[0], False), (description[1], True)):
        for dx, dy in vectors:
            dy *= 1 if side == 'w' else -1
            for distance in range(1, 12 if sliding else 2):
                xx, yy = x + dx * distance, y + dy * distance
                if not (0 <= xx < 11 and 1 <= yy <= 11):
                    break
                target = chr(ord('a') + xx) + str(yy)
                victim = pieces.get(target)
                if victim and victim.lstrip('+').isupper() == (side == 'w'):
                    break
                result.add(source + target)
                if victim:
                    break
    return result


class OniShogi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())

    def output(self, position='startpos', moves='', depth=1):
        position = 'startpos' if position == 'startpos' else 'fen ' + position
        result = subprocess.run([self.engine, 'load', str(CONFIG.resolve())],
            input='setoption name UCI_Variant value oni-shogi\n'
                  f'position {position} moves {moves}\nd\ngo perft {depth}\nd\nquit\n',
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('Nodes searched:', result.stdout)
        return result.stdout

    def moves(self, position, sequence=''):
        out = self.output(position, sequence)
        return {m[1] for m in re.finditer(r'(?m)^(\S+): \d+$', out)}

    def position(self, symbol, side='w', square='f6'):
        return {'a1': 'K', 'b1': 'G', 'k11': 'k', 'j11': 'g', square: symbol}

    def test_configuration_has_no_diagnostics(self):
        r = subprocess.run([self.engine, 'check', str(CONFIG.resolve())],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([s for s in r.stderr.splitlines() if s and not s.startswith('Parsing variant:')], [])

    def test_setup_inventory_symmetry_and_initial_moves(self):
        board = re.search(r'^startFen = (\S+)', CONFIG.read_text(), re.M)[1].split('/')
        pieces = {}
        for rank, row in zip(range(11, 0, -1), board):
            file = 0
            for token in row.split(','):
                if token.isdigit():
                    file += int(token)
                else:
                    pieces[chr(ord('a') + file) + str(rank)] = token
                    file += 1
            self.assertEqual(file, 11)
        self.assertEqual(len(board), 11)
        self.assertEqual(sum(p.isupper() for p in pieces.values()), 27)
        self.assertEqual(sum(p.islower() for p in pieces.values()), 27)
        inventory = {'k': 1, 'g': 2, 's': 2, 're': 2, 'n': 2, 'l': 2,
                     'b': 1, 'r': 1, 'sh': 1, 'hy': 2, 'ky': 3, 'p': 8}
        for symbol, count in inventory.items():
            self.assertEqual(list(pieces.values()).count(symbol.upper()), count)
            self.assertEqual(list(pieces.values()).count(symbol), count)
        for square, piece in pieces.items():
            reflected = chr(ord('k') - (ord(square[0]) - ord('a'))) + str(12 - int(square[1:]))
            self.assertEqual(pieces[reflected], piece.swapcase())
        self.assertEqual(pieces['b2'], 'B')
        self.assertEqual(pieces['j2'], 'R')
        expected = set()
        for square, piece in pieces.items():
            if piece.isupper():
                expected |= reference_moves(pieces, square, 'w', MOVES[piece.lower()])
        actual = self.moves('startpos')
        self.assertEqual(actual, expected)
        self.assertFalse(any('@' in move for move in actual))

    def test_all_base_and_promoted_movements_both_colours(self):
        for promoted, descriptions in ((False, MOVES), (True, PROMOTED)):
            for symbol, description in descriptions.items():
                for side in ('w', 'b'):
                    with self.subTest(promoted=promoted, piece=symbol, side=side):
                        token = symbol.upper() if side == 'w' else symbol
                        token = ('+' if promoted else '') + token
                        pieces = self.position(token, side)
                        actual = {m.rstrip('+') for m in self.moves(fen(pieces, side)) if m.startswith('f6')}
                        self.assertEqual(actual, reference_moves(pieces, 'f6', side, description))

    def test_optional_entry_inside_and_exit_both_colours(self):
        for side in ('w', 'b'):
            for sr, tr in ((7, 8), (8, 9), (8, 7)):
                if side == 'b':
                    sr, tr = 12 - sr, 12 - tr
                source, target = f'f{sr}', f'f{tr}'
                pieces = self.position('SH' if side == 'w' else 'sh', side, source)
                moves = self.moves(fen(pieces, side))
                self.assertIn(source + target, moves)
                self.assertIn(source + target + '+', moves)
        for symbol in ('K', 'G'):
            self.assertFalse(any(m.startswith('f8') and m.endswith('+')
                                 for m in self.moves(fen(self.position(symbol, square='f8')))))

    def test_all_mandatory_promotion_regions_both_colours(self):
        for symbol, sr, tr, tf in (('p', 10, 11, 'f'), ('l', 10, 11, 'f'),
                                   ('hy', 10, 11, 'g'), ('n', 8, 10, 'g'),
                                   ('n', 9, 11, 'g')):
            for side in ('w', 'b'):
                with self.subTest(piece=symbol, side=side, target=tr):
                    source = f'f{sr if side == "w" else 12-sr}'
                    target = f'{tf}{tr if side == "w" else 12-tr}'
                    pieces = self.position(symbol.upper() if side == 'w' else symbol, side, source)
                    moves = self.moves(fen(pieces, side))
                    self.assertNotIn(source + target, moves)
                    self.assertIn(source + target + '+', moves)

    def test_promoted_aliases_do_not_promote_again(self):
        for symbol in PROMOTED:
            pieces = self.position('+' + symbol.upper(), square='f9')
            self.assertFalse(any(m.startswith('f9') and m.endswith('+') for m in self.moves(fen(pieces))))

    def test_actual_promotion_replaces_movement(self):
        # Hyora -> Silver: backward diagonal steps become available, long slides disappear.
        pieces = self.position('HY', square='f7')
        out = self.moves(fen(pieces), 'f7g8+ j11j10')
        actual = {m for m in out if m.startswith('g8')}
        after = {'a1': 'K', 'b1': 'G', 'k11': 'k', 'j10': 'g', 'g8': '+HY'}
        self.assertEqual(actual, reference_moves(after, 'g8', 'w', PROMOTED['hy']))

    def test_king_capture_no_drops_and_perft_undo(self):
        pieces = {'a1': 'K', 'b1': 'G', 'k11': 'k', 'j11': 'g', 'k10': 'R'}
        out = self.output(fen(pieces), 'k10k11')
        self.assertIn('Nodes searched: 0', out)
        self.assertNotIn('@', out)
        out = self.output(depth=2)
        keys = re.findall(r'(?m)^Key:\s*(\S+)', out)
        self.assertEqual(len(keys), 2, out)
        self.assertEqual(keys[0], keys[1])


if __name__ == '__main__':
    unittest.main()
