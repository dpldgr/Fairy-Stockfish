#!/usr/bin/env python3
"""Burn timing and complete Tenjiku area routes through the real engine."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest


def fen(pieces, side='w', size=8):
    rows = []
    for rank in range(size, 0, -1):
        row, empty = [], 0
        for file in (chr(ord('a') + f) for f in range(size)):
            piece = pieces.get(file + str(rank))
            if piece:
                if empty:
                    row.append(str(empty))
                    empty = 0
                row.append(piece)
            else:
                empty += 1
        if empty:
            row.append(str(empty))
        rows.append(','.join(row))
    return '/'.join(rows) + f' {side} - - 0 1'


class Tenjiku(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'tenjiku.ini'
        cls.config.write_text('''[area]
commoner = k
piece = fd:K
piece = vg:W
piece = wb:W +wb:<fd>
piece = r:<rook>
piece = g:<gold>
piece = v:W +v:<g>
piece = ft:<immobile>
castling = false
doubleStep = false
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
tenjikuTripleStepPieceTypes = {fd,vg}
startFen = 7,k/8/8/8/3,FD,4/8/8/7,K w - - 0 1
[burn:area]
burnActivePieceTypes = {fd}
burnPassivePieceTypes = {fd,ft}
[active:burn]
burnPassivePieceTypes = {}
[passive:burn]
burnActivePieceTypes = -
[clear:burn]
burnActivePieceTypes = {}
burnPassivePieceTypes = -
tenjikuTripleStepPieceTypes = {}
[prohibited:area]
prohibitedCaptures = fd:v
[trade:area]
tradingRule = fd:[any,{v}]
[mobility:area]
mobilityRegionWhiteCustomPiece1 = d4 d5 e5 e6
[promote:burn]
promotedPieceType = fd:g
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{iicu} mandatory:{iicp}
[mandatory:promote]
promotionPolicy = optional:{} mandatory:{iic}
[choices:area]
piece = d:K
queen = q
rook = r
tenjikuTripleStepPieceTypes = {d}
promotionPawnTypes = d
promotionPieceTypes = q r
promotionRegionMandatoryWhite = *
promotionRegionOptionalWhite = -
promotionPolicy = optional:{} mandatory:{iic}
[royal:burn]
commoner = -
king = k
extinctionValue = none
[area-royal:area]
commoner = -
king = k
extinctionValue = none
[tower:passive]
tenjikuTripleStepPieceTypes = {}
[immobile-area:area]
tenjikuTripleStepPieceTypes = {ft}
immobilityIllegal = true
[pawn-area:area]
pawn = p
tenjikuTripleStepPieceTypes = {p}
promotionRegionOptionalWhite = -
promotionRegionMandatoryWhite = -
[promote-limit:mandatory]
promotionLimit = g:1
[trade-conditional:area]
tradingRule = fd:[any!,{v}]
''')

        if os.environ.get('TENJIKU_BURN_ONLY'):
            cls.config.write_text(re.sub(r'^tenjikuTripleStepPieceTypes = .*$',
                                         'tenjikuTripleStepPieceTypes = {}',
                                         cls.config.read_text(), flags=re.M))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, variant='burn', pieces=None, moves='', side='w', depth=1, commands=None):
        position = pieces if isinstance(pieces, str) else fen({'h1': 'K', 'h8': 'k', **(pieces or {'d4': 'FD'})}, side)
        result = subprocess.run([self.engine, 'load', str(self.config)],
                                input=f'setoption name UCI_Variant value {variant}\n'
                                      f'position fen {position} moves {moves}\n'
                                      + (commands or f'd\ngo perft {depth}\n') + 'quit\n',
                                capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def moves(self, *args, **kwargs):
        output = self.output(*args, **kwargs)
        self.assertIn('Nodes searched:', output)
        return re.findall(r'^(\S+): \d+$', output, re.M)

    def final(self, *args, **kwargs):
        output = self.output(*args, **kwargs)
        return re.search(r'^Fen: (.+)', output, re.M).group(1), re.search(r'^Key: (\S+)', output, re.M).group(1)

    def assert_fresh_key(self, variant, pieces, move):
        final, key = self.final(variant, pieces, move)
        fresh, fresh_key = self.final(variant, final)
        self.assertEqual(key, fresh_key)
        self.assertEqual(final, fresh)
        return final

    def test_configuration_has_no_parser_errors(self):
        result = subprocess.run([self.engine, 'check', str(self.config)], input='quit\n',
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn(' - ', result.stderr)

    def test_unsupported_rule_combinations_are_rejected(self):
        path = Path(self.temp.name) / 'unsupported.ini'
        for option in ('blastOnCapture = true', 'seirawanGating = true',
                       'wallingRule = duck', 'flipEnclosedPieces = ataxx'):
            path.write_text(self.config.read_text() + '\n[unsupported:burn]\n' + option + '\n')
            result = subprocess.run([self.engine, 'load', str(path)], input='uci\nquit\n',
                                    text=True, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0)
            self.assertRegex(result.stderr, 'Unsupported combination|requires Seirawan gating')
            self.assertNotIn(' var unsupported', result.stdout)

    def test_area_requires_wide_move_build(self):
        if not os.environ.get('TENJIKU_BURN_ONLY'):
            self.skipTest('32-bit move build only')
        path = Path(self.temp.name) / 'requires-wide.ini'
        path.write_text(self.config.read_text() + '\n[requires-wide:area]\ntenjikuTripleStepPieceTypes = {fd}\n')
        result = subprocess.run([self.engine, 'load', str(path)], input='uci\nquit\n',
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertIn('Requires a 64-bit move build', result.stderr)
        self.assertNotIn(' var requires-wide', result.stdout)

    def test_all_routes_both_colours_and_immobile_base(self):
        for piece in ('FD', 'VG', 'fd', 'vg'):
            side = 'w' if piece.isupper() else 'b'
            moves = [m for m in self.moves('area', {'d4': piece}, side=side) if m.startswith('d4')]
            self.assertEqual(len(moves), 584)
            self.assertEqual(len(set(moves)), 584)
            self.assertEqual([sum(len(m) == n for m in moves) for n in (4, 6, 8)], [8, 64, 512])
            self.assertIn('d4d5d4c3', moves)
            self.assertIn('d4e4d4', moves)
            self.assertNotIn('d4d6d7', moves)

    def test_stop_on_first_capture_at_every_leg(self):
        for square, present, absent in (
            ('d5', 'd4d5', ('d4d5d6', 'd4d5d6d7')),
            ('d6', 'd4d5d6', ('d4d5d6d7',)),
            ('d7', 'd4d5d6d7', ())):
            moves = self.moves('area', {'d4': 'FD', square: 'v'})
            self.assertIn(present, moves)
            for move in absent:
                self.assertNotIn(move, moves)

    def test_area_can_attach_to_pawn_and_immobile_types(self):
        for variant, piece in (('pawn-area', 'P'), ('immobile-area', 'FT')):
            with self.subTest(variant=variant):
                moves = [m for m in self.moves(variant, {'d4': piece}) if m.startswith('d4')]
                self.assertEqual(len(moves), 584)
                self.assertEqual(len(set(moves)), 584)

    def test_conditional_trading_on_every_leg(self):
        for square, move in (('d5', 'd4d5'), ('d6', 'd4d5d6'), ('d7', 'd4d5d6d7')):
            self.assertNotIn(move, self.moves('trade-conditional', {'d4': 'FD', square: 'v', 'd8': 'r'}))
            self.assertIn(move, self.moves('trade-conditional', {'d4': 'FD', square: 'v'}))

    def test_edges_friends_walls_and_mobility(self):
        moves = self.moves('area', {'a1': 'FD', 'h1': 'K', 'h8': 'k'})
        self.assertEqual(sum(m.startswith('a1') and len(m) == 4 for m in moves), 3)
        for blocker in ('V', '*'):
            moves = self.moves('area', {'d4': 'FD', 'd5': blocker})
            self.assertNotIn('d4d5', moves)
            self.assertNotIn('d4d5e6', moves)
            self.assertNotIn('d4d5e6f7', moves)
        moves = self.moves('mobility')
        self.assertIn('d4d5e5e6', moves)
        self.assertNotIn('d4e4e5e6', moves)

    def test_prohibited_and_trading_captures_apply_to_all_legs(self):
        for variant in ('prohibited', 'trade'):
            for square, move in (('d5', 'd4d5'), ('d6', 'd4d5d6'), ('d7', 'd4d5d6d7')):
                self.assertNotIn(move, self.moves(variant, {'d4': 'FD', square: 'v'}))

    def test_burn_final_only_and_friends_survive(self):
        pieces = {'d4': 'FD', 'c5': 'v', 'c7': 'v', 'e7': 'V'}
        final = self.assert_fresh_key('active', pieces, 'd4d5d6d7')
        self.assertEqual(final.split()[0].count('v'), 1)
        self.assertIn('V', final)
        self.assertIn('FD', final)

    def test_passive_before_active_and_no_cascade(self):
        pieces = {'d4': 'FD', 'e6': 'fd', 'c5': 'v'}
        final = self.assert_fresh_key('burn', pieces, 'd4d5')
        self.assertNotIn('FD', final)
        self.assertIn('fd', final)
        self.assertIn('v', final)
        # Passive-only towers never sweep neighbours on an unrelated move.
        final, _ = self.final('tower', {'a1': 'V', 'd4': 'FD', 'e5': 'ft'}, 'a1a2')
        self.assertIn('FD', final)

    def test_capture_burner_and_another_surviving_burner(self):
        for other in (False, True):
            pieces = {'d4': 'FD', 'd5': 'fd', **({'e6': 'ft'} if other else {})}
            final = self.assert_fresh_key('burn', pieces, 'd4d5')
            self.assertNotIn('fd', final)
            self.assertEqual('FD' in final, not other)
            if other:
                self.assertIn('ft', final)

    def test_passive_only_on_arrival_and_active_only_when_moving(self):
        pieces = {'d4': 'FD', 'f5': 'ft', 'c5': 'v'}
        final, _ = self.final('burn', pieces, 'd4e5d5c6')
        self.assertIn('FD', final)
        self.assertNotIn('v', final)
        self.assertIn('ft', final)
        final, _ = self.final('passive', {'d4': 'FD', 'c5': 'v'}, 'd4d5')
        self.assertIn('v', final)

    def test_water_buffalo_promotion_has_no_active_burn(self):
        # Give WB its own capture-only optional promotion rule.
        path = Path(self.temp.name) / 'wb.ini'
        original = self.config
        path.write_text(original.read_text() + '''\n[wb:burn]
promotionRegionOptionalWhite = *
promotionPolicy = optional:{iic} mandatory:{}
''')
        self.config = path
        try:
            pieces = {'d4': 'WB', 'd5': 'v', 'c6': 'v'}
            final = self.assert_fresh_key('wb', pieces, 'd4d5+')
            self.assertIn('+WB', final)
            self.assertEqual(final.split()[0].count('v'), 1)
        finally:
            self.config = original

    def test_burn_bycatch_never_triggers_promotion(self):
        moves = self.moves('promote', {'d4': 'FD', 'c6': 'v'})
        self.assertIn('d4d5', moves)
        self.assertNotIn('d4d5+', moves)
        # Capture the unpromoted v directly: optional; promoted v: mandatory.
        for victim, mandatory in (('v', False), ('+v', True)):
            pieces = {'d4': 'FD', 'd7': victim}
            moves = self.moves('promote', pieces)
            self.assertIn('d4d5d6d7+', moves)
            self.assertEqual('d4d5d6d7' in moves, not mandatory)
            self.assert_fresh_key('promote', pieces, 'd4d5d6d7+')

    def test_mover_burned_before_mandatory_promotion(self):
        pieces = {'d4': 'FD', 'd7': 'v', 'e7': 'ft'}
        self.assertIn('d4d5d6d7', self.moves('mandatory', pieces))
        self.assertNotIn('d4d5d6d7+', self.moves('mandatory', pieces))
        final = self.assert_fresh_key('mandatory', pieces, 'd4d5d6d7')
        self.assertNotIn('FD', final)
        self.assertNotIn('+FD', final)
        self.assertNotIn('v', final)
        self.assertIn('ft', final)

    def test_no_promotion_limit_blocks_a_move_that_dies(self):
        pieces = {'d4': 'FD', 'd7': 'v', 'e7': 'ft', 'a1': 'G'}
        self.assertIn('d4d5d6d7', self.moves('promote-limit', pieces))
        self.assertNotIn('d4d5d6d7+', self.moves('promote-limit', pieces))

    def test_burning_and_undo_for_black(self):
        pieces = {'d5': 'fd', 'c3': '+V', 'e3': 'V'}
        final = self.assert_fresh_key('burn', fen({'h1': 'K', 'h8': 'k', **pieces}, 'b'), 'd5d4')
        self.assertNotIn('V', final)
        self.assertIn('fd', final)

    def test_search_can_win_through_a_quiet_burn(self):
        position = fen({'h1': 'K', 'e6': 'k', 'd4': 'FD'})
        with subprocess.Popen([self.engine, 'load', str(self.config)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as engine:
            timer = threading.Timer(45, engine.kill)
            timer.start()
            try:
                engine.stdin.write('setoption name UCI_Variant value burn\n'
                                   f'position fen {position}\ngo depth 2 searchmoves d4d5\n')
                engine.stdin.flush()
                output = []
                for line in engine.stdout:
                    output.append(line)
                    if line.startswith('bestmove'):
                        break
                engine.stdin.write('quit\n')
                engine.stdin.flush()
                engine.wait(timeout=10)
                self.assertEqual(engine.returncode, 0, ''.join(output) + engine.stderr.read())
                self.assertIn('bestmove d4d5', ''.join(output))
                self.assertIn('score mate 1', ''.join(output))
            finally:
                timer.cancel()

    def test_three_leg_pawn_style_promotions_preserve_route(self):
        moves = self.moves('choices', {'d4': 'D', 'd7': 'v'})
        self.assertIn('d4d5d6d7q', moves)
        self.assertIn('d4d5d6d7r', moves)
        self.assertNotIn('d4d5d6d7', moves)
        for p in ('q', 'r'):
            self.assert_fresh_key('choices', {'d4': 'D', 'd7': 'v'}, 'd4d5d6d7' + p)

    def test_royal_extinction_by_burn(self):
        final, _ = self.final('burn', {'d4': 'FD', 'e6': 'k', 'h8': None}, 'd4d5')
        self.assertNotIn('k', final.split()[0])
        self.assertFalse(self.moves('burn', final))

    def test_area_and_burn_check_evasions(self):
        pieces = {'a1': 'K', 'a4': 'fd', 'h8': 'k', 'h1': None}
        moves = self.moves('area-royal', pieces)
        self.assertNotIn('a1a2', moves)  # enemy area mover reaches it
        # Burning the checking rook is an evasion even with a quiet destination.
        path = Path(self.temp.name) / 'royal.ini'
        original = self.config
        path.write_text(original.read_text() + '\n[royal-rook:royal]\nrook = r\n')
        self.config = path
        try:
            pieces = {'a1': 'K', 'a8': 'r', 'b5': 'FD', 'h1': None}
            self.assertIn('b5b6b7', self.moves('royal-rook', pieces))
        finally:
            self.config = original

    def test_inheritance_clears_all_sets(self):
        self.assertEqual(len([m for m in self.moves('clear') if m.startswith('d4')]), 8)
        final, _ = self.final('clear', {'d4': 'FD', 'e6': 'ft', 'c6': 'v'}, 'd4d5')
        self.assertIn('FD', final)
        self.assertIn('v', final)

    def test_high_slot_on_full_19x19_board(self):
        if os.environ.get('BOARD_SIZE') != '19' or int(os.environ.get('PIECE_SLOTS', '64')) < 128:
            self.skipTest('19x19 build with a wide piece catalogue only')
        last = int(os.environ['PIECE_SLOTS']) - 39
        path = Path(self.temp.name) / 'high-slot.ini'
        path.write_text(f'''[high-area]
maxFile = 19
maxRank = 19
commoner = k
gold = g
customPiece1 = v:W
customPiece{last} = hx:K
castling = false
tenjikuTripleStepPieceTypes = {{hx}}
burnActivePieceTypes = {{hx}}
burnPassivePieceTypes = {{hx}}
promotedPieceType = hx:g v:g
promotionRegionOptionalWhite = -
promotionRegionMandatoryWhite = *
promotionPolicy = optional:{{}} mandatory:{{iicp}}
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
''')
        original = self.config
        self.config = path
        try:
            position = fen({'s1': 'K', 's19': 'k', 'j10': 'HX'}, size=19)
            moves = [m for m in self.moves('high-area', position) if m.startswith('j10')]
            self.assertEqual(len(moves), 584)
            self.assertEqual(len(set(moves)), 584)
            position = fen({'s1': 'K', 's19': 'k', 'j10': 'HX', 'j13': '+v', 'i13': 'v'}, size=19)
            self.assertIn('j10j11j12j13+', self.moves('high-area', position))
            final = self.assert_fresh_key('high-area', position, 'j10j11j12j13+')
            self.assertIn('+HX', final)
            self.assertNotIn('v', final)
            position = fen({'s1': 'K', 'a19': 'k', 's19': 'HX'}, size=19)
            moves = [m for m in self.moves('high-area', position) if m.startswith('s19')]
            self.assertTrue(moves)
            self.assertNotIn('s19t19', moves)
        finally:
            self.config = original

    def test_large_move_list_and_exact_perft_undo(self):
        pieces = {'b4': 'VG', 'd4': 'VG', 'f4': 'VG', 'd6': 'v', 'd7': '+v'}
        moves = self.moves('burn', pieces)
        self.assertGreater(len(moves), 1024)
        output = self.output('burn', pieces, commands='d\ngo perft 2\nd\n')
        self.assertEqual(*re.findall(r'^Key: (\S+)', output, re.M))
        self.assertEqual(*re.findall(r'^Fen: (.+)', output, re.M))


if __name__ == '__main__':
    if os.environ.get('TENJIKU_BURN_ONLY'):
        cases = ('configuration_has_no_parser_errors', 'area_requires_wide_move_build',
                 'passive_before_active_and_no_cascade', 'capture_burner_and_another_surviving_burner',
                 'water_buffalo_promotion_has_no_active_burn', 'inheritance_clears_all_sets',
                 'burning_and_undo_for_black', 'search_can_win_through_a_quiet_burn')
        result = unittest.TextTestRunner().run(unittest.TestSuite(Tenjiku('test_' + name) for name in cases))
        raise SystemExit(not result.wasSuccessful())
    unittest.main()
