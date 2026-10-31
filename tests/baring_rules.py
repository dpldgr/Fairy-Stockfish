#!/usr/bin/env python3
"""Baring adjudication, reply timing, search, and inherited royal selection."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest


RULES = '''
[baring:chess]
baringRule = true
castling = false
nMoveRule = 0
[baring-win:baring]
baringValue = win
[baring-draw:baring]
baringValue = draw
[baring-disabled:baring]
baringRule = false
[baring-mate-win:baring]
checkmateValue = win
[baring-stalemate-loss:baring]
stalemateValue = loss
[baring-immobile:baring-stalemate-loss]
mobilityRegionBlackKing = a8

[capture-baring]
piece = k:<commoner> +k:<em>
piece = em:U
piece = r:<rook>
piece = tr:W
castling = false
nMoveRule = 0
baringRule = true
extinctionValue = loss
extinctionCondition = and(k=0,em=0)
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{iiq} mandatory:{}
startFen = 7,k/7,r/8/8/8/8/R,7/K,7 w - - 0 1
[capture-baring-win:capture-baring]
baringValue = win
[capture-baring-draw:capture-baring]
baringValue = draw
[explicit:capture-baring]
baringRuleRoyalTypes = {k}
[auto:explicit]
baringRuleRoyalTypes = auto
[auto-grandchild:auto]
extinctionCondition = tr=0
[pseudo:capture-baring]
extinctionPseudoRoyal = true
baringRuleRoyalTypes = {k,em}
[legacy-auto:capture-baring]
extinctionCondition = -
extinctionPieceTypes = k
[ambiguous:capture-baring]
extinctionCondition = or(k=0,em=0)
baringRule = false

[treasure:baring]
piece = tr:W
piece = em:U
extinctionValue = loss
extinctionPieceTypes = {tr}
baringValue = win
baringRuleRoyalTypes = {k}
startFen = 7,k/7,tr/8/8/8/8/R,7/K,TR,6 w - - 0 1
[treasure-auto:treasure]
baringRuleRoyalTypes = auto
[pockets:baring]
pieceDrops = true
capturesToHand = true
'''


def fen(pieces, side='w', flip=False, pocket=''):
    if flip:
        pieces = {chr(ord('h') - (ord(s[0]) - ord('a'))) + str(9 - int(s[1])):
                  p.swapcase() for s, p in pieces.items()}
        side = 'b' if side == 'w' else 'w'
        pocket = pocket.swapcase()
    rows = []
    for rank in range(8, 0, -1):
        cells, empty = [], 0
        for file in 'abcdefgh':
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
    return '/'.join(rows) + (f'[{pocket}]' if pocket else '') + f' {side} - - 0 1'


def flip_move(move):
    return ''.join(chr(ord('h') - (ord(c) - ord('a'))) if c.isalpha()
                   else str(9 - int(c)) if c.isdigit() else c for c in move)


class BaringRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        compiler = subprocess.run([cls.engine, 'compiler'], text=True, capture_output=True, timeout=30)
        slots = re.search(r'piece_slots=(\d+)', compiler.stdout)
        cls.slots = int(slots[1]) if slots else 64
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'baring.ini'
        cls.config.write_text(RULES)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, variant, position, command='go perft 1', config=None):
        with subprocess.Popen([self.engine, 'load', str(config or self.config)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) as engine:
            timer = threading.Timer(60, engine.kill)
            timer.start()
            try:
                engine.stdin.write(f'setoption name UCI_Variant value {variant}\n'
                                   f'position fen {position}\n{command}\n')
                engine.stdin.flush()
                lines = []
                for line in engine.stdout:
                    lines.append(line)
                    if line.startswith('bestmove ') or line.startswith('Nodes searched:'):
                        break
                engine.stdin.write('quit\n')
                engine.stdin.flush()
                _, errors = engine.communicate(timeout=10)
                self.assertEqual(engine.returncode, 0, errors + ''.join(lines))
                return ''.join(lines)
            finally:
                timer.cancel()

    def nodes(self, variant, position, config=None):
        out = self.output(variant, position, config=config)
        match = re.search(r'Nodes searched:\s*(\d+)', out)
        self.assertIsNotNone(match, out)
        return int(match[1])

    def assert_reply_score(self, variant, position, move, kind, value):
        out = self.output(variant, position, f'go depth 1 searchmoves {move}')
        self.assertRegex(out, rf'info depth 1 .*score {kind} {value}(?: |\n)')
        self.assertRegex(out, rf'bestmove {re.escape(move)}(?: |\n)')

    def test_one_reply_then_loss_both_colours(self):
        pieces = {'d4': 'K', 'c5': 'R', 'd6': 'k'}
        for flip in (False, True):
            with self.subTest(flip=flip):
                position = fen(pieces, 'b', flip)
                self.assertGreater(self.nodes('baring', position), 0)
                self.assert_reply_score('baring', position, flip_move('d6e6') if flip else 'd6e6', 'mate', -1)

    def test_counter_baring_draw_in_every_mode_both_colours(self):
        for variant in ('baring', 'baring-win', 'baring-draw'):
            for flip in (False, True):
                with self.subTest(variant=variant, flip=flip):
                    self.assert_reply_score(variant, fen({'e3': 'K', 'c5': 'R', 'd6': 'k'}, 'b', flip),
                                            flip_move('d6c5') if flip else 'd6c5', 'cp', 0)

    def test_bare_reply_outcome_modes(self):
        position = fen({'d4': 'K', 'c5': 'R', 'd6': 'k'}, 'b')
        self.assert_reply_score('baring-win', position, 'd6e6', 'mate', 1)
        self.assert_reply_score('baring-draw', position, 'd6e6', 'cp', 0)

    def test_search_extends_the_reply_at_a_quiescence_leaf(self):
        position = fen({'e3': 'K', 'c5': 'R', 'd6': 'k', 'b5': 'r'})
        self.assert_reply_score('baring', position, 'c5b5', 'mate', 1)
        self.assert_reply_score('baring-win', position, 'c5b5', 'mate', -1)

    def test_builtin_shatranj_baring(self):
        position = fen({'e3': 'K', 'c5': 'R', 'd6': 'k'}, 'b')
        self.assert_reply_score('shatranj', position, 'd6c5', 'cp', 0)
        self.assert_reply_score('shatranj', position, 'd6e6', 'mate', -1)

    def test_royal_capture_precedes_bare_loss_and_extinction(self):
        for variant, kind, value in (('capture-baring', 'mate', 1),
                                     ('capture-baring-win', 'mate', -1),
                                     ('capture-baring-draw', 'cp', 0)):
            for flip in (False, True):
                with self.subTest(variant=variant, flip=flip):
                    self.assert_reply_score(variant, fen({'d4': 'EM', 'h8': 'k', 'a8': 'r'}, flip=flip),
                                            flip_move('d4h8') if flip else 'd4h8', kind, value)

    def test_disabled_rule_and_ongoing_armies(self):
        position = fen({'a1': 'K', 'a2': 'R', 'h8': 'k'})
        self.assertEqual(self.nodes('baring', position), 0)
        self.assertGreater(self.nodes('baring-disabled', position), 0)
        self.assertGreater(self.nodes('baring', fen({'a1': 'K', 'a2': 'R', 'h8': 'k', 'h7': 'r'})), 0)

    def test_promotion_and_promoted_fen_keep_royalty(self):
        position = fen({'a1': 'K', 'a2': 'R', 'h8': 'k', 'h7': 'r'})
        out = self.output('capture-baring', position, 'go perft 1')
        self.assertIn('a1b1+:', out)
        self.assertGreater(self.nodes('capture-baring', fen({'b1': '+K', 'a2': 'R', 'h8': 'k', 'h7': 'r'})), 0)

    def test_explicit_auto_and_grandchild_recomputation(self):
        position = fen({'a1': 'K', 'a2': 'R', 'h8': 'em', 'h7': 'r'}, 'b')
        self.assertEqual(self.nodes('explicit', position), 0)
        self.assertGreater(self.nodes('auto', position), 0)
        self.assertEqual(self.nodes('auto-grandchild', position), 0)

    def test_legacy_auto_and_pseudo_royals(self):
        for variant in ('legacy-auto', 'pseudo'):
            position = fen({'e3': 'K', 'c5': 'R', 'd6': 'k'}, 'b')
            self.assert_reply_score(variant, position, 'd6c5', 'cp', 0)

    def test_mixed_treasure_extinction_is_independent(self):
        for variant in ('treasure', 'treasure-auto'):
            position = fen({'a1': 'K', 'b1': 'TR', 'h1': 'R', 'h8': 'k', 'h7': 'tr'})
            self.assert_reply_score(variant, position, 'h1h7', 'mate', 1)

    def test_checkmate_and_stalemate_keep_their_results(self):
        mate = fen({'a8': 'k', 'c6': 'K', 'b7': 'Q'}, 'b')
        stalemate = fen({'a8': 'k', 'c6': 'K', 'b6': 'Q'}, 'b')
        self.assertEqual(self.nodes('baring', mate), 0)
        self.assertEqual(self.nodes('baring', stalemate), 0)
        # A lone Emperor mates a pseudo-royal king: mate beats mutual-baring draw.
        out = self.output('pseudo', fen({'a8': 'k', 'd4': 'EM'}, 'b'), 'go depth 1')
        self.assertIn('score mate 0', out)
        # Likewise, an immobile lone native king uses the configured stalemate result.
        out = self.output('baring-immobile', fen({'a8': 'k', 'c6': 'K'}, 'b'), 'go depth 1')
        self.assertIn('score mate 0', out)

    def test_pieces_in_hand_prevent_baring(self):
        position = fen({'a1': 'K', 'a2': 'R', 'h8': 'k'}, pocket='p')
        self.assertGreater(self.nodes('pockets', position), 0)

    def test_royal_types_above_the_first_piece_set_word(self):
        if self.slots < 128:
            self.skipTest('requires at least 128 piece slots')
        config = Path(self.temp.name) / 'high-slot.ini'
        config.write_text('''
[high-slot]
commoner = k
rook = r
customPiece70 = em:U
castling = false
baringRule = true
extinctionValue = loss
extinctionCondition = and(k=0,em=0)
startFen = 7,k/7,r/8/8/8/8/R,7/K,7 w - - 0 1
[high-explicit:high-slot]
baringRuleRoyalTypes = {em}
''')
        position = fen({'d4': 'EM', 'a1': 'R', 'h8': 'em', 'a8': 'r'})
        for variant in ('high-slot', 'high-explicit'):
            self.assertGreater(self.nodes(variant, position, config), 0)
        king_only = fen({'d4': 'EM', 'a1': 'R', 'h8': 'k', 'a8': 'r'}, 'b')
        self.assertGreater(self.nodes('high-slot', king_only, config), 0)
        self.assertEqual(self.nodes('high-explicit', king_only, config), 0)

    def test_invalid_settings_and_ambiguous_auto_are_diagnosed(self):
        for option, value, diagnostic in (
                ('baringRuleRoyalTypes', '{k,unknown}', 'Expected auto or a nonempty piece set'),
                ('baringRuleRoyalTypes', '{k,}', 'Expected auto or a nonempty piece set'),
                ('baringRuleRoyalTypes', '*', 'Expected auto or a nonempty piece set'),
                ('baringValue', 'none', 'Expected win, loss, or draw'),
                ('baringValue', 'garbage', 'Expected win, loss, or draw')):
            with self.subTest(option=option, value=value):
                config = Path(self.temp.name) / 'invalid.ini'
                config.write_text(RULES + f'\n[invalid:explicit]\n{option} = {value}\n')
                result = subprocess.run([self.engine, 'check', str(config)], capture_output=True, text=True, timeout=30)
                self.assertIn(diagnostic, result.stderr)
                self.assertEqual(self.nodes('invalid', fen({'a1': 'K', 'a2': 'R', 'h8': 'em', 'h7': 'r'}, 'b'), config), 0)
        config.write_text(RULES + '\n[invalid:ambiguous]\nbaringRule = true\n')
        result = subprocess.run([self.engine, 'check', str(config)], capture_output=True, text=True, timeout=30)
        self.assertIn('Cannot determine royal types', result.stderr)


if __name__ == '__main__':
    unittest.main()
