#!/usr/bin/env python3
"""Continuous freeze and burn immunity through real legal moves and search."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
import range_jumps as rj
from range_jumps import fen


class FreezeEffects(unittest.TestCase):
    def output(self, variant='freeze', *args, **kwargs):
        return rj.RangeJumps.output(self, variant, *args, **kwargs)

    moves = rj.RangeJumps.moves
    final = rj.RangeJumps.final

    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'freeze.ini'
        cls.config.write_text('''[freeze]
commoner = k
rook = r
bishop = b
knight = n
pawn = p
piece = ik:K
piece = fk:K
piece = v:W
piece = ln:KNAD
lionMovePieces = ln(FFFFFFFFFFFFFFFF)
castling = false
doubleStep = false
freezeEffectPieces = {ik}
freezeImmunePieces = {ik}
burnActivePieceTypes = {fk}
extinctionValue = loss
extinctionPieceTypes = k
extinctionPseudoRoyal = false
nMoveRule = 0
promotionPolicy = optional:{} mandatory:{}
[mutual:freeze]
freezeImmunePieces = {ik,fk}
burnImmunePieces = {ik}
[no-immune:freeze]
freezeImmunePieces = {}
[clear:freeze]
freezeEffectPieces = -
freezeImmunePieces = -
burnImmunePieces = -
[passive:freeze]
burnPassivePieceTypes = {fk}
[passive-immune:mutual]
burnPassivePieceTypes = {fk}
[blast:mutual]
burnActivePieceTypes = -
blastOnCapture = true
[royal:freeze]
commoner = -
king = k
extinctionValue = none
[castle:royal]
castling = true
[fire-ice:mutual]
extinctionCondition = and(fk=0,ik=0)
[drop:freeze]
pieceDrops = true
capturesToHand = true
[range:freeze]
rangeJumpPieces = r:cR:{v}
[trading:mutual]
tradingRule = fk:[any!,{v}]
[promote:freeze]
promotedPieceType = v:ik
promotionRegionMandatoryWhite<v> = *
promotionPolicy = optional:{} mandatory:{iic}
[promote-passive:promote]
burnPassivePieceTypes = {fk}
[promote-passive-immune:promote-passive]
burnImmunePieces = {v}
[freeze-win:freeze]
burnActivePieceTypes = -
stalemateValue = loss

''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_each_adjacent_square_and_both_colours(self):
        for df, dr in ((0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1)):
            square = chr(ord('d') + df) + str(4 + dr)
            for side, emitter, victim in [('b','IK','r'),('w','ik','R')]:
                with self.subTest(square=square, side=side):
                    moves = self.moves(board={'d4':emitter,square:victim}, side=side)
                    self.assertFalse(any(m.startswith(square) for m in moves))

    def test_frozen_pieces_remain_capturable_and_blockers(self):
        moves = self.moves(board={'c4':'IK','d4':'r','d1':'R'})
        self.assertIn('d1d4', moves)
        self.assertNotIn('d1d5', moves)
        moves = self.moves('range', {'c4':'IK','d4':'v','d1':'R','d7':'r'})
        self.assertNotIn('d1d7', moves)

    def test_moving_emitter_thaws_without_changing_piece_identity(self):
        board = {'d4':'IK','d5':'r'}
        self.assertNotIn('d5d6', self.moves(board=board, side='b'))
        self.assertIn('d5d6', self.moves(board=board, moves='d4c3'))
        self.final('freeze', board, 'd4c3')

    def test_capturing_emitter_thaws(self):
        board = {'d4':'IK','d5':'r','f6':'b'}
        self.assertIn('f6d4', self.moves(board=board, side='b'))
        self.assertIn('d5d6', self.moves(board=board, side='b', moves='f6d4 h1g1'))

    def test_frozen_emitter_keeps_aura(self):
        board = {'d4':'IK','d5':'ik','c4':'r','e5':'R'}
        for side, starts in [('w',('d4','e5')),('b',('d5','c4'))]:
            moves = self.moves('no-immune', board, side=side)
            self.assertFalse(any(m.startswith(starts) for m in moves))

    def test_explicit_immunity_and_clear_inheritance(self):
        board = {'d4':'IK','e5':'fk'}
        self.assertNotIn('e5f5', self.moves('freeze', board, side='b'))
        self.assertIn('e5f5', self.moves('mutual', board, side='b'))
        self.assertIn('e5f5', self.moves('clear', board, side='b'))

    def test_frozen_native_and_lion_sources(self):
        for piece in ('P','N','B','R','LN'):
            with self.subTest(piece=piece):
                self.assertFalse(any(m.startswith('d4') for m in self.moves(board={'d4':piece,'e5':'ik'})))

    def test_frozen_fire_demon_retains_passive_burn(self):
        board = {'d4':'IK','d5':'fk','e3':'V'}
        result = self.final('passive', board, 'e3e4')
        self.assertNotIn('V', result)
        self.assertIn('IK', result)

    def test_burn_immune_arrival_survives_passive_burn(self):
        board = {'d4':'IK','f6':'fk'}
        result = self.final('passive-immune', board, 'd4e5')
        self.assertIn('IK', result)
        result = self.final('passive', board, 'd4e5')
        self.assertNotIn('IK', result)

    def test_active_burn_preserves_immune_victim_only(self):
        result = self.final('mutual', {'d4':'FK','f5':'ik','f4':'v'}, 'd4e4')
        self.assertIn('ik', result)
        self.assertNotIn('v', result)

    def test_immune_piece_still_directly_capturable(self):
        result = self.final('mutual', {'d4':'FK','e5':'ik'}, 'd4e5')
        self.assertNotIn('ik', result)

    def test_burn_immunity_does_not_protect_from_blast(self):
        result = self.final('blast', {'d1':'R','d5':'v','e5':'ik'}, 'd1d5')
        self.assertNotIn('ik', result)

    def test_thawing_attacker_can_make_emitter_move_illegal(self):
        board = {'h8':'r','a8':'k','g7':'IK'}
        self.assertNotIn('g7f6', self.moves('royal', board))
        self.assertIn('g7g8', self.moves('royal', board))

    def test_freezing_attacker_can_evade_check_off_the_ray(self):
        board = {'h8':'r','a8':'k','g6':'IK'}
        self.assertIn('g6g7', self.moves('royal', board))
        self.final('royal', board, 'g6g7')

    def test_frozen_rook_cannot_castle(self):
        position = '1k6/8/8/8/8/8/7,ik/R3K2R w KQ - 0 1'
        moves = self.moves('castle', position)
        self.assertNotIn('e1g1', moves)
        self.assertIn('e1c1', moves)

    def test_drops_can_arrive_frozen(self):
        position = '7,k/8/8/4,ik,3/8/8/8/7,K[R] w - - 0 1'
        self.assertIn('R@d4', self.moves('drop', position))
        self.final('drop', position, 'R@d4')

    def test_frozen_defender_does_not_protect_a_trade(self):
        board = {'d4':'FK','e5':'v','e8':'r','f7':'IK'}
        self.assertIn('d4e5', self.moves('trading', board))
        board.pop('f7')
        self.assertNotIn('d4e5', self.moves('trading', board))

    def test_overlapping_auras_require_all_emitters_to_leave(self):
        board = {'c4':'IK','e4':'IK','d5':'r'}
        self.assertNotIn('d5d6',self.moves(board=board,moves='c4b3'))
        self.assertIn('d5d6',self.moves(board=board,moves='c4b3 h8g8 e4f3'))

    def test_compound_move_is_not_interrupted_by_intermediate_freezing(self):
        board = {'d4':'LN','f6':'ik'}
        self.assertIn('d4e5f4',self.moves(board=board))
        self.final('freeze',board,'d4e5f4')

    def test_promotion_enables_aura_immediately(self):
        board = {'d4':'V','d5':'p','e6':'r'}
        self.assertIn('d4d5+',self.moves('promote',board))
        self.assertNotIn('e6e7',self.moves('promote',board,moves='d4d5+'))
        self.final('promote',board,'d4d5+')

    def test_arrival_immunity_uses_unpromoted_type(self):
        board = {'d4':'V','d5':'p','e6':'fk'}
        moves = self.moves('promote-passive',board)
        self.assertIn('d4d5',moves)
        self.assertNotIn('d4d5+',moves)
        self.assertNotIn('V',self.final('promote-passive',board,'d4d5'))
        self.assertIn('d4d5+',self.moves('promote-passive-immune',board))
        self.assertIn('+V',self.final('promote-passive-immune',board,'d4d5+'))

    def test_invalid_piece_sets_report_diagnostics(self):
        path = Path(self.temp.name) / 'bad.ini'
        for option in ('freezeEffectPieces','freezeImmunePieces','burnImmunePieces'):
            path.write_text(self.config.read_text() + f'\n[bad:freeze]\n{option} = {{missing}}\n')
            p = subprocess.run([self.engine,'check',str(path)],input='quit\n',text=True,capture_output=True,timeout=120)
            self.assertIn(option + ' - Invalid piece set',p.stderr)

    def test_high_slot_full_board(self):
        if os.environ.get('BOARD_SIZE') != '19' or int(os.environ.get('PIECE_SLOTS','64')) < 128:
            self.skipTest('19x19 high-slot build only')
        slots = int(os.environ['PIECE_SLOTS'])
        path = Path(self.temp.name) / 'high.ini'
        path.write_text(f'''[high]
maxFile = 19
maxRank = 19
commoner = k
rook = r
customPiece{slots-39} = hx:K
freezeEffectPieces = {{hx}}
freezeImmunePieces = {{hx}}
burnImmunePieces = {{hx}}
castling = false
extinctionValue = loss
extinctionPieceTypes = k
''')
        position = fen({'a1':'K','a19':'k','r18':'HX','s19':'r','p18':'r'},side='b',size=19)
        moves = self.moves('high',position,config=path)
        self.assertFalse(any(m.startswith('s19') for m in moves))
        self.assertIn('p18p17',moves)

    def test_search_keeps_quiet_freezing_win(self):
        position = fen({'h1':'K','e6':'k','d4':'IK'})
        self.search_case('freeze-win',position,'d4e5')

    def search_case(self, variant, position, move):
        with subprocess.Popen([self.engine,'load',str(self.config)],stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as p:
            timer = threading.Timer(30,p.kill); timer.start()
            try:
                p.stdin.write(f'setoption name UCI_Variant value {variant}\nposition fen {position}\ngo depth 3 searchmoves {move}\n');p.stdin.flush()
                lines=[]
                for line in p.stdout:
                    lines.append(line)
                    if line.startswith('bestmove'):break
                p.stdin.write('quit\n');p.stdin.flush();_,errors=p.communicate(timeout=10)
                self.assertEqual(p.returncode,0,errors)
                self.assertIn('score mate 1',''.join(lines))
                self.assertIn('bestmove '+move,''.join(lines))
            finally:timer.cancel()

    def test_search_recognizes_direct_royal_capture_despite_immunity(self):
        self.search_case('fire-ice', fen({'d4':'FK','e5':'ik'}), 'd4e5')


if __name__ == '__main__':
    unittest.main()
