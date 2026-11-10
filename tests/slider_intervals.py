#!/usr/bin/env python3
"""Block-policy slider intervals: square-walk oracle and engine integration."""
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
from count_selectors import oracle as special_oracle

R = (0, 2, 4, 6)
B = (1, 3, 5, 7)
Q = tuple(range(8))
# Atom, ordinary interval terms (directions, minimum, maximum, modality).
SPECS = {
    'queen': ('Q[3..8]', [(Q, 3, 8, '')]),
    'quiet': ('mQ[3..8]', [(Q, 3, 8, 'm')]),
    'capture': ('cQ[3..8]', [(Q, 3, 8, 'c')]),
    'rook': ('R[2..5]', [(R, 2, 5, '')]),
    'bishop': ('B[2..4]', [(B, 2, 4, '')]),
    'exact': ('Q[3]', [(Q, 3, 3, '')]),
    'equal': ('Q[3..3]', [(Q, 3, 3, '')]),
    'forward': ('fR[2..5]', [((0,), 2, 5, '')]),
    'back-diagonal': ('bB[2..5]', [((3, 5), 2, 5, '')]),
    'side': ('rlR[2..4]', [((2, 6), 2, 4, '')]),
    'modal': ('mR[2..5]cB[3]', [(R, 2, 5, 'm'), (B, 3, 3, 'c')]),
    'overlap': ('Q[2..4]R[3..6]', [(Q, 2, 4, ''), (R, 3, 6, '')]),
    'full-union': ('Q[3]Q', [(Q, 1, 99, '')]),
    'disjoint': ('R[2]R[4..6]', [(R, 2, 2, ''), (R, 4, 6, '')]),
    'regular': ('Q[3..4]R2B', [(Q, 3, 4, ''), (R, 1, 2, ''), (B, 1, 99, '')]),
    'legacy-q': ('Q3', [(Q, 1, 3, '')]),
    'legacy-r': ('R3', [(R, 1, 3, '')]),
    'legacy-b': ('B3', [(B, 1, 3, '')]),
    'one-q': ('Q[1..3]', [(Q, 1, 3, '')]),
    'one-r': ('R[1..3]', [(R, 1, 3, '')]),
    'one-b': ('B[1..3]', [(B, 1, 3, '')]),
    'large': ('Q[3..2147483647]', [(Q, 3, 2147483647, '')]),
    'impossible': ('R[2147483647]', [(R, 2147483647, 2147483647, '')]),
    'skip': ('R[3..4]j5R7', [(R, 3, 4, '')]),
    'cannon': ('R[3..4]cpR', [(R, 3, 4, '')]),
    'grass': ('R[3..4]gR', [(R, 3, 4, '')]),
    'policy-profile': ('R[3]j2R3', [(R, 3, 3, '')]),
    'lame': ('Q[3..4]nD', [(Q, 3, 4, ''), (R, 2, 2, '')]),
    'counted': ('mR[3..4]cp[1,3]R', [(R, 3, 4, 'm')]),
    'bounded': ('R2R[5..6]cpR', [(R, 1, 2, ''), (R, 5, 6, '')]),
    'knight': ('Q[3..4]N', [(Q, 3, 4, '')]),
}
SPECIAL = {
    'skip': [('j', {5}, R, '', 7)],
    'cannon': [('p', {1}, R, 'c', 0)],
    'grass': [('p', {1}, R, '', 1)],
    'policy-profile': [('j', {2}, R, '', 3)],
    'counted': [('p', {1, 3}, R, 'c', 0)],
    'bounded': [('p', {1}, R, 'c', 0)],
}


def oracle(board, origin, side, terms, size=8):
    result = set()
    for directions, minimum, maximum, mode in terms:
        for direction in directions:
            df, dr = rj.DIRECTIONS[direction]
            if side == 'b':
                df, dr = -df, -dr
            f, r = ord(origin[0]) - 97, int(origin[1:])
            for distance in range(1, size):
                f, r = f + df, r + dr
                if not (0 <= f < size and 1 <= r <= size) or distance > maximum:
                    break
                to = chr(97 + f) + str(r)
                pc = board.get(to)
                if pc == '*':
                    break
                enemy = pc and pc.isupper() != (side == 'w')
                if distance >= minimum and ((not pc and mode != 'c') or (enemy and mode != 'm')):
                    result.add(origin + to)
                if pc:
                    break
    return result


class IntervalSliders(unittest.TestCase):
    command = classmethod(sr.SkipRays.command.__func__)
    output = sr.SkipRays.output
    moves = sr.SkipRays.moves
    tearDownClass = classmethod(sr.SkipRays.tearDownClass.__func__)

    @classmethod
    def setUpClass(cls):
        cls.binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'intervals.ini'
        text = '''[base]
commoner = k
piece = x:W
castling = false
doubleStep = false
extinctionValue = loss
extinctionPieceTypes = k
extinctionPseudoRoyal = false
nMoveRule = 0
'''
        for name, (atom, _) in SPECS.items():
            text += f'\n[{name}:base]\npiece = s:{atom}\n'
        text += '''
[royal:queen]
commoner = -
king = k
extinctionValue = none
[royal-mixed:royal]
piece = s:R[3..4]cpR
[castle:chess]
piece = s:cR[3..5]
[prohibited:queen]
prohibitedCaptures = s:x
[limited:queen]
mobilityRegionWhiteCustomPiece2 = d7 d8
[promote:queen]
piece = s:Q[3..5] +s:B[3]
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{} mandatory:{ii}
[last:base]
piece = s:fmR[3] +s:K
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{last} mandatory:{}
[initial:base]
doubleStep = true
doubleStepRegionWhite = *1
doubleStepRegionBlack = *8
piece = s:WimR[3]
[burn:queen]
burnActivePieceTypes = {s}
[freeze:queen]
piece = z:K
freezeEffectPieces = {z}
'''
        if int(os.environ.get('BOARD_SIZE', '8')) >= 19:
            text += '\n[big:base]\nmaxFile = 19\nmaxRank = 19\npiece = s:R[10..18]B[17]\n'
        cls.config.write_text(text)
        cls.engine = subprocess.Popen([cls.binary, 'load', str(cls.config)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.lines = queue.Queue()
        def read():
            for line in cls.engine.stdout:
                cls.lines.put(line)
            cls.lines.put(None)
        cls.reader = threading.Thread(target=read, daemon=True)
        cls.reader.start()
        cls.current = None
        startup = cls.command('isready\n')
        if 'piece -' in startup:
            raise AssertionError(startup)

    def test_random_oracle(self):
        rng = random.Random(88413)
        squares = [chr(97 + f) + str(r) for f in range(8) for r in range(1, 9)
                   if chr(97 + f) + str(r) not in ('d4', 'h1', 'h8')]
        for name, (_, terms) in SPECS.items():
            for side in ('w', 'b'):
                for case in range(4):
                    board = {'d4': 'S' if side == 'w' else 's', 'h1': 'K', 'h8': 'k'}
                    for sq in rng.sample(squares, 14):
                        board[sq] = rng.choice(('x', 'X', '*'))
                    expected = oracle(board, 'd4', side, terms)
                    if name in SPECIAL:
                        expected |= special_oracle(board, 'd4', side, SPECIAL[name])
                    if name == 'knight':
                        for df, dr in ((a, b) for a in (-2, -1, 1, 2) for b in (-2, -1, 1, 2) if abs(a) != abs(b)):
                            f, r = 3 + df, 4 + dr
                            if 0 <= f < 8 and 1 <= r <= 8:
                                sq = chr(97 + f) + str(r)
                                pc = board.get(sq)
                                if pc != '*' and (not pc or pc.isupper() != (side == 'w')):
                                    expected.add('d4' + sq)
                    with self.subTest(name=name, side=side, case=case):
                        self.assertEqual({m for m in self.moves(name, board, side) if m.startswith('d4')}, expected)

    def test_blocked_prefix_and_terminal_capture(self):
        for pc in ('x', 'X', '*'):
            for sq in ('d5', 'd6'):
                moves = self.moves('queen', {'d4': 'S', sq: pc, 'd8': 'x'})
                self.assertNotIn('d4d7', moves)
                self.assertNotIn('d4d8', moves)
        moves = self.moves('queen', {'d4': 'S', 'd7': 'x', 'd8': 'x'})
        self.assertIn('d4d7', moves)
        self.assertNotIn('d4d8', moves)

    def test_exact_and_legacy(self):
        board = {'a1': 'S'}
        for name in ('exact', 'equal'):
            self.assertEqual({m for m in self.moves(name, board) if m.startswith('a1')}, {'a1a4', 'a1d1', 'a1d4'})
        self.assertIn('a1a2', self.moves('legacy-q', board))
        for atom in ('q', 'r', 'b'):
            self.assertEqual(self.moves('legacy-' + atom, board), self.moves('one-' + atom, board))

    def test_masks_do_not_leak_between_terms(self):
        board = {'a1': 'S', 'a6': 'x'}
        self.assertNotIn('a1a6', self.moves('cannon', board))
        self.assertNotIn('a1a8', self.moves('bounded', {'a1': 'S', 'a8': 'x'}))
        self.assertNotIn('a1a3', self.moves('skip', {'a1': 'S'}))
        self.assertIn('a1a7', self.moves('skip', {'a1': 'S', 'a2': 'X'}))

    def test_native_checks_pins_and_evasions(self):
        board = {'h1': None, 'a1': 'K', 'a4': 's'}
        out = self.output('royal', board)
        self.assertIn('a4', re.search(r'^Checkers: *(.*)', out, re.M)[1])
        self.assertIn('a1a2', self.moves('royal', board))  # Inside the forbidden landing distance.
        self.assertNotIn('a1b2', self.moves('royal', {'h1': None, 'a1': 'K', 'e5': 's'}))
        board['a2'] = 'X'
        self.assertNotIn('a2b2', self.moves('royal', board))
        self.assertIn('a2a3', self.moves('royal', board))
        for name in ('royal', 'royal-mixed'):
            out = self.output(name, {'h1': None, 'a1': 'K', 'a3': 's'})
            self.assertEqual(re.search(r'^Checkers: *(.*)', out, re.M)[1], '')

    def test_prohibition_mobility_freeze_and_burn(self):
        self.assertNotIn('d4d7', self.moves('prohibited', {'d4': 'S', 'd7': 'x'}))
        self.assertEqual({m for m in self.moves('limited', {'d4': 'S'}) if m.startswith('d4')}, {'d4d7', 'd4d8'})
        self.assertFalse(any(m.startswith('d4') for m in self.moves('freeze', {'d4': 'S', 'c4': 'z'})))
        out = self.output('burn', {'d4': 'S', 'e7': 'x'}, moves='d4d7', commands='d\n')
        board = re.search(r'^Fen: (.*)', out, re.M)[1].split()[0]
        self.assertNotIn('x', board)

    def test_promotion_immobility_and_initial(self):
        self.assertIn('a1a4+', self.moves('promote', {'a1': 'S'}))
        self.assertNotIn('a1a4', self.moves('promote', {'a1': 'S'}))
        self.assertIn('a3a6+', self.moves('last', {'a3': 'S'}))
        self.assertNotIn('a1a4+', self.moves('last', {'a1': 'S'}))
        self.assertIn('a1a4+', self.moves('last', {'a1': 'S', 'a6': '*'}))
        self.assertIn('a1a4', self.moves('initial', {'a1': 'S'}))
        out = self.output('initial', {'a1': 'S'}, moves='a1a4 h8g8')
        self.assertNotIn('a4a7:', out)
        self.assertIn('a4a5:', out)

    def test_castling_attack(self):
        board = {'e1': 'K', 'h1': 'R', 'a8': 'k', 'f4': 's'}
        position = rj.fen(board).replace(' w - - ', ' w K - ')
        self.assertNotIn('e1g1', self.moves('castle', position))
        board['f3'] = 'P'
        position = rj.fen(board).replace(' w - - ', ' w K - ')
        self.assertIn('e1g1', self.moves('castle', position))

    def test_large_board(self):
        if int(os.environ.get('BOARD_SIZE', '8')) < 19:
            self.skipTest('requires 19x19')
        board = {'a1': 'S', 's1': 'K', 's19': 'k', 'a15': 'x'}
        actual = {m for m in self.moves('big', rj.fen(board, size=19)) if m.startswith('a1')}
        self.assertEqual(actual, oracle(board, 'a1', 'w', [(R, 10, 18, ''), (B, 17, 17, '')], size=19))
        self.assertIn('a1r18', actual)
        self.assertIn('a1a15', actual)
        self.assertNotIn('a1a16', actual)

    def test_invalid_syntax(self):
        forms = ('Q[]', 'Q[0]', 'Q[0..3]', 'Q[4..3]', 'Q[3..]', 'Q[..3]', 'Q[1,3]',
                 'Q[1..2..3]', 'Q[3', 'Q3]', 'Q[3]]', 'Q[-1]', 'Q[+3]', 'Q[3]2',
                 'Q[99999999999999999999]', 'Q[3..2147483648]', 'Q[3][4]',
                 'jQ[3]', 'pQ[3]', 'gQ[3]', 'nQ[3]', 'N[3]', '(2,1)[3]')
        path = Path(self.temp.name) / 'invalid.ini'
        path.write_text(self.config.read_text() + ''.join(
            f'\n[bad{i}:base]\npiece = s:{atom}\n' for i, atom in enumerate(forms)))
        p = subprocess.run([self.binary, 'load', str(path)], input='uci\nquit\n',
                           text=True, capture_output=True, timeout=90)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for i in range(len(forms)):
            self.assertNotRegex(p.stdout, r' var bad' + str(i) + r'(?: |\n)')
        self.assertIn('piece -', p.stderr)


if __name__ == '__main__':
    unittest.main()
