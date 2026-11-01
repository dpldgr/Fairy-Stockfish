#!/usr/bin/env python3
"""Screened range jumps, movement modes and automatic missile detonation."""
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import threading
import unittest
import range_jumps as rj


def oracle(board, side, friends, enemies, mode='both'):
    """Walk squares; ordinary R ends at the first piece, jumping starts beyond."""
    result=set()
    for df,dr in ((0,1),(1,0),(0,-1),(-1,0)):
        f,r=3+df,4+dr
        screened=False
        while 0<=f<8 and 1<=r<=8:
            to=chr(97+f)+str(r);pc=board.get(to)
            if pc=='*':break
            own=bool(pc) and pc.isupper()==(side=='w')
            if pc:
                if not own and pc.lower()!='s' and (not screened or mode!='quiet'):
                    result.add('d4'+to)
                if pc.lower() in (friends if own else enemies):break
                screened=True
            elif not screened or mode!='capture':result.add('d4'+to)
            f,r=f+df,r+dr
    return result


class MissileEffects(unittest.TestCase):
    def output(self,variant='missile',*args,**kwargs):
        return rj.RangeJumps.output(self,variant,*args,**kwargs)
    moves=rj.RangeJumps.moves
    final=rj.RangeJumps.final

    @classmethod
    def setUpClass(cls):
        cls.engine=str(Path(os.environ.get('STOCKFISH','./stockfish')).resolve())
        cls.temp=tempfile.TemporaryDirectory();cls.config=Path(cls.temp.name)/'missile.ini'
        cls.config.write_text('''[base]
commoner = k
rook = r
pawn = p
piece = m:R
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
[capture:missile]
rangeJumpPieces = m:cR:{s}
[quiet:missile]
rangeJumpPieces = m:mR:{s}
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
[quiet-live:clear]
rangeJumpPieces = m:mR:{s}
[capture-live:clear]
rangeJumpPieces = m:cR:{s}
[initial-live:clear]
piece = m:WifD
rangeJumpPieces = m:mR:{s}
[quiet-burn:quiet-live]
burnActivePieceTypes = {m}
[last:clear]
piece = m:fD
rangeJumpPieces = m:cfR:{}
promotedPieceType = m:r
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{last} mandatory:{}
[last-hard:last]
rangeJumpPieces = m:cR:{*}
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
promotionPolicy = optional:{} mandatory:{all}
[royal:missile]
commoner = -
king = k
piece = m:K
extinctionValue = none
rangeJumpPieces = m:cR:{s=enemy}
[royal-forward:royal]
rangeJumpPieces = m:cfR:{s=enemy}
[royal-quiet:royal]
missileEffectPieces = -
rangeJumpPieces = m:mR:{s=enemy}
[royal-quiet-missile:royal]
rangeJumpPieces = m:mR:{s=enemy}
[royal-immune:royal]
mutuallyImmuneTypes = m
[pawn-missile:missile]
rangeJumpPieces = p:R:{s=enemy}
missileEffectPieces = {p}
[pawn-live:pawn-missile]
missileEffectPieces = -
promotionPieceTypes = r
promotionRegionMandatoryWhite<pawn> = *8
promotionPolicy = optional:{} mandatory:{oi}
[leaper:missile]
piece = m:D
[drop:missile]
pieceDrops = true
capturesToHand = true
''')

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_clear_line_is_ordinary_without_detonation_or_marker(self):
        board={'d4':'M','d7':'v'}
        moves=self.moves(board=board)
        self.assertEqual(moves.count('d4d7'),1)
        self.assertFalse(any('!' in m for m in moves))
        self.assertIn('M',self.final('missile',board,'d4d7'))
        self.assertIn('M',self.final('missile',{'d4':'M'},'d4d7'))

    def test_first_occupied_square_is_ordinary_capture(self):
        board={'d4':'M','d5':'v','e5':'P'}
        self.assertIn('M',self.final('missile',board,'d4d5'))
        self.assertIn('P',self.final('missile',board,'d4d5'))

    def test_quiet_and_capture_jumps_detonate(self):
        for target in ({},{'d7':'v'}):
            board={'d4':'M','d5':'V','c7':'p','e7':'P',**target}
            moves=self.moves(board=board)
            self.assertEqual(moves.count('d4d7'),1)
            final=self.final('missile',board,'d4d7')
            self.assertEqual(final,rj.fen({'h1':'K','h8':'k','d5':'V'},side='b'))

    def test_modes_only_restrict_the_jumping_component(self):
        board={'d4':'M','d5':'V','d7':'v'}
        for variant,quiet,capture in [('missile',True,True),('quiet',True,False),('capture',False,True)]:
            moves=self.moves(variant,board)
            self.assertEqual('d4d6' in moves,quiet)
            self.assertEqual('d4d7' in moves,capture)
            self.assertEqual('d4d8' in moves,quiet) # May cross a second soft piece.
            self.assertIn('d4e4',moves) # Ordinary quiet R remains available.
            self.assertIn('d4e4',self.moves(variant,{'d4':'M','e4':'v'}))

    def test_unarmed_quiet_jump_survives(self):
        board={'d4':'M','d5':'V','d7':'v'}
        self.assertIn('M',self.final('quiet-live',board,'d4d6'))
        self.assertNotIn('d4d7',self.moves('quiet-live',board))
        self.assertNotIn('d4d6',self.moves('capture-live',board))
        self.assertIn('M',self.final('capture-live',board,'d4d7'))

    def test_unarmed_quiet_jump_can_burn_on_arrival(self):
        board={'d4':'M','d5':'V','e7':'v'}
        final=self.final('quiet-burn',board,'d4d7')
        self.assertIn('M',final);self.assertNotIn('v',final)

    def test_qualifiers_both_colours(self):
        for side,mover,target,ally,enemy in [('w','M','v','S','s'),('b','m','V','s','S')]:
            for blocker,own in [(ally,True),(enemy,False)]:
                board={'d4':mover,'d5':blocker,'d7':target}
                for variant,blocks in [('enemy',not own),('friend',own),('both',True),('missile',True)]:
                    with self.subTest(side=side,variant=variant,blocker=blocker):
                        self.assertEqual('d4d7' in self.moves(variant,board,side=side),not blocks)

    def test_randomized_independent_oracle(self):
        rng=random.Random(203186)
        squares=[chr(97+f)+str(r) for f in range(8) for r in range(1,9) if (f,r) not in ((3,4),(7,1),(7,8))]
        policies=[('enemy',set(),{'s'},'both'),('friend',{'s'},set(),'both'),('both',{'s'},{'s'},'both'),
                  ('mixed',{'p'},{'s'},'both'),('quiet',{'s'},{'s'},'quiet'),('capture',{'s'},{'s'},'capture')]
        for side in ('w','b'):
            for variant,friends,enemies,mode in policies:
                for case in range(2):
                    board={'d4':'M' if side=='w' else 'm'}
                    for square in rng.sample(squares,18):
                        pc=rng.choice(('s','p','v','r','*'));board[square]=pc.upper() if rng.randrange(2) else pc
                    moves=self.moves(variant,board,side=side)
                    actual=[m for m in moves if m.startswith('d4')]
                    with self.subTest(side=side,variant=variant,case=case):
                        self.assertEqual(len(actual),len(set(actual)))
                        self.assertEqual(set(actual),oracle(board,side,friends,enemies,mode))

    def test_multiple_screens_and_hard_endpoint(self):
        board={'d4':'M','d5':'V','d6':'P','d7':'s','d8':'v'}
        self.assertIn('d4d7',self.moves('base',board))
        self.assertNotIn('d4d8',self.moves('base',board))
        self.assertNotIn('d4d7',self.moves('missile',board))
        self.assertNotIn('d4d8',self.moves('missile',board))

    def test_mixed_wildcard_and_empty_sets(self):
        self.assertNotIn('d4d7',self.moves('mixed',{'d4':'M','d5':'P','d7':'v'}))
        self.assertIn('d4d7',self.moves('mixed',{'d4':'M','d5':'p','d7':'v'}))
        self.assertIn('d4d7',self.moves('all-enemy',{'d4':'M','d5':'V','d7':'v','d8':'v'}))
        self.assertNotIn('d4d8',self.moves('all-enemy',{'d4':'M','d5':'V','d7':'v','d8':'v'}))
        self.assertIn('d4d7',self.moves('empty-blockers',{'d4':'M','d5':'S','d7':'v'}))

    def test_walls_and_mobility(self):
        self.assertNotIn('d4d7',self.moves('enemy',{'d4':'M','d5':'V','d6':'*','d7':'v'}))
        path=Path(self.temp.name)/'limited.ini'
        path.write_text(self.config.read_text()+'\n[limited:missile]\nmobilityRegionWhiteCustomPiece1 = d4 d5 d6\n')
        # m is the first allocated custom type (native slots are explicitly defined).
        self.assertNotIn('d4d7',self.moves('limited',{'d4':'M','d5':'V','d7':'v'},config=path))

    def test_all_colour_and_pawn_bycatch(self):
        board={'d4':'M','d5':'V','d7':'v','c6':'V','d6':'P','e6':'p','c7':'s','e7':'R','c8':'r','d8':'v','e8':'P','f7':'V'}
        self.assertEqual(self.final('missile',board,'d4d7'),rj.fen({'h1':'K','h8':'k','d5':'V','f7':'V'},side='b'))

    def test_priority_over_passive_burn_and_immunity(self):
        board={'d4':'M','d5':'V','d7':'v','e7':'fd','e6':'p'}
        for variant in ('passive','immune'):
            final=self.final(variant,board,'d4d7')
            self.assertNotIn('fd',final);self.assertNotIn('p',final);self.assertNotIn('M',final)

    def test_frozen_source_and_immunity(self):
        board={'d4':'M','d5':'V','d7':'v','e5':'fd'}
        self.assertFalse(any(m.startswith('d4') for m in self.moves('freeze',board)))
        self.assertIn('d4d7',self.moves('freeze-immune',board))

    def test_destroying_emitter_thaws_survivor(self):
        board={'d4':'M','d5':'V','e6':'fd','f6':'R'}
        self.assertNotIn('f6f7',self.moves('freeze',board))
        self.assertIn('f6f7',self.moves('freeze',board,moves='d4d6 h8g8'))

    def test_no_chain_reaction(self):
        final=self.final('missile',{'d4':'M','d5':'V','d7':'v','e7':'m','f7':'V'},'d4d7')
        self.assertIn('V',final);self.assertNotIn('m',final)
        self.assertEqual(final,rj.fen({'h1':'K','h8':'k','d5':'V','f7':'V'},side='b'))

    def test_dead_missile_does_not_promote(self):
        board={'d4':'M','d5':'V','d7':'v'}
        moves=self.moves('promote',board)
        self.assertIn('d4d7',moves);self.assertNotIn('d4d7+',moves)
        self.final('promote',board,'d4d7')
        self.assertIn('d4e4+',self.moves('promote',{'d4':'M','e4':'v'}))
        self.assertNotIn('d4e4',self.moves('promote',{'d4':'M','e4':'v'}))
        self.assertIn('d4d6',moves);self.assertNotIn('d4d6+',moves)

    def test_last_promotion_requires_space_for_a_future_screen(self):
        for variant in ('last','last-hard'):
            self.assertIn('d5d7+',self.moves(variant,{'d5':'M'}))
            self.assertIn('d4d2+',self.moves(variant,{'d4':'m'},side='b'))

    def test_native_pawn_quiet_and_capturing_jumps(self):
        for target in ({},{'d8':'v'}):
            board={'d6':'P','d7':'V',**target}
            moves=self.moves('pawn-missile',board)
            self.assertEqual(sum(m.startswith('d6d8') for m in moves),1)
            self.assertIn('d6d8',moves)
            self.final('pawn-missile',board,'d6d8')

    def test_live_pawn_quiet_jump_uses_mandatory_promotion(self):
        board={'d6':'P','d7':'V'}
        moves=self.moves('pawn-live',board)
        self.assertIn('d6d8r',moves);self.assertNotIn('d6d8',moves)
        self.final('pawn-live',board,'d6d8r')

    def test_range_jump_does_not_enable_en_passant(self):
        scenarios=[('pawn-live',{'d2':'P','d3':'V','c4':'p'},'d2d4','w'),
                   ('pawn-live',{'d2':'P','d3':'V','c5':'p'},'d2d5','w'),
                   ('pawn-live',{'d2':'P','d3':'V','d4':'v','c4':'p'},'d2d4','w'),
                   ('pawn-live',{'d7':'p','d6':'v','c5':'P'},'d7d5','b'),
                   ('initial-live',{'d2':'M','d3':'V','c4':'p'},'d2d4','w')]
        for variant,board,move,side in scenarios:
            position=rj.fen({'h1':'K','h8':'k',**board},side=side)
            final=self.final(variant,position,move)
            self.assertEqual(final.split()[3],'-')

    def test_overlapping_base_leap_emits_one_automatic_effect(self):
        board={'d4':'M','d5':'V','d6':'v'}
        moves=self.moves('leaper',board)
        self.assertEqual(moves.count('d4d6'),1)
        self.assertNotIn('M',self.final('leaper',board,'d4d6'))

    def test_reverse_queries_keep_attackers_colour(self):
        for variant in ('royal','royal-forward'):
            board={'d1':'K','h1':None,'d7':'m','d5':'s'}
            self.assertIn('Checkers: d7',self.output(variant,board))
            board['d5']='S';self.assertIn('Checkers: \n',self.output(variant,board))
            board={'d1':'M','d7':'k','h8':None,'d3':'S'}
            self.assertIn('Checkers: d1',self.output(variant,board,side='b'))
            board['d3']='s';self.assertIn('Checkers: \n',self.output(variant,board,side='b'))
        self.assertIn('Checkers: \n',self.output('royal',{'d1':'K','h1':None,'d7':'m'}))

    def test_quiet_jump_is_not_a_direct_attack(self):
        self.assertIn('Checkers: \n',self.output('royal-quiet',{'d1':'K','h1':None,'d7':'m','d5':'s'}))

    def test_off_ray_capture_and_quiet_blast_threats(self):
        board={'d4':'m','d5':'v','d6':'V','e6':'K','h1':None}
        self.assertIn('Checkers: d4',self.output('royal',board))
        board['d6']='S';self.assertIn('Checkers: \n',self.output('royal',board))
        board['d6']=None;board['e5']='S'
        self.assertIn('Checkers: d4',self.output('royal-quiet-missile',board))

    def test_mutually_immune_direct_target(self):
        board={'d4':'m','d5':'v','d6':'M','e6':'K','h1':None}
        self.assertIn('Checkers: d4',self.output('royal',board))
        self.assertIn('Checkers: \n',self.output('royal-immune',board))

    def test_blocker_replacement_during_legality(self):
        board={'a1':'K','h1':None,'g1':'m','d1':'v','d2':'S','f1':'v'}
        self.assertIn('d2d1',self.moves('royal',board))
        self.final('royal',board,'d2d1')

    def search_case(self,board,allowed,score,variant='capture',restrict=False):
        position=rj.fen({'h1':'K','h8':'k',**board})
        with subprocess.Popen([self.engine,'load',str(self.config)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as p:
            timer=threading.Timer(40,p.kill);timer.start()
            try:
                command='go depth 3'+(' searchmoves '+' '.join(allowed) if restrict else '')
                p.stdin.write(f'setoption name UCI_Variant value {variant}\nposition fen {position}\n{command}\n');p.stdin.flush();lines=[]
                for line in p.stdout:
                    lines.append(line)
                    if line.startswith('bestmove'):break
                p.stdin.write('quit\n');p.stdin.flush();_,err=p.communicate(timeout=10)
                self.assertEqual(p.returncode,0,err);output=''.join(lines)
                self.assertIn('score '+score,output)
                best=re.search(r'^bestmove (\S+)',output,re.M).group(1)
                self.assertIn(best,allowed)
            finally:timer.cancel()

    def test_search_finds_capturing_and_quiet_blast_wins(self):
        self.search_case({'d4':'M','d5':'V','d7':'v','e7':'k','h8':None},['d4d7'],'mate 1')
        self.search_case({'d4':'M','d5':'V','e7':'k','h8':None},['d4d6','d4d7','d4d8'],'mate 1',variant='quiet')

    def test_self_and_mutual_royal_destruction(self):
        for board in [{'d4':'M','d5':'V','d7':'v','c7':'K','h1':None},
                      {'d4':'M','d5':'V','d7':'v','c7':'K','e7':'k','h1':None,'h8':None}]:
            self.search_case(board,['d4d7'],'mate -1',restrict=True)

    def test_parser_rejects_invalid_modes_and_sets(self):
        path=Path(self.temp.name)/'invalid.ini'
        options=['rangeJumpPieces = m:R:{s=other}','rangeJumpPieces = m:R:{s=}',
                 'rangeJumpPieces = m:R:{s=friend,s=enemy}','rangeJumpPieces = m:R:{=both}',
                 'rangeJumpPieces = m:R:{missing=enemy}','rangeJumpPieces = -',
                 'rangeJumpPieces = m:mcR:{}','rangeJumpPieces = m:mmR:{}',
                 'rangeJumpPieces = m:c:{}','missileEffectPieces = {missing}']
        for option in options:
            with self.subTest(option=option):
                path.write_text(self.config.read_text()+'\n[invalid:missile]\n'+option+'\n')
                p=subprocess.run([self.engine,'load',str(path)],input='uci\nquit\n',text=True,capture_output=True,timeout=120)
                self.assertEqual(p.returncode,0);self.assertNotIn(' var invalid',p.stdout)
                self.assertRegex(p.stderr,r'rangeJumpPieces - |missileEffectPieces - ')

    def test_requested_8x10_fixture(self):
        if int(os.environ.get('BOARD_SIZE','8'))<10:self.skipTest('build supporting ten ranks only')
        path=Path(__file__).parent/'fixtures/missile-chess.ini'
        position=next(line.split('=',1)[1].strip() for line in path.read_text().splitlines() if line.startswith('startFen'))
        moves=self.moves('missile-chess',position,config=path)
        self.assertEqual(len(moves),52);self.assertIn('a1b1',moves)
        self.assertIn('a1a7',moves);self.assertNotIn('a1a8',moves)
        self.assertEqual(self.final('missile-chess',position,'a1a4',config=path).split()[0].count('M'),1)
        self.assertEqual(self.final('missile-chess',position,'a1b1',config=path).split()[0].count('M'),2)
        castle='8/4k3/8/8/8/8/8/8/R3K2R/8 w KQ - 0 1'
        self.assertIn('e2g2',self.moves('missile-chess',castle,config=path))
        self.assertIn('e2c2',self.moves('missile-chess',castle,config=path))
        black_double='8/4k3/3p4/8/4P3/8/8/8/4K3/8 b - - 0 1'
        self.assertIn('e6d7',self.moves('missile-chess',black_double,config=path,moves='d8d6'))
        white_double='8/4k3/8/8/8/4p3/8/3P4/4K3/8 w - - 0 1'
        self.assertIn('e5d4',self.moves('missile-chess',white_double,config=path,moves='d3d5'))
        promotion='8/4k3/3P4/8/8/8/8/8/4K3/8 w - - 0 1'
        self.assertIn('d8d9q',self.moves('missile-chess',promotion,config=path))

    def test_high_slot_full_board(self):
        if os.environ.get('BOARD_SIZE')!='19' or int(os.environ.get('PIECE_SLOTS','64'))<128:self.skipTest('19x19 high-slot build only')
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
        self.assertIn('j10j18',self.moves('high',position,config=path))
        self.assertIn('j10j17',self.moves('high',position,config=path))
        self.assertNotIn('HX',self.output('high',position,moves='j10j17',config=path).split('Fen: ')[1].splitlines()[0])
        board['j12']='p';self.assertNotIn('j10j18',self.moves('high',rj.fen(board,size=19),config=path))


if __name__=='__main__':unittest.main()
