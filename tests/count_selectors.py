#!/usr/bin/env python3
"""Independent coordinate oracle for exact/mixed p and j count selectors."""
import os
from pathlib import Path
import queue
import random
import re
import subprocess
import tempfile
import threading
import unittest

import range_jumps as rj
import skip_rays as sr

R = (0, 2, 4, 6)
B = (1, 3, 5, 7)
Q = tuple(range(8))
# kind, allowed counts, directions, modality, range (1 is legacy grasshopper for p)
SPECS = {
    'exact': ('cp2R', [('p', {2}, R, 'c', 0)]),
    'list': ('cp[1,3]R', [('p', {1, 3}, R, 'c', 0)]),
    'range': ('cp[1..3]R', [('p', {1, 2, 3}, R, 'c', 0)]),
    'mixed': ('cp[1,3..4]R', [('p', {1, 3, 4}, R, 'c', 0)]),
    'combined': ('Rcp[1..3]R', [('p', {0}, R, '', 0), ('p', {1, 2, 3}, R, 'c', 0)]),
    'bounded-base': ('R2cp3R', [('p', {0}, R, '', 2), ('p', {3}, R, 'c', 0)]),
    'bounded-quiet': ('mR2mp3R', [('p', {0}, R, 'm', 2), ('p', {3}, R, 'm', 0)]),
    'zero': ('p0R', [('p', {0}, R, '', 0)]),
    'zero-range': ('p[0..2]R', [('p', {0, 1, 2}, R, '', 0)]),
    'quiet': ('mp[1,3]B', [('p', {1, 3}, B, 'm', 0)]),
    'bishop': ('p2B', [('p', {2}, B, '', 0)]),
    'queen': ('cp[1..3]Q', [('p', {1, 2, 3}, Q, 'c', 0)]),
    'forward': ('cp[1..3]fR', [('p', {1, 2, 3}, (0,), 'c', 0)]),
    'limited': ('p[1,3]R6', [('p', {1, 3}, R, '', 6)]),
    'grass': ('p2R1', [('p', {2}, R, '', 1)]),
    'plain': ('pR', [('p', {1}, R, '', 0)]),
    'repeated': ('cppR', [('p', {1}, R, 'c', 0)]),
    'grass-legacy': ('pR1', [('p', {1}, R, '', 1)]),
    'one': ('p[1]R', [('p', {1}, R, '', 0)]),
    'single': ('cp[2..2]R', [('p', {2}, R, 'c', 0)]),
    'duplicates': ('cp[1,1,2..3,2]R', [('p', {1, 2, 3}, R, 'c', 0)]),
    'large': ('cp[0..2147483647]R', [('p', set(range(8)), R, 'c', 0)]),
    'empty': ('cp100R', [('p', {100}, R, 'c', 0)]),
    'j-list': ('cj[1,3]R', [('j', {1, 3}, R, 'c', 0)]),
    'j-range': ('j[1..3]B', [('j', {1, 2, 3}, B, '', 0)]),
    'j-mixed': ('j[1,3..4]Q6', [('j', {1, 3, 4}, Q, '', 6)]),
    'j-zero': ('j[0,2]R', [('j', {0, 2}, R, '', 0)]),
    'overlap': ('p2Rcp[1..3]Rj[1,3]R', [('p', {2}, R, '', 0), ('p', {1, 2, 3}, R, 'c', 0), ('j', {1, 3}, R, '', 0)]),
}


def oracle(board, origin, side, components):
    result = set()
    for kind, counts, dirs, mode, limit in components:
        for direction in dirs:
            df, dr = rj.DIRECTIONS[direction]
            if side == 'b':
                df, dr = -df, -dr
            for skip in (counts if kind == 'j' else (0,)):
                f, r = ord(origin[0]) - 97, int(origin[1:])
                screens, last_screen = 0, 0
                for distance in range(1, 9):
                    f, r = f + df, r + dr
                    if not (0 <= f < 8 and 1 <= r <= 8):
                        break
                    if limit and not (kind == 'p' and limit == 1 and counts != {0}) and distance > limit:
                        break
                    to = chr(97 + f) + str(r)
                    pc = board.get(to)
                    if pc == '*':
                        break
                    if kind == 'j' and distance <= skip:
                        continue
                    permitted = kind == 'j' or screens in counts
                    if kind == 'p' and limit == 1 and screens and distance != last_screen + 1:
                        permitted = False
                    enemy = pc and pc.isupper() != (side == 'w')
                    if permitted and ((not pc and mode != 'c') or (enemy and mode != 'm')):
                        result.add(origin + to)
                    if pc:
                        if kind == 'j':
                            break
                        screens += 1
                        last_screen = distance
    return result


class CountSelectors(unittest.TestCase):
    # Reuse the established synchronous protocol/FEN helpers, not their oracle.
    command = classmethod(sr.SkipRays.command.__func__)
    tearDownClass = classmethod(sr.SkipRays.tearDownClass.__func__)
    output = sr.SkipRays.output
    moves = sr.SkipRays.moves

    @classmethod
    def setUpClass(cls):
        cls.binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'counts.ini'
        text = '''[base]
commoner = k
piece = x:W
piece = a:cpR
castling = false
doubleStep = false
extinctionValue = loss
extinctionPieceTypes = k
extinctionPseudoRoyal = false
nMoveRule = 0
'''
        for name, (betza, _) in SPECS.items():
            text += f'\n[{name}:base]\npiece = h:{betza}\n'
        text += '''
[royal:exact]
commoner = -
king = k
extinctionValue = none
[double:royal]
lionMovePieces = x(FFFFFFFFFFFFFFFF)
[drop:exact]
pieceDrops = true
capturesToHand = true
[promotion:exact]
piece = h:p2R +h:j[1,3..4]R
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{} mandatory:{ii}
[last:base]
piece = h:fp2R +h:W
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionRegionMandatoryWhite = -
promotionRegionMandatoryBlack = -
promotionPolicy = optional:{last} mandatory:{}
[initial:base]
piece = h:ip2R
doubleStep = true
doubleStepRegionWhite = *
doubleStepRegionBlack = *
'''
        if int(os.environ.get('BOARD_SIZE', '8')) >= 19:
            text += '''
[big:base]
maxFile = 19
maxRank = 19
piece = h:cp[1,3..4]R
'''
        cls.config.write_text(text)
        cls.engine = subprocess.Popen([cls.binary, 'load', str(cls.config)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.lines = queue.Queue()
        def reader():
            for line in cls.engine.stdout:
                cls.lines.put(line)
            cls.lines.put(None)
        cls.reader = threading.Thread(target=reader, daemon=True)
        cls.reader.start()
        cls.current = None
        out = cls.command('setoption name Use NNUE value false\nisready\n')
        assert 'piece -' not in out, out

    def test_screen_intervals_and_sets(self):
        board = {'a4': 'H', 'c4': 'X', 'e4': 'x', 'f4': 'x', 'g4': 'x', 'h4': 'x'}
        self.assertEqual({m for m in self.moves('list', board) if m.startswith('a4')}, {'a4e4', 'a4g4'})
        self.assertEqual({m for m in self.moves('range', board) if m.startswith('a4')}, {'a4e4', 'a4f4', 'a4g4'})
        self.assertEqual({m for m in self.moves('mixed', board) if m.startswith('a4')}, {'a4e4', 'a4g4', 'a4h4'})

    def test_randomized_coordinate_oracle(self):
        rng = random.Random(20261108)
        squares = [chr(97 + f) + str(r) for f in range(8) for r in range(1, 9)
                   if chr(97 + f) + str(r) not in ('d4', 'h1', 'h8')]
        for name, (_, components) in SPECS.items():
            for side in ('w', 'b'):
                for trial in range(12):
                    board = {'h1': 'K', 'h8': 'k', 'd4': 'H' if side == 'w' else 'h'}
                    for square in rng.sample(squares, 24):
                        board[square] = rng.choice(('x', 'X') if name in ('plain', 'repeated', 'grass-legacy') else ('x', 'X', '*'))
                    with self.subTest(name=name, side=side, trial=trial):
                        moves = self.moves(name, board, side)
                        actual = {m for m in moves if m.startswith('d4')}
                        self.assertEqual(actual, oracle(board, 'd4', side, components))
                        self.assertEqual(len(moves), len(set(moves)))

    def test_adding_and_removing_screens_in_check(self):
        checked = {'a1': 'K', 'h8': 'k', 'a8': 'h', 'a3': 'X', 'a5': 'X'}
        out = self.output('royal', rj.fen(checked))
        self.assertIn('a8', re.search(r'^Checkers: *(.*)', out, re.M)[1])
        self.assertIn('a3b3', self.moves('royal', rj.fen(checked)))
        adding = {'a1': 'K', 'h8': 'k', 'a8': 'h', 'a3': 'X', 'b5': 'X'}
        self.assertNotIn('b5a5', self.moves('royal', rj.fen(adding)))
        removing = {'a1': 'K', 'h8': 'k', 'a8': 'h', 'a2': 'X', 'a3': 'X', 'a4': 'X'}
        self.assertNotIn('a3b3', self.moves('royal', rj.fen(removing)))
        king = {'a2': 'K', 'h8': 'k', 'h1': 'h', 'd1': 'X', 'f1': 'x'}
        self.assertNotIn('a2a1', self.moves('royal', rj.fen(king)))
        self.assertIn('a2b2', self.moves('royal', rj.fen(king)))

    def test_nonking_double_check_evasion(self):
        board = {'a1': 'K', 'h8': 'k', 'a8': 'h', 'a5': 'a', 'a3': 'X', 'b5': 'X'}
        out = self.output('double', rj.fen(board))
        checkers = re.search(r'^Checkers: *(.*)', out, re.M)[1].split()
        self.assertEqual(set(checkers), {'a5', 'a8'})
        self.assertIn('b5a5b5', self.moves('double', rj.fen(board)))

    def test_promotion_drop_and_initial_quiet(self):
        board = {'d4': 'H', 'd5': 'X', 'd6': 'x'}
        out = self.output('promotion', board, moves='d4d7+', commands='d\n')
        self.assertIn('+H', re.search(r'^Fen: (.*)', out, re.M)[1])
        initial = {m for m in self.moves('initial', board) if m.startswith('d4')}
        self.assertEqual(initial, oracle({'h1': 'K', 'h8': 'k', **board}, 'd4', 'w', [('p', {2}, R, 'm', 0)]))
        fen = rj.fen({'h1': 'K', 'h8': 'k', 'b1': 'X', 'c1': 'x', 'd1': 'x'})
        fen = fen.replace(' w ', '[H] w ')
        self.assertIn('H@a1', self.moves('drop', fen))
        after = self.output('drop', fen, moves='H@a1 h8g8')
        self.assertIn('a1d1:', after)

    def test_last_uses_possible_future_screens_and_walls(self):
        self.assertIn('a3a6+', self.moves('last', {'a3': 'H', 'a4': 'x', 'a5': 'X'}))
        self.assertNotIn('a2a5+', self.moves('last', {'a2': 'H', 'a3': 'x', 'a4': 'X'}))
        self.assertIn('a2a5+', self.moves('last', {'a2': 'H', 'a3': 'x', 'a4': 'X', 'a8': '*'}))

    def test_long_multiword_ray(self):
        if int(os.environ.get('BOARD_SIZE', '8')) < 19:
            self.skipTest('requires 19x19')
        board = {'a1': 'H', 'a6': 'X', 'a9': 'x', 'a13': 'x', 'a16': 'x', 'a19': 'x', 's1': 'K', 's19': 'k'}
        actual = {m for m in self.moves('big', rj.fen(board, size=19)) if m.startswith('a1')}
        self.assertEqual(actual, {'a1a9', 'a1a16', 'a1a19'})

    def test_classical_search_preserves_root(self):
        fen = rj.fen({'a1': 'K', 'h8': 'k', 'a8': 'h', 'a3': 'X', 'a5': 'X'})
        legal = set(self.moves('royal', fen))
        before = self.command('d\nisready\n')
        self.engine.stdin.write('go depth 3\n')
        self.engine.stdin.flush()
        output = []
        while True:
            line = self.lines.get(timeout=90)
            self.assertIsNotNone(line, ''.join(output))
            output.append(line)
            if line.startswith('bestmove '):
                self.assertIn(line.split()[1], legal)
                break
        self.assertIn('info depth 3 ', ''.join(output))
        after = self.command('d\nisready\n')
        for label in ('Fen', 'Key', 'Checkers'):
            self.assertEqual(re.search(r'^' + label + r': *(.*)', before, re.M)[1],
                             re.search(r'^' + label + r': *(.*)', after, re.M)[1])

    def test_invalid_selectors_are_rejected(self):
        forms = ('p[]R', 'p[1,]R', 'p[1,,2]R', 'p[3..1]R', 'p[1..]R', 'p[1,3R',
                 'p-2R', 'p{1,3}R', 'p999999999999999R', 'p[2]N', 'p[2]',
                 'j[]R', 'j[1,]R', 'j[3..1]R', 'j[1,3R', 'j[2]N', 'jp2R')
        path = Path(self.temp.name) / 'invalid.ini'
        path.write_text(self.config.read_text() + ''.join(
            f'\n[bad{i}:base]\npiece = h:{betza}\n' for i, betza in enumerate(forms)))
        result = subprocess.run([self.binary, 'load', str(path)], input='uci\nquit\n', capture_output=True,
                                text=True, timeout=90)
        self.assertEqual(result.returncode, 0)
        for i in range(len(forms)):
            self.assertNotIn(' var bad' + str(i) + ' ', result.stdout)
            self.assertNotRegex(result.stdout, r' var bad' + str(i) + r'\n')
        self.assertIn('piece -', result.stderr)


if __name__ == '__main__':
    unittest.main()
