#!/usr/bin/env python3
"""Victim-derived substitutions, ordered captures, provenance and effects."""
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import unittest


RULES = '''[transform]
maxFile = 8
maxRank = 8
piece = k:<commoner> +k:<em>
piece = em:K
piece = tk:Q
piece = bs:B
piece = dv:F +dv:<tk>
piece = ds:W +ds:<bs>
piece = g:<gold>
piece = p:fW +p:<g>
piece = r:R
piece = x:W
piece = l:KNAD
piece = ld:KADGH
piece = h:R
piece = z:K
piece = a:K
castling = false
doubleStep = false
promotionPawnTypes = -
promotionPieceTypes = -
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{} mandatory:{iic}
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionCondition = and(k=0,em=0)
nMoveRule = 0
lionMovePieces = l(FFFFFFFFFFFFFFFF)
lionDogMovePieces = ld:FFFFFFFFFFFF
hookMovePieces = h:R-sR:2
doubleMovePieces = z:x-x:2
transformOnCapturePieces = {tk,bs,dv:tk,ds:bs}
transformOnCaptureImmunePieces = {k,em}
startFen = 7,k/8/8/8/8/8/8/7,K w - - 0 1
[transform-first:transform]
transformOnCapturePolicy = first
[transform-last:transform]
transformOnCapturePolicy = last
[transform-clear:transform]
transformOnCapturePieces = {}
[transform-replace:transform]
transformOnCapturePieces = {tk:bs}
[transform-immune:transform]
transformOnCaptureImmunePieces = {k,em,l,tk}
[transform-limit:transform]
transformOnCapturePieces = {tk:g,bs,dv:g,ds:bs}
promotionLimit = g:1
[transform-limit-first:transform-limit]
transformOnCapturePolicy = first
[transform-limit-last:transform-limit]
transformOnCapturePolicy = last
[transform-prohibited:transform]
prohibitedCaptures = r:dv
[transform-trading:transform]
tradingRule = r:[any!,{dv}]
[transform-ep:transform]
pawn = o
enPassantRegionWhite = *
enPassantRegionBlack = *
transformOnCapturePieces = {tk,bs,dv:tk,ds:bs,o:tk}
[transform-burn:transform]
burnActivePieceTypes = {r}
[transform-passive:transform]
burnPassivePieceTypes = {r}
[transform-promote-burn:transform]
burnActivePieceTypes = {tk}
burnOnPromotePieces = {p,dv,l,ld,h,z,a}
[transform-freeze:transform]
freezeEffectPieces = {tk}
[transform-flip:transform]
pieceDemotion = true
[transform-native:chess]
pieceToCharTable = -
pawn = -
knight = -
bishop = -
rook = -
queen = -
piece = tk:R
piece = bs:B
piece = dv:K
piece = x:W
castling = false
transformOnCapturePieces = {dv:tk}
transformOnCaptureImmunePieces = {k}
[transform-atomic:atomic]
pieceToCharTable = -
piece = dv:K
piece = tk:B
transformOnCapturePieces = {dv:tk}
[transform-pawn-result:transform-ep]
transformOnCapturePieces = {dv:o}
[transform-hand:transform]
capturesToHand = true
pieceDrops = true
transformOnCapturePieces = {x:g}
[transform-range:transform]
rangeJumpPieces = r:cR:{k}
'''


def fixture_rules():
    rules = RULES
    if os.environ.get('BOARD_SIZE', '8') != '8':
        rules += '\n[transform-area:transform]\ntenjikuTripleStepPieceTypes = {a}\n'
    if int(os.environ.get('PIECE_SLOTS', '64')) >= 256:
        rules += '\n[transform-high:transform]\ncustomPiece200 = hi:W\ntransformOnCapturePieces = {hi:hi,dv:hi}\n'
    return rules


def fen(board=None, side='w', ep='-'):
    board = {'h1': 'K', 'h8': 'k', **(board or {})}
    rows = []
    for rank in range(8, 0, -1):
        cells, empty = [], 0
        for file in 'abcdefgh':
            pc = board.get(file + str(rank))
            if not pc:
                empty += 1
            else:
                if empty:
                    cells.append(str(empty))
                    empty = 0
                cells.append(pc)
        if empty:
            cells.append(str(empty))
        rows.append(','.join(cells))
    return '/'.join(rows) + f' {side} - {ep} 0 1'


class TransformOnCapture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'transform.ini'
        rules = fixture_rules()
        cls.config.write_text(rules)
        cls.engine_path = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.engine = subprocess.Popen([cls.engine_path, 'load', str(cls.config)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True)
        cls.lines = queue.Queue()
        def reader():
            try:
                for line in cls.engine.stdout:
                    cls.lines.put(line)
            finally:
                cls.lines.put(None)
        cls.reader = threading.Thread(target=reader, daemon=True)
        cls.reader.start()
        out = cls.command('setoption name Use NNUE value false\nisready\n')
        assert not any(s in out for s in (' - Invalid', 'Expected unique', 'Unsupported combination', 'undefined piece')), out

    @classmethod
    def command(cls, text):
        cls.engine.stdin.write(text)
        cls.engine.stdin.flush()
        out, ready = [], False
        done = 'go ' not in text
        while True:
            line = cls.lines.get(timeout=120)
            if line is None:
                raise AssertionError('Engine exited:\n' + ''.join(out))
            out.append(line)
            ready |= line.strip() == 'readyok'
            done |= 'Nodes searched:' in line or line.startswith('bestmove ')
            if ready and done:
                return ''.join(out)

    @classmethod
    def tearDownClass(cls):
        if cls.engine.poll() is None:
            cls.engine.stdin.write('quit\n')
            cls.engine.stdin.flush()
            cls.engine.wait(timeout=30)
        cls.engine.stdin.close()
        cls.engine.stdout.close()
        cls.reader.join(timeout=5)
        cls.temp.cleanup()

    def output(self, name='transform', board=None, side='w', moves='', ep='-', action='go perft 1\n'):
        return self.command(f'setoption name UCI_Variant value {name}\n'
                            f'position fen {fen(board, side, ep)}'
                            + (' moves ' + moves if moves else '') + '\n' + action + 'isready\n')

    def moves(self, *args, **kwargs):
        output = self.output(*args, **kwargs)
        moves = re.findall(r'^(\S+): \d+$', output, re.M)
        self.assertEqual(len(moves), len(set(moves)), output)
        return set(moves)

    def test_mapping_and_replacement_both_colours(self):
        for side in ('w', 'b'):
            target = 'd5' if side == 'w' else 'd3'
            own = 'P' if side == 'w' else 'p'
            enemy = 'dv' if side == 'w' else 'DV'
            board = {'d4': own, target: enemy}
            moves = self.moves(board=board, side=side)
            self.assertIn('d4' + target + 'tk', moves)
            self.assertNotIn('d4' + target, moves)
            self.assertNotIn('d4' + target + '+', moves)
            after = self.output(board=board, side=side, moves='d4' + target + 'tk', action='d\n')
            self.assertIn('TK~' if side == 'w' else 'tk~', after)

    def test_actual_promoted_victim_type_and_inheritance_replacement(self):
        moves = self.moves('transform-replace', {'d4': 'R', 'd5': '+dv'})
        self.assertIn('d4d5bs', moves)
        self.assertNotIn('d4d5', moves)
        # The child replaced its parent's mappings; unpromoted dv is ordinary.
        self.assertIn('d4d5', self.moves('transform-replace', {'d4': 'R', 'd5': 'dv'}))

    def test_immune_capturer_uses_ordinary_promotion(self):
        moves = self.moves(board={'d4': 'K', 'e5': 'dv'})
        self.assertIn('d4e5+', moves)
        self.assertNotIn('d4e5tk', moves)
        moves = self.moves(board={'d4': 'EM', 'e5': 'dv'})
        self.assertIn('d4e5', moves)
        self.assertNotIn('d4e5tk', moves)

    def test_clear_restores_ordinary_capture(self):
        self.assertIn('d4d5', self.moves('transform-clear', {'d4': 'R', 'd5': 'dv'}))

    def test_non_contagious_capture_and_quiet_move_are_unchanged(self):
        moves = self.moves(board={'d4': 'P', 'd5': 'x'})
        self.assertIn('d4d5+', moves)
        self.assertIn('d4d5', self.moves(board={'d4': 'P'}))

    def test_choose_first_last_ignore_non_contagious_captures(self):
        board = {'d4': 'LD', 'd5': 'dv', 'd6': 'x', 'd7': 'ds'}
        route = 'd4d5d6d7'
        for variant, results in [('transform', {'tk', 'bs'}),
                                 ('transform-first', {'tk'}), ('transform-last', {'bs'})]:
            moves = self.moves(variant, board)
            self.assertEqual({m[len(route):] for m in moves if m.startswith(route)}, results)

    def test_capture_order_is_not_bitboard_order_and_revisits_do_not_recapture(self):
        board = {'d4': 'LD', 'd6': 'bs', 'd5': 'dv'}
        for variant, suffix in [('transform-first', 'bs'), ('transform-last', 'tk')]:
            self.assertIn('d4d6d5' + suffix, self.moves(variant, board))
        board = {'d4': 'LD', 'd5': 'dv', 'd6': 'ds'}
        moves = self.moves('transform-last', board)
        self.assertIn('d4d5d6d5bs', moves)
        self.assertNotIn('d4d5d6d5tk', moves)

    def test_duplicate_results_are_emitted_once(self):
        moves = self.moves(board={'d4': 'L', 'e5': 'dv', 'f6': 'tk'})
        self.assertIn('d4e5f6tk', moves)
        self.assertNotIn('d4e5f6', moves)

    def test_igui_and_already_promoted_sources(self):
        moves = self.moves(board={'d4': 'L', 'e5': 'ds'})
        self.assertIn('d4e5d4bs', moves)
        after = self.output(board={'d4': '+P', 'e5': 'ds'}, moves='d4e5bs', action='d\n')
        self.assertIn('BS~', after)

    def test_immunity_is_checked_before_the_complete_move(self):
        moves = self.moves('transform-immune', {'d4': 'LD', 'd5': 'dv', 'd6': 'ds'})
        self.assertIn('d4d5d6tk', moves)
        self.assertIn('d4d5d6bs', moves)

    def test_hook_and_generic_double_move_choices(self):
        for piece, route, board in [
            ('H', 'd4d6f6', {'d6': 'dv', 'f6': 'ds'}),
            ('Z', 'd4e4f4', {'e4': 'dv', 'f4': 'ds'})]:
            moves = self.moves(board={'d4': piece, **board})
            self.assertIn(route + 'tk', moves)
            self.assertIn(route + 'bs', moves)

    def test_promotion_limits_and_same_type_replacement(self):
        moves = self.moves('transform-limit', {'d4': 'R', 'd5': 'dv', 'a2': 'G'})
        self.assertFalse(any(m.startswith('d4d5') for m in moves))
        moves = self.moves('transform-limit', {'d4': 'G', 'd5': 'dv'})
        self.assertIn('d4d5g', moves)
        board = {'d4': 'L', 'e5': 'dv', 'f6': 'ds', 'a2': 'G'}
        self.assertIn('d4e5f6bs', self.moves('transform-limit', board))
        self.assertFalse(any(m.startswith('d4e5f6') for m in self.moves('transform-limit-first', board)))

    def test_prohibited_captures_and_trading_still_apply(self):
        self.assertNotIn('d4d5tk', self.moves('transform-prohibited', {'d4': 'R', 'd5': 'dv'}))
        self.assertNotIn('d4d5tk', self.moves('transform-trading', {'d4': 'R', 'd5': 'dv', 'd6': 'x'}))
        self.assertIn('d4d5tk', self.moves('transform-trading', {'d4': 'R', 'd5': 'dv'}))

    def test_en_passant_substitution(self):
        board = {'d5': 'O', 'e5': 'o'}
        moves = self.moves('transform-ep', board, ep='e6')
        self.assertIn('d5e6tk', moves)
        self.assertNotIn('d5e6', moves)
        after = self.output('transform-ep', board, ep='e6', moves='d5e6tk', action='d\n')
        self.assertIn('TK~', after)
        moves = self.moves('transform-ep', {'d7': 'O', 'e8': 'dv'})
        self.assertIn('d7e8tk', moves)

    def test_atomic_capture_and_pawn_result(self):
        after = self.output('transform-atomic', {'d4': 'R', 'd5': 'dv'},
                            moves='d4d5tk', action='d\n')
        self.assertRegex(after, r'(?m)^Fen: 7,k/8/8/8/8/8/8/7,K b ')
        after = self.output('transform-pawn-result', {'d4': 'R', 'd5': 'dv'},
                            moves='d4d5o', action='d\n')
        self.assertIn('O~', after)

    def test_range_jump_screens_do_not_trigger_substitution(self):
        moves = self.moves('transform-range', {'d4': 'R', 'd5': 'dv', 'd7': 'ds'})
        self.assertIn('d4d7bs', moves)
        self.assertNotIn('d4d7tk', moves)

    def test_burn_victims_do_not_offer_choices_and_passive_death_does_not_transform(self):
        moves = self.moves('transform-burn', {'d4': 'R', 'd5': 'x', 'e5': 'dv'})
        self.assertIn('d4d5', moves)
        self.assertNotIn('d4d5tk', moves)
        moves = self.moves('transform-passive', {'d4': 'R', 'd5': 'dv', 'e5': 'r'})
        self.assertIn('d4d5', moves)
        self.assertNotIn('d4d5tk', moves)

    def test_transform_burning_and_freezing_use_the_resulting_type(self):
        after = self.output('transform-promote-burn', {'d4': 'P', 'd5': 'dv', 'e5': 'x'},
                            moves='d4d5tk', action='d\n')
        self.assertIn('TK~', after)
        self.assertNotRegex(re.search(r'^Fen: (.*)', after, re.M)[1], r'(^|[,/])x([,/ ]|$)')
        # tk freezes the adjacent enemy x, but that aura starts after the route.
        moves = self.moves('transform-freeze', {'d4': 'P', 'd5': 'dv', 'e5': 'x'}, moves='d4d5tk')
        self.assertFalse(any(m.startswith('e5') for m in moves))

    def test_native_king_legality_and_result_check(self):
        out = self.output('transform-native', {'d4': 'X', 'e4': 'dv', 'h8': None, 'e8': 'k'},
                          moves='d4e4tk', action='d\n')
        self.assertIn('Checkers: e4', out)
        self.assertIn('d4e5', self.moves('transform-native', {'d4': 'K', 'e5': 'dv', 'h1': None}))

    def test_search_can_use_transformation_choices(self):
        board = {'d4': 'LD', 'd5': 'dv', 'd6': 'ds'}
        for name in ('transform', 'transform-first', 'transform-last'):
            legal = self.moves(name, board)
            out = self.output(name, board, action='go depth 2\n')
            self.assertIn(re.search(r'^bestmove (\S+)', out, re.M)[1], legal)

    def test_perft_undo_preserves_promoted_source_and_keys(self):
        for board in [{'d4': '+P', 'e5': 'ds'}, {'d4': 'LD', 'd5': 'dv', 'd6': 'ds'},
                      {'d4': 'H', 'd6': 'dv', 'f6': 'ds'}]:
            out = self.output(board=board, action='d\ngo perft 2\nd\n')
            self.assertEqual(*re.findall(r'^Fen: (.*)', out, re.M))
            self.assertEqual(*re.findall(r'^Key: (.*)', out, re.M))

    @unittest.skipIf(os.environ.get('BOARD_SIZE', '8') == '8', 'Requires wide area-route encoding')
    def test_three_step_area_uses_the_last_direct_capture(self):
        moves = self.moves('transform-area', {'d4': 'A', 'd7': 'dv'})
        self.assertIn('d4d5d6d7tk', moves)
        self.assertNotIn('d4d5d6d7', moves)

    @unittest.skipUnless(int(os.environ.get('PIECE_SLOTS', '64')) >= 256, 'Requires high piece IDs')
    def test_high_piece_id_targets(self):
        self.assertIn('d4d5hi', self.moves('transform-high', {'d4': 'R', 'd5': 'dv'}))

    def test_invalid_options_reject_variant_registration(self):
        cases = [('transformOnCapturePieces', '{dv:unknown}'),
                 ('transformOnCapturePieces', '{dv:tk,dv:bs}'),
                 ('transformOnCapturePieces', '{tk,}'),
                 ('transformOnCapturePieces', '{,tk}'),
                 ('transformOnCapturePieces', '{dv:}'),
                 ('transformOnCapturePieces', 'tk'),
                 ('transformOnCapturePolicy', 'random'),
                 ('transformOnCaptureImmunePieces', '{unknown}')]
        for option, value in cases:
            config = Path(self.temp.name) / 'invalid.ini'
            config.write_text(RULES + f'\n[invalid:transform]\n{option} = {value}\n')
            out = subprocess.run([self.engine_path, 'check', str(config)], input='quit\n',
                                 text=True, capture_output=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn(option + ' - ', out.stderr)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--fixture':
        Path(sys.argv[2]).write_text(fixture_rules())
    else:
        unittest.main(verbosity=2)
