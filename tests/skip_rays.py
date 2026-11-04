#!/usr/bin/env python3
"""Initial ray skips: independent square-walk oracle and engine integration."""
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

DIRS = rj.DIRECTIONS


def oracle(board, origin, side, components, prohibited=(), region=None):
    result = set()
    for directions, skip, limit, mode in components:
        for d in directions:
            df, dr = DIRS[d]
            if side == 'b':
                df, dr = -df, -dr
            f, r = ord(origin[0]) - 97, int(origin[1:])
            for distance in range(1, 9):
                f, r = f + df, r + dr
                if not (0 <= f < 8 and 1 <= r <= 8) or (limit and distance > limit):
                    break
                to = chr(97 + f) + str(r)
                pc = board.get(to)
                if pc == '*':
                    break
                if distance <= skip:
                    continue
                enemy = pc and pc.isupper() != (side == 'w')
                if ((not pc and mode != 'c') or (enemy and mode != 'm' and pc.lower() not in prohibited)):
                    if region is None or to in region:
                        result.add(origin + to)
                if pc:
                    break
    return result


class SkipRays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'skip.ini'
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
        for name, betza in [('rook', 'jR'), ('two', 'j2R5'), ('bishop', 'j2B'),
                            ('queen', 'jQ'), ('quiet', 'mj2Q5'), ('capture', 'cj2Q5'),
                            ('forward', 'fjR4'), ('hybrid', 'Rj2B'),
                            ('overlap', 'jR3j3R'), ('zero', 'j0R'), ('empty', 'j3R2'),
                            ('tetrarch', 'jBjfbRjrlR3')]:
            text += f'\n[{name}:base]\npiece = s:{betza}\n'
        text += '''
[limited:rook]
mobilityRegionWhiteCustomPiece2 = d6 d7
[prohibited:rook]
prohibitedCaptures = s:x
[igui:queen]
lionMovePieces = s:0804020180402010
[promote:two]
piece = s:j2R +s:jB
promotionRegionMandatoryWhite = *
promotionPolicy = optional:{} mandatory:{ii}
[drop:two]
pieceDrops = true
capturesToHand = true
[royal:rook]
commoner = -
king = k
extinctionValue = none
[royal-two:royal]
piece = s:j2R
[castle:chess]
piece = s:jR
[skip-king:chess]
king = k:j2R
[legacy:base]
customPiece2 = s:cjB
[burn:queen]
burnActivePieceTypes = {s}
[freeze:queen]
piece = z:K
freezeEffectPieces = {z}
'''
        if int(os.environ.get('BOARD_SIZE', '8')) >= 19:
            text += '\n[big:base]\nmaxFile = 19\nmaxRank = 19\npiece = s:j10R15\n'
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

    @classmethod
    def command(cls, commands):
        cls.engine.stdin.write(commands)
        cls.engine.stdin.flush()
        output = []
        ready = False
        perft = 'go perft' not in commands
        while True:
            line = cls.lines.get(timeout=90)
            if line is None:
                raise AssertionError('Engine exited: ' + ''.join(output))
            output.append(line)
            ready |= line.strip() == 'readyok'
            perft |= 'Nodes searched:' in line
            if ready and perft:
                return ''.join(output)

    @classmethod
    def tearDownClass(cls):
        if cls.engine.poll() is None:
            cls.engine.stdin.write('quit\n')
            cls.engine.stdin.flush()
            cls.engine.wait(timeout=10)
        cls.engine.stdin.close()
        cls.engine.stdout.close()
        cls.reader.join(timeout=5)
        cls.temp.cleanup()

    def output(self, variant, board=None, side='w', moves='', commands='d\ngo perft 1\n'):
        setup = ''
        if variant != self.current:
            setup = f'setoption name UCI_Variant value {variant}\n'
            self.__class__.current = variant
        position = board if isinstance(board, str) else rj.fen({'h1': 'K', 'h8': 'k', **(board or {})}, side)
        return self.command(setup + f'position fen {position} moves {moves}\n' + commands + 'isready\n')

    def moves(self, *args, **kwargs):
        out = self.output(*args, **kwargs)
        self.assertIn('Nodes searched:', out)
        moves = re.findall(r'^(\S+): \d+$', out, re.M)
        self.assertEqual(len(moves), len(set(moves)), out)
        return moves

    def test_random_square_walk_oracle(self):
        rules = {
            'rook': [(range(0, 8, 2), 1, 0, '')],
            'two': [(range(0, 8, 2), 2, 5, '')],
            'bishop': [(range(1, 8, 2), 2, 0, '')],
            'queen': [(range(8), 1, 0, '')],
            'quiet': [(range(8), 2, 5, 'm')],
            'capture': [(range(8), 2, 5, 'c')],
            'forward': [((0,), 1, 4, '')],
            'hybrid': [(range(0, 8, 2), 0, 0, ''), (range(1, 8, 2), 2, 0, '')],
            'overlap': [(range(0, 8, 2), 1, 3, ''), (range(0, 8, 2), 3, 0, '')],
            'zero': [(range(0, 8, 2), 0, 0, '')],
            'empty': [(range(0, 8, 2), 3, 2, '')],
            'tetrarch': [(range(1, 8, 2), 1, 0, ''), ((0, 4), 1, 0, ''), ((2, 6), 1, 3, '')],
        }
        rng = random.Random(401184)
        squares = [chr(97 + f) + str(r) for f in range(8) for r in range(1, 9)
                   if chr(97 + f) + str(r) not in ('d4', 'h1', 'h8')]
        for variant, components in rules.items():
            for side in ('w', 'b'):
                for case in range(3):
                    board = {'h1': 'K', 'h8': 'k', 'd4': 'S' if side == 'w' else 's'}
                    for square in rng.sample(squares, 16):
                        board[square] = rng.choice(('x', 'X', '*'))
                    with self.subTest(variant=variant, side=side, case=case):
                        actual = {m for m in self.moves(variant, board, side) if m.startswith('d4')}
                        self.assertEqual(actual, oracle(board, 'd4', side, components))

    def test_ignored_pieces_stay_and_next_piece_stops(self):
        board = {'d4': 'S', 'd5': 'x', 'd6': 'X', 'd7': 'x', 'd8': 'x'}
        moves = self.moves('two', board)
        self.assertIn('d4d7', moves)
        self.assertNotIn('d4d5', moves)
        self.assertNotIn('d4d6', moves)
        self.assertNotIn('d4d8', moves)
        out = self.output('two', board, moves='d4d7', commands='d\n')
        self.assertIn('Fen:', out)
        actual = re.search(r'^Fen: (.*)', out, re.M).group(1)
        expected = rj.fen({'h1': 'K', 'h8': 'k', 'd5': 'x', 'd6': 'X', 'd7': 'S', 'd8': 'x'}, 'b')
        self.assertEqual(actual.split()[0], expected.split()[0].replace(',', ''))

    def test_wall_inside_ignored_prefix_is_opaque(self):
        moves = self.moves('two', {'d4': 'S', 'd5': '*', 'd8': 'x'})
        self.assertNotIn('d4d7', moves)
        self.assertNotIn('d4d8', moves)

    def test_mobility_and_prohibited_capture(self):
        board = {'d4': 'S', 'd5': 'X'}
        self.assertEqual({m for m in self.moves('limited', board) if m.startswith('d4')}, {'d4d6', 'd4d7'})
        board.update({'d6': 'x', 'd8': 'x'})
        moves = self.moves('prohibited', board)
        self.assertNotIn('d4d6', moves)
        self.assertNotIn('d4d8', moves)

    def test_source_end_skip_in_native_check_and_evasions(self):
        board = {'h1': None, 'a1': 'K', 'a4': 's', 'a3': 'X'}
        out = self.output('royal', board)
        self.assertIn('a4', re.search(r'^Checkers: *(.*)', out, re.M).group(1))
        moves = self.moves('royal', board)
        self.assertIn('a1b1', moves)
        self.assertNotIn('a1a2', moves)
        self.assertNotIn('a3b3', moves)

    def test_reverse_skip_does_not_create_a_false_check(self):
        board = {'h1': None, 'a1': 'K', 'a4': 's', 'a2': 'X'}
        out = self.output('royal', board)
        self.assertEqual(re.search(r'^Checkers: *(.*)', out, re.M).group(1), '')
        self.assertNotIn('a2b2', self.moves('royal', board))

    def test_castling_through_skip_attack(self):
        board = {'e1': 'K', 'h1': 'R', 'a8': 'k', 'f4': 's', 'f3': 'P'}
        position = rj.fen(board).replace(' w - - ', ' w K - ')
        self.assertNotIn('e1g1', self.moves('castle', position))
        board.pop('f3'); board['f2'] = 'P'
        position = rj.fen(board).replace(' w - - ', ' w K - ')
        self.assertIn('e1g1', self.moves('castle', position))

    def test_en_passant_cannot_expose_skip_ray(self):
        position = rj.fen({'h5': 'K', 'h8': 'k', 'a5': 's', 'b5': 'p', 'c5': 'P'}).replace(' w - - ', ' w - b6 ')
        self.assertNotIn('c5b6', self.moves('castle', position))

    def test_igui_remains_separate_from_ray_moves(self):
        moves = self.moves('igui', {'d4': 'S', 'd5': 'x'})
        self.assertIn('d4d5d4', moves)
        self.assertNotIn('d4d5', moves)
        self.assertIn('d4d6', moves)

    def test_promoted_form_uses_its_own_skip(self):
        out = self.output('promote', {'d4': 'S'}, moves='d4d7+', commands='d\ngo perft 1\n')
        self.assertIn('+S', re.search(r'^Fen: (.*)', out, re.M).group(1))
        # Let Black move before enumerating White's promoted piece.
        out = self.output('promote', {'d4': 'S'}, moves='d4d7+ h8h7')
        actual = {m for m in re.findall(r'^(\S+): \d+$', out, re.M) if m.startswith('d7')}
        self.assertIn('d7f5', actual)
        self.assertNotIn('d7e6', actual)

    def test_native_king_and_single_slot_custom_definition(self):
        position = rj.fen({'h8': 'k', 'd4': 'K', 'd5': 'P', 'd6': 'P', 'd7': 'p'})
        moves = self.moves('skip-king', position)
        self.assertIn('d4d7', moves)
        self.assertNotIn('d4d5', moves)
        self.assertNotIn('d4d6', moves)
        board = {'h1': 'K', 'h8': 'k', 'd4': 'S', 'e5': 'X', 'f6': 'x'}
        self.assertEqual({m for m in self.moves('legacy', board) if m.startswith('d4')}, {'d4f6'})

    def test_burn_freeze_and_drops(self):
        board = {'d4': 'S', 'd5': 'x', 'e6': 'x'}
        out = self.output('burn', board, moves='d4d6', commands='d\n')
        self.assertEqual(re.search(r'^Fen: (.*)', out, re.M).group(1).split()[0], '7k/8/3S4/8/8/8/8/7K')
        self.assertFalse(any(m.startswith('d4') for m in self.moves('freeze', {'d4': 'S', 'e5': 'z'})))
        position = rj.fen({'h1': 'K', 'h8': 'k', 'd5': 'x'}).replace(' w ', '[S] w ')
        moves = self.moves('drop', position)
        self.assertIn('S@d4', moves)
        out = self.output('drop', position, moves='S@d4 h8h7')
        self.assertIn('d4d7: 1', out)
        self.assertNotIn('d4d5: 1', out)

    def test_multidigit_skip_and_range(self):
        if int(os.environ.get('BOARD_SIZE', '8')) < 19:
            self.skipTest('19x19 build')
        board = {'b2': 'S', 'b3': 'X', 'b12': 'x', 's19': 'k', 'a1': 'K'}
        position = rj.fen(board, size=19)
        moves = {m for m in self.moves('big', position) if m.startswith('b2')}
        self.assertEqual(moves, {'b2b13', 'b2b14', 'b2b15', 'b2b16', 'b2b17', 'b2m2', 'b2n2', 'b2o2', 'b2p2', 'b2q2'})

    def test_invalid_syntax_rejected(self):
        path = Path(self.temp.name) / 'invalid.ini'
        path.write_text(''.join(f'[{name}:base]\npiece = s:{betza}\n' for name, betza in
                                [('bad-leaper', 'jN'), ('bad-hop', 'jpR'), ('bad-sign', 'j-2R'),
                                 ('bad-overflow', 'j999999999999999R'), ('bad-tail', 'Rj')]))
        # Include base before malformed children.
        path.write_text(self.config.read_text() + path.read_text())
        result = subprocess.run([self.binary, 'load', str(path)], input='uci\nquit\n', capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0)
        self.assertIn('piece -', result.stderr)
        for name in ('bad-leaper', 'bad-hop', 'bad-sign', 'bad-overflow', 'bad-tail'):
            self.assertNotIn(' var ' + name, result.stdout)


if __name__ == '__main__':
    unittest.main()
