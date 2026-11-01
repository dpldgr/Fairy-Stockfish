#!/usr/bin/env python3
"""Colour-relative range blockers and distinct, self-destructing missile strikes."""
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import threading
import unittest
import range_jumps as rj


def oracle(board, side, friends, enemies):
    result = set()
    origin = 'd4'
    for df, dr in ((0,1),(1,0),(0,-1),(-1,0)):
        f, r = 3+df, 4+dr
        while 0 <= f < 8 and 1 <= r <= 8:
            to = chr(97+f)+str(r)
            pc = board.get(to)
            if pc == '*': break
            if pc:
                own = pc.isupper() == (side == 'w')
                if not own and pc.lower() != 's': result.add(origin+to+'!')
                if pc.lower() in (friends if own else enemies): break
            f, r = f+df, r+dr
    return result


class MissileEffects(unittest.TestCase):
    def output(self, variant='missile', *args, **kwargs):
        return rj.RangeJumps.output(self, variant, *args, **kwargs)
    moves = rj.RangeJumps.moves
    final = rj.RangeJumps.final

    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH','./stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name)/'missile.ini'
        cls.config.write_text('''[base]
commoner = k
rook = r
pawn = p
piece = m:K
piece = s:K
piece = v:W
piece = fd:K
castling = false
doubleStep = false
rangeJumpPieces = m:R:{s}
missileEffectPieces = {m}
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
nMoveRule = 0
promotionPolicy = optional:{} mandatory:{}
[missile:base]
prohibitedCaptures = m:s
[enemy:missile]
rangeJumpPieces = m:R:{s=enemy}
[friend:missile]
rangeJumpPieces = m:R:{s=friend}
[both:missile]
rangeJumpPieces = m:R:{s=both}
[mixed:missile]
rangeJumpPieces = m:R:{s=enemy,p=friend}
[all-enemy:missile]
rangeJumpPieces = m:R:{*=enemy}
[empty-blockers:missile]
rangeJumpPieces = m:R:{-}
[clear:missile]
missileEffectPieces = -
[passive:missile]
burnPassivePieceTypes = {fd}
burnActivePieceTypes = {fd}
[immune:passive]
burnImmunePieces = {m,s,p,fd,k}
[freeze:missile]
freezeEffectPieces = {fd}
[freeze-immune:freeze]
freezeImmunePieces = {m}
[promote:missile]
promotedPieceType = m:r
promotionRegionMandatoryWhite<m> = *
promotionPolicy = optional:{} mandatory:{iic}
[royal:missile]
commoner = -
king = k
extinctionValue = none
[royal-enemy:royal]
rangeJumpPieces = m:R:{s=enemy}
[royal-forward:royal]
rangeJumpPieces = m:fR:{s=enemy}
[royal-immune:royal]
mutuallyImmuneTypes = m
[pawn-missile:missile]
rangeJumpPieces = p:R:{s=enemy}
missileEffectPieces = {p}
[drop:missile]
pieceDrops = true
capturesToHand = true
''')

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_distinct_capture_choices_and_no_quiet_strikes(self):
        moves = self.moves(board={'d4':'M','e4':'v','d7':'v'})
        self.assertIn('d4e4',moves)
        self.assertIn('d4e4!',moves)
        self.assertIn('d4d7!',moves)
        self.assertNotIn('d4d7',moves)
        self.assertNotIn('d4d6!',moves)
        self.assertEqual(len(moves),len(set(moves)))
        self.assertIn('M',self.final('missile',{'d4':'M','e4':'v'},'d4e4'))
        self.assertNotIn('M',self.final('missile',{'d4':'M','e4':'v'},'d4e4!'))

    def test_qualifiers_both_colours(self):
        for side, mover, ally, enemy, target in [('w','M','S','s','v'),('b','m','s','S','V')]:
            for blocker, own in [(ally,True),(enemy,False)]:
                board={'d4':mover,'d5':blocker,'d7':target}
                for variant, blocks in [('enemy',not own),('friend',own),('both',True),('missile',True)]:
                    with self.subTest(side=side,blocker=blocker,variant=variant):
                        self.assertEqual('d4d7!' in self.moves(variant,board,side=side),not blocks)

    def test_randomized_independent_blocker_oracle(self):
        rng=random.Random(203186)
        squares=[chr(97+f)+str(r) for f in range(8) for r in range(1,9) if (f,r) not in ((3,4),(7,1),(7,8))]
        for side in ('w','b'):
            for variant, friends, enemies in [('enemy',set(),{'s'}),('friend',{'s'},set()),('both',{'s'},{'s'}),('mixed',{'p'},{'s'})]:
                for case in range(3):
                    board={'d4':'M' if side=='w' else 'm'}
                    for square in rng.sample(squares,18):
                        pc=rng.choice(('s','p','v','r','*'))
                        board[square]=pc.upper() if rng.randrange(2) else pc
                    actual={m for m in self.moves(variant,board,side=side) if m.startswith('d4') and m.endswith('!')}
                    with self.subTest(side=side,variant=variant,case=case):
                        self.assertEqual(actual,oracle(board,side,friends,enemies))

    def test_shield_endpoint_and_prohibited_capture_are_independent(self):
        board={'d4':'M','d6':'s','d7':'v'}
        self.assertIn('d4d6!',self.moves('base',board))
        self.assertNotIn('d4d7!',self.moves('base',board))
        self.assertNotIn('d4d6!',self.moves('missile',board))
        self.assertNotIn('d4d7!',self.moves('missile',board))
        self.assertNotIn('d4e4',self.moves(board={'d4':'M','e4':'s'}))
        self.assertNotIn('d4e4!',self.moves(board={'d4':'M','e4':'s'}))

    def test_mixed_and_wildcard_sets(self):
        self.assertNotIn('d4d7!',self.moves('mixed',{'d4':'M','d5':'P','d7':'v'}))
        self.assertIn('d4d7!',self.moves('mixed',{'d4':'M','d5':'p','d7':'v'}))
        self.assertIn('d4d6!',self.moves('all-enemy',{'d4':'M','d5':'R','d6':'v','d7':'v'}))
        self.assertNotIn('d4d7!',self.moves('all-enemy',{'d4':'M','d5':'R','d6':'v','d7':'v'}))

    def test_walls_and_destinations(self):
        self.assertNotIn('d4d7!',self.moves('enemy',{'d4':'M','d5':'*','d7':'v'}))
        path=Path(self.temp.name)/'limited.ini'
        path.write_text(self.config.read_text()+'\n[limited:enemy]\nmobilityRegionWhiteCustomPiece1 = d4 d5 d6\n')
        self.assertNotIn('d4d7!',self.moves('limited',{'d4':'M','d7':'v'},config=path))

    def test_all_colour_and_pawn_bycatch_destroyed(self):
        board={'d4':'M','d7':'v','c6':'V','d6':'P','e6':'p','c7':'s','e7':'R','c8':'r','d8':'v','e8':'P','f7':'V'}
        final=self.final('missile',board,'d4d7!')
        self.assertEqual(final,rj.fen({'h1':'K','h8':'k','f7':'V'},side='b'))

    def test_missile_has_priority_over_passive_burn_and_immunity(self):
        board={'d4':'M','d5':'v','e6':'fd','e5':'p'}
        for variant in ('passive','immune'):
            final=self.final(variant,board,'d4d5!')
            self.assertNotIn('fd',final)
            self.assertNotIn('p',final)
            self.assertNotIn('M',final)
        final=self.final('passive',board,'d4d5')
        self.assertIn('fd',final)
        self.assertIn('p',final)
        self.assertNotIn('M',final)

    def test_frozen_missile_cannot_fire(self):
        board={'d4':'M','d7':'v','e5':'fd'}
        self.assertFalse(any(m.startswith('d4') for m in self.moves('freeze',board)))
        self.assertIn('d4d7!',self.moves('freeze-immune',board))

    def test_strike_does_not_promote_or_decline_a_live_mandatory_promotion(self):
        moves=self.moves('promote',{'d4':'M','e4':'v'})
        self.assertIn('d4e4!',moves)
        self.assertIn('d4e4+',moves)
        self.assertNotIn('d4e4',moves)
        self.assertNotIn('d4e4!+',moves)
        self.final('promote',{'d4':'M','e4':'v'},'d4e4!')

    def test_native_pawn_strike_has_no_promotion(self):
        moves=self.moves('pawn-missile',{'d6':'P','d8':'v'})
        self.assertIn('d6d8!',moves)
        self.assertFalse(any(m.startswith('d6d8') and m!='d6d8!' for m in moves))
        self.final('pawn-missile',{'d6':'P','d8':'v'},'d6d8!')

    def test_destroying_emitter_thaws_survivor_outside_blast(self):
        board={'d4':'M','d6':'v','e6':'fd','f6':'R'}
        self.assertNotIn('f6f7',self.moves('freeze',board))
        self.assertIn('f6f7',self.moves('freeze',board,moves='d4d6! h8g8'))
        self.final('freeze',board,'d4d6!')

    def test_destroyed_missile_does_not_chain_detonate(self):
        result=self.final('missile',{'d4':'M','d6':'v','e6':'m','f6':'V'},'d4d6!')
        self.assertIn('V',result)
        self.assertNotIn('m',result)

    def test_clearing_effect_restores_ordinary_range_capture(self):
        moves=self.moves('clear',{'d4':'M','d7':'v'})
        self.assertIn('d4d7',moves)
        self.assertNotIn('d4d7!',moves)
        self.assertIn('M',self.final('clear',{'d4':'M','d7':'v'},'d4d7'))

    def test_royal_threat_from_off_ray_blast(self):
        board={'d4':'m','d6':'V','e6':'K','h1':None}
        out=self.output('royal',board)
        self.assertIn('Checkers: d4',out)
        self.assertIn('d6c6',self.moves('royal',board))
        self.assertIn('e6f6',self.moves('royal',board))
        board['d6']='S'
        self.assertIn('Checkers: \n',self.output('royal',board))

    def test_mutually_immune_target_cannot_trigger_blast(self):
        board={'d4':'m','d6':'M','e6':'K','h1':None}
        self.assertIn('Checkers: d4',self.output('royal',board))
        self.assertIn('Checkers: \n',self.output('royal-immune',board))
        self.assertNotIn('d4d6!',self.moves('royal-immune',board,side='b'))

    def test_legacy_empty_blocker_set(self):
        self.assertIn('d4d7!',self.moves('empty-blockers',{'d4':'M','d5':'s','d7':'v'}))

    def test_reverse_attack_queries_keep_the_attackers_colour(self):
        for variant in ('royal-enemy','royal-forward'):
            board={'d1':'K','h1':None,'d7':'m','d5':'s'}
            self.assertIn('Checkers: d7',self.output(variant,board))
            board['d5']='S'
            self.assertIn('Checkers: \n',self.output(variant,board))
            board={'d1':'M','d7':'k','h8':None,'d3':'S'}
            self.assertIn('Checkers: d1',self.output(variant,board,side='b'))
            board['d3']='s'
            self.assertIn('Checkers: \n',self.output(variant,board,side='b'))

    def test_capturing_into_blocker_square_evades_check(self):
        board={'a1':'K','h1':None,'g1':'m','d1':'v','d2':'S'}
        self.assertIn('d2d1',self.moves('royal-enemy',board))
        self.final('royal-enemy',board,'d2d1')
        board={'a1':'K','h1':None,'g1':'m','d1':'S','d2':'v'}
        self.assertNotIn('d1d2',self.moves('royal-enemy',board))

    def test_self_and_mutual_royal_destruction_lose_for_mover(self):
        for board in [{'d4':'M','d5':'v','c5':'K','h1':None},
                      {'d4':'M','d5':'v','c5':'K','e5':'k','h1':None,'h8':None}]:
            self.assertIn('d4d5!',self.moves(board=board))
            self.search_case(board,'d4d5!','mate -1')

    def test_search_finds_blast_royal_capture(self):
        self.search_case({'d4':'M','d7':'v','e7':'k','h8':None},'d4d7!','mate 1',restrict=False)

    def search_case(self,board,move,score,restrict=True):
        position=rj.fen({'h1':'K','h8':'k',**board})
        with subprocess.Popen([self.engine,'load',str(self.config)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as p:
            timer=threading.Timer(40,p.kill);timer.start()
            try:
                command='go depth 3'+(f' searchmoves {move}' if restrict else '')
                p.stdin.write(f'setoption name UCI_Variant value missile\nposition fen {position}\n{command}\n');p.stdin.flush();lines=[]
                for line in p.stdout:
                    lines.append(line)
                    if line.startswith('bestmove'):break
                p.stdin.write('quit\n');p.stdin.flush();_,err=p.communicate(timeout=10)
                self.assertEqual(p.returncode,0,err)
                self.assertIn('score '+score,''.join(lines))
                self.assertIn('bestmove '+move,''.join(lines))
            finally:timer.cancel()

    def test_malformed_options_reject_variant(self):
        path=Path(self.temp.name)/'invalid.ini'
        options=['rangeJumpPieces = m:R:{s=other}','rangeJumpPieces = m:R:{s=}',
                 'rangeJumpPieces = m:R:{s=friend,s=enemy}','rangeJumpPieces = m:R:{=both}',
                 'rangeJumpPieces = m:R:{missing=enemy}','rangeJumpPieces = -',
                 'missileEffectPieces = {missing}']
        for option in options:
            with self.subTest(option=option):
                path.write_text(self.config.read_text()+'\n[invalid:missile]\n'+option+'\n')
                p=subprocess.run([self.engine,'load',str(path)],input='uci\nquit\n',text=True,capture_output=True,timeout=120)
                self.assertEqual(p.returncode,0)
                self.assertNotIn(' var invalid',p.stdout)
                self.assertRegex(p.stderr,r'rangeJumpPieces - |missileEffectPieces - ')

    def test_requested_8x10_fixture(self):
        if int(os.environ.get('BOARD_SIZE','8')) < 10:
            self.skipTest('build supporting ten ranks only')
        path=Path(__file__).parent/'fixtures/missile-chess.ini'
        position=next(line.split('=',1)[1].strip() for line in path.read_text().splitlines() if line.startswith('startFen'))
        moves=self.moves('missile-chess',position,config=path)
        self.assertEqual(len(moves),34)
        self.assertIn('a1b1',moves)
        self.assertFalse(any(m.endswith('!') for m in moves))
        castle='8/4k3/8/8/8/8/8/8/R3K2R/8 w KQ - 0 1'
        moves=self.moves('missile-chess',castle,config=path)
        self.assertIn('e2g2',moves)
        self.assertIn('e2c2',moves)
        black_double='8/4k3/3p4/8/4P3/8/8/8/4K3/8 b - - 0 1'
        self.assertIn('e6d7',self.moves('missile-chess',black_double,config=path,moves='d8d6'))
        white_double='8/4k3/8/8/8/4p3/8/3P4/4K3/8 w - - 0 1'
        self.assertIn('e5d4',self.moves('missile-chess',white_double,config=path,moves='d3d5'))
        promotion='8/4k3/3P4/8/8/8/8/8/4K3/8 w - - 0 1'
        moves=self.moves('missile-chess',promotion,config=path)
        self.assertIn('d8d9q',moves)
        self.assertNotIn('d8d9',moves)
        promotion='8/4k3/8/8/8/8/8/3p4/4K3/8 b - - 0 1'
        moves=self.moves('missile-chess',promotion,config=path)
        self.assertIn('d3d2q',moves)
        self.assertNotIn('d3d2',moves)

    def test_high_slot_full_board(self):
        if os.environ.get('BOARD_SIZE')!='19' or int(os.environ.get('PIECE_SLOTS','64'))<128:
            self.skipTest('19x19 high-slot build only')
        slots=int(os.environ['PIECE_SLOTS']);path=Path(self.temp.name)/'high.ini'
        path.write_text(f'''[high]
maxFile = 19
maxRank = 19
commoner = k
pawn = p
rook = r
customPiece{slots-39} = hx:K
castling = false
rangeJumpPieces = hx:R:{{p=enemy}}
missileEffectPieces = {{hx}}
prohibitedCaptures = hx:p
extinctionValue = loss
extinctionPieceTypes = k
''')
        board={'a1':'K','a19':'k','j10':'HX','j12':'P','j18':'r','i18':'P','k19':'R'}
        position=rj.fen(board,size=19)
        self.assertIn('j10j18!',self.moves('high',position,config=path))
        final=self.output('high',position,moves='j10j18!',config=path)
        self.assertIn('P',re.search(r'^Fen: (.+)',final,re.M).group(1)) # j12 survives
        board['j12']='p'
        self.assertNotIn('j10j18!',self.moves('high',rj.fen(board,size=19),config=path))


if __name__=='__main__': unittest.main()
