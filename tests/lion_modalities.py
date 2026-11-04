#!/usr/bin/env python3
"""Complete-path Lion modalities and optional promotion-arrival burning."""
import os
from pathlib import Path
import random
import re
import subprocess
import unittest
import range_jumps as rj
import skip_rays as sr

class LionModalities(unittest.TestCase):
    command = classmethod(sr.SkipRays.command.__func__)
    output = sr.SkipRays.output
    moves = sr.SkipRays.moves
    tearDownClass = classmethod(sr.SkipRays.tearDownClass.__func__)

    @classmethod
    def setUpClass(cls):
        sr.SkipRays.setUpClass.__func__(cls)
        text = '''[lm:base]
piece = l:<immobile>
lionMovePieces = l(FFFFFFFFFFFFFFFF)
[lm-quiet:lm]
lionMovePieces = l(m:FFFFFFFFFFFFFFFF)
[lm-capture:lm]
lionMovePieces = l(c:FFFFFFFFFFFFFFFF)
[lm-mixed:lm]
lionMovePieces = l( m : AA00AA00AA00AA00 , c : 0804020180402010 )
[lm-inherit:lm-mixed]
lionMovePieces = l(c:0804020180402010)
[lm-untouched:lm-capture]
piece = y:W
lionMovePieces = y(0000000000000000)
[lm-ht:lm]
piece = l:jBjfbRjrlR3
lionMovePieces = l(c:0804020180402010)
[lm-lower:lm]
lionMovePieces = l(c000000000000000)
[lm-native:lm-capture]
commoner = -
king = k
extinctionValue = none
[lm-native-quiet:lm-native]
lionMovePieces = l(m:FFFFFFFFFFFFFFFF)
[lm-burn:lm-quiet]
burnActivePieceTypes = {l}
[lm-burn-capture:lm-burn]
lionMovePieces = l(c:FFFFFFFFFFFFFFFF)
[pb:base]
piece = f:K
piece = w:W +w:<f>
piece = v:F +v:<w>
burnActivePieceTypes = {f}
burnPassivePieceTypes = {f}
burnOnPromotePieces = {w}
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{all} mandatory:{}
[pb-off:pb]
burnOnPromotePieces = {}
[pb-immune:pb]
burnImmunePieces = {x}
[pb-capture:pb]
promotionPolicy = optional:{iic} mandatory:{}
[pb-split:pb]
promotionPolicy = optional:{iicu} mandatory:{iicp}
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
[pb-native:pb]
commoner = -
king = k
extinctionValue = none
[pb-native-capture:pb-native]
promotionPolicy = optional:{iic} mandatory:{}
[pb-limit:pb-native]
promotionLimit = f:1
[pb-choice:chess]
burnActivePieceTypes = {q}
burnOnPromotePieces = {p}
[pb-path:pb]
lionMovePieces = w(FFFFFFFFFFFFFFFF)
[pb-last:pb]
promotionRegionOptionalWhite = *8
promotionPolicy = optional:{last} mandatory:{}
piece = w:fW +w:<f>
'''
        if int(os.environ.get('BOARD_SIZE','8')) >= 16:
            text += '\n[pb-area:pb]\ntenjikuTripleStepPieceTypes = {w}\n'
        cls.extra = Path(cls.temp.name)/'modalities.ini'
        cls.extra.write_text(text)
        startup = cls.command(f'setoption name VariantPath value {cls.extra}\nisready\n')
        if ' - ' in startup and ('Invalid' in startup or 'no active-burning' in startup):
            raise AssertionError(startup)

    def test_random_complete_path_oracle(self):
        rng = random.Random(91063)
        for variant, quiet, capture in [('lm', 0xffffffffffffffff, 0xffffffffffffffff),
                                        ('lm-quiet',0xffffffffffffffff,0),
                                        ('lm-capture',0,0xffffffffffffffff),
                                        ('lm-mixed',0xaa00aa00aa00aa00,0x0804020180402010),
                                        ('lm-lower',0xc000000000000000,0xc000000000000000)]:
            for side in ('w','b'):
                for case in range(4):
                    board={'d4':'L' if side=='w' else 'l','h1':'K','h8':'k'}
                    for f in range(1,6):
                        for r in range(2,7):
                            sq=chr(97+f)+str(r)
                            if sq!='d4' and rng.random()<.3: board[sq]=rng.choice(('x','X','*'))
                    expected=set()
                    for first,(df,dr) in enumerate(rj.DIRECTIONS):
                        if side=='b':df,dr=-df,-dr
                        via=chr(ord('d')+df)+str(4+dr)
                        for second,(ef,er) in enumerate(rj.DIRECTIONS):
                            if side=='b':ef,er=-ef,-er
                            to=chr(ord(via[0])+ef)+str(int(via[1:])+er)
                            visited={via,to}-{'d4'}
                            if any(board.get(s)=='*' or (board.get(s) and board[s].isupper()==(side=='w')) for s in visited):continue
                            has_capture=any(board.get(s) and board[s].isupper()!=(side=='w') for s in visited)
                            if (capture if has_capture else quiet)&(1<<(first*8+second)):expected.add('d4'+via+to)
                    with self.subTest(variant=variant,side=side,case=case):
                        actual={m for m in self.moves(variant,board,side) if m.startswith('d4')}
                        self.assertEqual(actual,expected)

    def test_capture_on_either_leg_and_igui(self):
        for board,move in [({'d5':'x'},'d4d5d6'),({'d6':'x'},'d4d5d6'),
                           ({'d5':'x','d6':'x'},'d4d5d6'),({'d5':'x'},'d4d5d4')]:
            self.assertIn(move,self.moves('lm-capture',{'d4':'L',**board}))
            self.assertNotIn(move,self.moves('lm-quiet',{'d4':'L',**board}))
        self.assertNotIn('d4d5d4',self.moves('lm-capture',{'d4':'L'}))
        self.assertIn('d4d5d4',self.moves('lm-quiet',{'d4':'L'}))

    def test_inheritance_replaces_mentioned_piece_only(self):
        self.assertFalse(any(m.startswith('d4') for m in self.moves('lm-inherit',{'d4':'L'})))
        self.assertIn('d4d5d4',self.moves('lm-inherit',{'d4':'L','d5':'x'}))
        self.assertIn('d4d5d6',self.moves('lm-untouched',{'d4':'L','d5':'x'}))
        self.assertNotIn('d4d5d6',self.moves('lm-untouched',{'d4':'L'}))

    def test_ht_ordinary_moves_survive_capture_only_mask(self):
        self.assertIn('d4d6',self.moves('lm-ht',{'d4':'L'}))
        self.assertNotIn('d4d5d4',self.moves('lm-ht',{'d4':'L'}))
        self.assertIn('d4d5d4',self.moves('lm-ht',{'d4':'L','d5':'x'}))

    def test_direct_attack_queries_respect_modality(self):
        board={'h1':None,'d2':'K','d4':'l'}
        out=self.output('lm-native',board)
        self.assertIn('d4',re.search(r'^Checkers: *(.*)',out,re.M).group(1))
        out=self.output('lm-native-quiet',board)
        self.assertEqual(re.search(r'^Checkers: *(.*)',out,re.M).group(1),'')

    def test_quiet_burn_paths_do_not_become_direct_captures(self):
        board={'d4':'L','e6':'x'}
        self.assertIn('d4d5d6',self.moves('lm-burn',board))
        out=self.output('lm-burn',board,moves='d4d5d6',commands='d\n')
        self.assertNotIn('x',re.search(r'^Fen: (.*)',out,re.M).group(1).split()[0])
        self.assertNotIn('d4d5d6',self.moves('lm-burn-capture',board))

    def test_promotion_only_burns_when_selected_and_enabled(self):
        board={'d4':'W','e5':'x'}
        for variant,move,expected in [('pb','d4d5',True),('pb','d4d5+',False),('pb-off','d4d5+',True),('pb-immune','d4d5+',True)]:
            out=self.output(variant,board,moves=move,commands='d\n')
            self.assertEqual('x' in re.search(r'^Fen: (.*)',out,re.M).group(1).split()[0],expected,(variant,move,out))
        self.assertNotIn('d4d5+',self.moves('pb-capture',board))
        self.assertIn('d4d5+',self.moves('pb-capture',{'d4':'W','d5':'x','e5':'x'}))

    def test_passive_burn_precedes_promotion_bonus(self):
        board={'d4':'W','e5':'f'}
        self.assertNotIn('d4d5+',self.moves('pb',board))
        out=self.output('pb',board,moves='d4d5',commands='d\n')
        fen=re.search(r'^Fen: (.*)',out,re.M).group(1).split()[0]
        self.assertIn('f',fen);self.assertNotIn('W',fen);self.assertNotIn('+W',fen)

    def test_pawn_choice_controls_burn(self):
        position=rj.fen({'h1':'K','h8':'k','a7':'P','b8':'r'})
        for suffix,burn in [('q',True),('r',False),('b',False),('n',False)]:
            out=self.output('pb-choice',position,moves='a7a8'+suffix,commands='d\n')
            fen=re.search(r'^Fen: (.*)',out,re.M).group(1).split()[0]
            self.assertEqual('r' not in fen,burn)

    def test_promotion_threat_requires_policy_and_available_target(self):
        board={'h1':None,'e6':'K','d4':'w'}
        out=self.output('pb-native',board)
        self.assertIn('d4',re.search(r'^Checkers: *(.*)',out,re.M).group(1))
        out=self.output('pb-limit',{**board,'a8':'f'})
        self.assertNotIn('d4',re.search(r'^Checkers: *(.*)',out,re.M).group(1))
        out=self.output('pb-native-capture',board)
        self.assertNotIn('d4',re.search(r'^Checkers: *(.*)',out,re.M).group(1))
        # +v occupies W's slot but cannot promote a second time.
        out=self.output('pb-native',{**board,'d4':'+v'})
        self.assertNotIn('d4',re.search(r'^Checkers: *(.*)',out,re.M).group(1))

    def test_burned_promoted_victim_does_not_force_promotion(self):
        moves=self.moves('pb-split',{'d4':'W','d5':'x','e5':'+v'})
        self.assertIn('d4d5',moves)
        self.assertIn('d4d5+',moves)

    def test_path_and_area_promotion_burn(self):
        board={'d4':'W','e7':'x'}
        out=self.output('pb-path',board,moves='d4d5d6+',commands='d\n')
        self.assertNotIn('x',re.search(r'^Fen: (.*)',out,re.M).group(1).split()[0])
        if int(os.environ.get('BOARD_SIZE','8'))>=16:
            out=self.output('pb-area',{'d4':'W','e8':'x'},moves='d4d5d6d7+',commands='d\n')
            self.assertNotIn('x',re.search(r'^Fen: (.*)',out,re.M).group(1).split()[0])

    def test_invalid_syntax_and_burn_sources_rejected(self):
        bad=['l:FFFFFFFFFFFFFFFF','l()','l(m:FFFFFFFFFFFFFFFF,)','l(m:FFFFFFFFFFFFFFFF,m:FFFFFFFFFFFFFFFF)',
             'l(FFFFFFFFFFFFFFFF,c:FFFFFFFFFFFFFFFF)','l(z:FFFFFFFFFFFFFFFF)','l(c:FFFFFFFFFFFFFFFG)',
             'l(c:FFFFFFFFFFFFFFFF) l(m:FFFFFFFFFFFFFFFF)','l((FFFFFFFFFFFFFFFF))','l(FFFFFFFFFFFFFFF)']
        path=Path(self.temp.name)/'invalid-modes.ini'
        text=self.config.read_text()+self.extra.read_text()
        text+=''.join(f'\n[bad-{i}:lm]\nlionMovePieces = {value}\n' for i,value in enumerate(bad))
        text+='\n[bad-dog:lm]\nlionMovePieces = l(c:0000000000000011)\nlionDogMovePieces = l:000000000003\n'
        text+='\n[bad-burn:pb]\nburnOnPromotePieces = {x}\n'
        path.write_text(text)
        result=subprocess.run([self.binary,'load',str(path)],input='uci\nquit\n',capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stderr)
        for i in range(len(bad)):self.assertNotIn(' var bad-'+str(i)+' ',result.stdout)
        self.assertNotIn(' var bad-burn ',result.stdout)
        self.assertNotIn(' var bad-dog ',result.stdout)
        self.assertIn('Conflicting shared path',result.stderr)
        self.assertIn('burnOnPromotePieces -',result.stderr)

if __name__=='__main__': unittest.main()
