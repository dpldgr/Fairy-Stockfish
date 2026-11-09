#!/usr/bin/env python3
"""Range-clearing effects: independent victim oracle, legality and parser checks."""
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import unittest

from range_jumps import DIRECTIONS, fen


class Clearing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'clear.ini'
        text = '''[clear-base]
commoner = k
piece = x:K +x:Q
piece = y:W +y:F
piece = im:W
piece = bl:W
piece = fd:K
piece = zz:W
castling = false
doubleStep = false
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
promotionRegionOptionalWhite = -
promotionRegionOptionalBlack = -
promotionRegionMandatoryWhite = -
promotionRegionMandatoryBlack = -
promotionPolicy = optional:{} mandatory:{}
prohibitedCaptures = x:im
startFen = 7,k/8/8/8/3,X,4/8/8/7,K w - - 0 1
'''
        for ray in ['R', 'B', 'Q', 'fR', 'mR', 'cR']:
            for policy in ['none', 'enemy', 'friend', 'all']:
                text += f'''[clear-{ray}-{policy}:clear-base]
rangeJumpPieces = x:{ray}:{{bl=enemy}}
rangeJumpCapturePolicy = x:{policy}
rangeJumpProhibitedCaptures = x:{{zz}}
'''
        text += '''[clear-reset:clear-Q-all]
rangeJumpCapturePolicy = x:none
rangeJumpProhibitedCaptures = x:{}
[clear-dash:clear-Q-all]
rangeJumpCapturePolicy = -
rangeJumpProhibitedCaptures = -
[clear-overlap:clear-R-all]
piece = x:RD
[clear-royal:clear-mR-all]
commoner = -
king = k
extinctionValue = none
[clear-royal-enemy:clear-royal]
rangeJumpCapturePolicy = x:enemy
[clear-burn:clear-R-all]
burnPassivePieceTypes = {fd}
[clear-burn-active:clear-burn]
burnActivePieceTypes = {x}
commoner = -
king = k
extinctionValue = none
[clear-wall:clear-R-all]
[clear-mobility:clear-R-all]
mobilityRegionWhiteCustomPiece1 = *1 *2 *3 *4 *5 *6
[clear-promotion:clear-cR-all]
promotionRegionOptionalWhite = *
promotionPolicy = optional:{iic} mandatory:{}
pieceDrops = true
capturesToHand = true
[clear-transform:clear-R-all]
transformOnCapturePieces = {y:fd}
[clear-landing:clear-R-all]
rangeJumpProhibitedCaptures = x:{k}
[clear-landing-only:clear-landing]
rangeJumpCapturePolicy = x:none
[clear-ordinary:clear-landing-only]
piece = x:R
'''
        cls.config.write_text(text)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, variant, board, side='w', move='', config=None):
        position = fen(board, side) if isinstance(board, dict) else board
        result = subprocess.run([self.engine, 'load', str(config or self.config)], text=True,
                                input=f'setoption name UCI_Variant value {variant}\nposition fen {position} moves {move}\nd\ngo perft 1\nquit\n',
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Nodes searched:', result.stdout, result.stdout + result.stderr)
        return result.stdout

    @staticmethod
    def moves(out):
        return set(re.findall(r'^(\S+): \d+$', out, re.M))

    @staticmethod
    def position(out):
        return re.search(r'^Fen: (.+)', out, re.M).group(1)

    def assert_result(self, variant, board, move, expected, side='w'):
        out = self.output(variant, board, side)
        self.assertIn(move, self.moves(out), out)
        after = self.output(variant, board, side, move)
        position = self.position(after)
        self.assertEqual(position.split()[0], fen(expected, 'b' if side == 'w' else 'w').split()[0])
        fresh = self.output(variant, position)
        self.assertEqual(re.search(r'^Key: (\S+)', after, re.M).group(1),
                         re.search(r'^Key: (\S+)', fresh, re.M).group(1))
        return position

    def test_random_rays_against_victim_oracle(self):
        rng = random.Random(2701)
        for side in ['w', 'b']:
            for ray, allowed in [('R', [0, 2, 4, 6]), ('B', [1, 3, 5, 7]), ('Q', range(8)), ('fR', [0])]:
                for policy in ['none', 'enemy', 'friend', 'all']:
                    for _ in range(3):
                        d = rng.choice(list(allowed))
                        df, dr = DIRECTIONS[d]
                        if side == 'b': df, dr = -df, -dr
                        path, f, r = [], 3 + df, 4 + dr
                        while 0 <= f < 8 and 1 <= r <= 8:
                            path.append(chr(97 + f) + str(r)); f += df; r += dr
                        board = {'a8': 'k', 'h1': 'K', 'd4': 'X' if side == 'w' else 'x'}
                        for s in path[:-1]: board[s] = rng.choice(['y', 'Y', 'im', 'IM', 'BL' if side == 'w' else 'bl'])
                        to = path[-1]
                        # Choose a legal empty or enemy landing, with at least one screen.
                        if rng.randrange(2): board[to] = 'y' if side == 'w' else 'Y'
                        else: board.pop(to, None)
                        expected = dict(board)
                        for s in path[:-1]:
                            p = board[s]
                            if p.lower() == 'im': continue
                            enemy = p.isupper() != (side == 'w')
                            if policy == 'all' or policy == ('enemy' if enemy else 'friend'): expected.pop(s)
                        expected[to] = expected.pop('d4')
                        with self.subTest(side=side, ray=ray, policy=policy, path=path):
                            self.assert_result(f'clear-{ray}-{policy}', board, 'd4' + to, expected, side)

    def test_immunity_and_landing_bans_do_not_block_crossing(self):
        board = {'a1': 'X', 'b1': 'y', 'c1': 'im', 'd1': 'zz', 'e1': 'Y', 'f1': 'IM', 'g1': 'y', 'h8': 'k', 'a8': 'K'}
        expected = {s: p for s, p in board.items() if s not in ['a1', 'b1', 'd1', 'e1', 'g1']}
        expected['h1'] = 'X'
        self.assert_result('clear-R-all', board, 'a1h1', expected)
        moves = self.moves(self.output('clear-R-all', board))
        self.assertNotIn('a1c1', moves)
        self.assertNotIn('a1d1', moves)
        board['e1'] = 'bl'
        self.assertNotIn('a1h1', self.moves(self.output('clear-R-all', board)))

    def test_default_reset_and_no_screen_preserve_ordinary_moves(self):
        board = {'d4': 'X', 'd5': 'y', 'd6': 'y', 'a8': 'k', 'h1': 'K'}
        for variant in ['clear-reset', 'clear-dash']:
            self.assert_result(variant, board, 'd4d7', {**{s:p for s,p in board.items() if s != 'd4'}, 'd7':'X'})
        board = {'d4': 'X', 'd5': 'y', 'a8': 'k', 'h1': 'K'}
        self.assert_result('clear-R-all', board, 'd4d5', {'d5':'X','a8':'k','h1':'K'})
        # A base leap overlapping a genuine jump uses the effect exactly once.
        self.assert_result('clear-overlap', board, 'd4d6', {'d6':'X','a8':'k','h1':'K'})

    def test_landing_ban_preserves_ordinary_component(self):
        board = {'d4':'X','d5':'y','d7':'k','h1':'K'}
        out = self.output('clear-landing-only', board)
        self.assertNotIn('d4d7', self.moves(out))
        self.assert_result('clear-landing', board, 'd4d8', {'d8':'X','h1':'K'})
        board.pop('d5')
        self.assertIn('d4d7', self.moves(self.output('clear-ordinary', board)))

    def test_royal_threats_from_quiet_clearing_and_self_removal(self):
        board = {'d4':'x','d6':'K','h8':'k'}
        out = self.output('clear-royal-enemy', board)
        self.assertRegex(out, r'Checkers: d4')
        self.assertNotIn('d6d5', self.moves(out))
        self.assertIn('d6c6', self.moves(out))
        board = {'d4':'X','d6':'K','h8':'k'}
        self.assertNotIn('d4d7', self.moves(self.output('clear-royal', board)))

    def test_burn_mobility_and_static_walls(self):
        board = {'d4':'X','d6':'fd','h8':'k','h1':'K'}
        self.assert_result('clear-burn', board, 'd4d7', {'d7':'X','h8':'k','h1':'K'})
        board['d6'] = 'im'; board['e7'] = 'fd'
        expected = {s:p for s,p in board.items() if s != 'd4'}
        self.assert_result('clear-burn', board, 'd4d7', expected)
        self.assertNotIn('d4d7', self.moves(self.output('clear-mobility', board)))
        board['d6'] = '*'
        self.assertNotIn('d4d7', self.moves(self.output('clear-wall', board)))
        # Clearing the passive burner permits the source's active burn on arrival.
        out = self.output('clear-burn-active', {'d4':'x','d6':'FD','e7':'K','h8':'k'})
        self.assertRegex(out, r'Checkers: d4')

    def test_effect_does_not_trigger_capture_promotion_or_transformation(self):
        board = {'d4':'X','d5':'y','h8':'k','h1':'K'}
        self.assert_result('clear-transform', board, 'd4d7', {'d7':'X','h8':'k','h1':'K'})
        self.assert_result('clear-transform', board, 'd4d5fd', {'d5':'FD~','h8':'k','h1':'K'})
        board['d7'] = 'y'
        out = self.output('clear-promotion', board)
        self.assertIn('d4d7+', self.moves(out))
        after = self.output('clear-promotion', board, move='d4d7+')
        # Only the direct landing victim enters the hand; crossed victim is destroyed.
        self.assertRegex(self.position(after), r'\[Y\]')

    def test_invalid_and_inherited_options(self):
        for setting in ['rangeJumpCapturePolicy = x:bogus', 'rangeJumpCapturePolicy = nope:all',
                        'rangeJumpCapturePolicy = x:all x:none', 'rangeJumpCapturePolicy = y:enemy',
                        'rangeJumpProhibitedCaptures = x:k', 'rangeJumpProhibitedCaptures = x:{missing}']:
            path = Path(self.temp.name) / 'bad.ini'
            path.write_text(self.config.read_text() + '\n[bad:clear-R-all]\n' + setting + '\n')
            result = subprocess.run([self.engine, 'check', str(path)], capture_output=True, text=True, timeout=60)
            self.assertRegex(result.stderr, r'(rangeJump|Range-jump)', setting + result.stderr)

    def test_quiet_and_capture_modalities(self):
        board = {'d4':'X', 'd5':'y', 'd7':'y', 'h8':'k', 'h1':'K'}
        quiet = self.moves(self.output('clear-mR-all', board))
        capture = self.moves(self.output('clear-cR-all', board))
        self.assertIn('d4d6', quiet)
        self.assertNotIn('d4d7', quiet)
        self.assertNotIn('d4d6', capture)
        self.assertIn('d4d7', capture)
        self.assert_result('clear-mR-all', board, 'd4d6', {'d6':'X','d7':'y','h8':'k','h1':'K'})

    def test_long_ray_high_slot(self):
        slots = int(os.environ.get('PIECE_SLOTS', '64'))
        if os.environ.get('BOARD_SIZE') != '19' or slots < 128:
            self.skipTest('19x19 build with a wide piece catalogue only')
        path = Path(self.temp.name) / 'long.ini'
        path.write_text(f'''[long-clearing]
maxFile = 19
maxRank = 19
commoner = k
customPiece1 = lo:W
customPiece{slots - 40} = im:W
customPiece{slots - 39} = hx:K
castling = false
rangeJumpPieces = hx:Q:{{}}
rangeJumpCapturePolicy = hx:all
rangeJumpProhibitedCaptures = hx:{{k}}
prohibitedCaptures = hx:im
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
''')
        for diagonal in [False, True]:
            board = {'s1':'K', 'a19':'k', 'a1':'HX'}
            for i in range(2, 19):
                s = chr(96 + i) + str(i) if diagonal else 'a' + str(i)
                board[s] = 'LO' if i % 2 else 'lo'
            immune = 'j10' if diagonal else 'a10'
            board[immune] = 'im'
            to = 's19' if diagonal else 'a19'
            expected = {'s1':'K', immune:'im', to:'HX'}
            if diagonal: expected['a19'] = 'k'
            else:
                # Avoid landing on the prohibited royal, while retaining 17 victims.
                board['a19'] = 'lo'; board['s19'] = 'k'; expected['s19'] = 'k'
            root = self.output('long-clearing', fen(board, size=19), config=path)
            self.assertIn('a1' + to, self.moves(root))
            after = self.output('long-clearing', fen(board, size=19), move='a1' + to, config=path)
            self.assertEqual(self.position(after).split()[0], fen(expected, size=19).split()[0])
            fresh = self.output('long-clearing', self.position(after), config=path)
            self.assertEqual(re.search(r'^Key: (\S+)', after, re.M).group(1),
                             re.search(r'^Key: (\S+)', fresh, re.M).group(1))


if __name__ == '__main__':
    unittest.main()
