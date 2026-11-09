#!/usr/bin/env python3
"""Coordinate atoms and Taikyoku Free Eagle sweeps, with independent geometry."""
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import threading
import unittest

from range_jumps import DIRECTIONS, fen


class FreeEagle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'eagle.ini'
        text = '''[eagle]
commoner = k
piece = fe:QDAHGf(4,4)j[1..2]Qfj[3]B +fe:Q
piece = p:W +p:F
piece = sh:W
piece = fd:K
piece = bs:K
piece = tk:W
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
lionMovePieces = fe(0804020180402010)
taikyokuFreeEagleMultiCapturePieces = {fe}
startFen = 7,k/8/8/8/3,FE,4/8/8/7,K w - - 0 1
[sweep:eagle]
piece = fe:j63Q
lionMovePieces = fe(0000000000000000)
[sweep-clear:sweep]
taikyokuFreeEagleMultiCapturePieces = {}
[sweep-dash:sweep]
taikyokuFreeEagleMultiCapturePieces = -
[sweep-prohibited:sweep]
prohibitedCaptures = fe:sh
[eagle-prohibited:eagle]
prohibitedCaptures = fe:sh
[sweep-immune:sweep]
mutuallyImmuneTypes = fe
[sweep-royal:sweep]
commoner = -
king = k
extinctionValue = none
[sweep-mobility:sweep]
mobilityRegionWhiteCustomPiece1 = *1 *2 *3 *4 *5 *6
[sweep-hands:sweep]
pieceDrops = true
capturesToHand = true
[sweep-loop:sweep-hands]
dropLoop = true
[sweep-promotion:sweep-hands]
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{} mandatory:{iic}
[sweep-split:sweep-promotion]
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{iicu} mandatory:{iicp}
[sweep-transform:sweep]
transformOnCapturePieces = {bs,tk}
transformOnCapturePolicy = choose
[sweep-first:sweep-transform]
transformOnCapturePolicy = first
[sweep-last:sweep-transform]
transformOnCapturePolicy = last
[sweep-trading:sweep]
tradingRule = fe:[any,{sh}]
[sweep-trading-protected:sweep]
tradingRule = fe:[any!,{sh}]
[sweep-counter:sweep]
tradingRuleCounterstrike = {sh}
[sweep-burn:sweep]
burnPassivePieceTypes = {fd}
[sweep-active:sweep-burn]
burnActivePieceTypes = {fe}
[sweep-active-royal:sweep-active]
commoner = -
king = k
extinctionValue = none
[sweep-transformed-burn-royal:sweep-royal]
burnActivePieceTypes = {fd}
burnOnPromotePieces = {fe}
transformOnCapturePieces = {bs:fd}
[sweep-freeze:sweep]
freezeEffectPieces = {fd}
[sweep-duplicate:eagle]
lionMovePieces = fe(FFFFFFFFFFFFFFFF)
lionDogMovePieces = fe:FFFFFFFFFFFF
[sweep-dog-identity:sweep]
lionDogMovePieces = fe:000000000010
'''
        # Separate variants avoid mutating the movement tables during a query.
        for name, atom in [('n','(2,1)'), ('nswap','(1,2)'), ('h','(3,0)'), ('g','(3,3)'),
                           ('four','(4,4)'), ('long','(7,2)'), ('huge','(2147483647,0)'),
                           ('forward','f(4,4)'), ('capture','c(2,1)'), ('quiet','m(2,1)'),
                           ('native','N')]:
            text += f'[coord-{name}:sweep-clear]\npiece = fe:{atom}\n'
        cls.config.write_text(text)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, variant, board, side='w', move='', commands=None, config=None):
        position = board if isinstance(board, str) else fen(board, side)
        p = subprocess.run([self.engine, 'load', str(config or self.config)], text=True,
                           input=f'setoption name UCI_Variant value {variant}\nposition fen {position} moves {move}\n'
                                 + (commands or 'd\ngo perft 1\n') + 'quit\n',
                           capture_output=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def moves(self, variant, board, side='w'):
        out = self.output(variant, board, side)
        self.assertIn('Nodes searched:', out, out)
        result = re.findall(r'^(\S+): \d+$', out, re.M)
        self.assertEqual(len(result), len(set(result)), out)
        return set(result)

    def after(self, variant, board, move, expected, side='w'):
        self.assertIn(move, self.moves(variant, board, side))
        out = self.output(variant, board, side, move)
        text = re.search(r'^Fen: (.+)', out, re.M).group(1)
        self.assertEqual(text.split()[0].split('[')[0], fen(expected).split()[0], out)
        fresh = self.output(variant, text)
        self.assertEqual(re.search(r'^Key: (\S+)', out, re.M).group(1),
                         re.search(r'^Key: (\S+)', fresh, re.M).group(1))
        return text

    @staticmethod
    def oracle(board, origin, side, prohibited=()):
        result = {}
        f0, r0 = ord(origin[0]) - 97, int(origin[1:])
        for df, dr in DIRECTIONS:
            prefix = 4 if df and dr == (1 if side == 'w' else -1) else 3
            route, victims = [], set()
            for step in range(1, prefix + 1):
                f, r = f0 + df * step, r0 + dr * step
                if not (0 <= f < 8 and 1 <= r <= 8): break
                s = chr(97 + f) + str(r)
                p = board.get(s)
                if p and (p == '*' or p.isupper() == (side == 'w') or p.lstrip('+').lower() in prohibited): break
                route.append(s)
                if p: victims.add(s)
            if len(route) != prefix: continue
            result[origin + ''.join(route)] = (route[-1], set(victims))
            for step in range(prefix + 1, 9):
                f, r = f0 + df * step, r0 + dr * step
                if not (0 <= f < 8 and 1 <= r <= 8): break
                s = chr(97 + f) + str(r)
                p = board.get(s)
                if p and (p == '*' or p.isupper() == (side == 'w') or p.lstrip('+').lower() in prohibited): break
                captured = victims | ({s} if p else set())
                result[origin + ''.join(route) + s] = (s, captured)
                if p: break
        return result

    def test_coordinate_atom_symmetry_bounds_and_modifiers(self):
        for side in ['w', 'b']:
            board = {'d4':'FE' if side == 'w' else 'fe','h1':'K','a8':'k'}
            for name, m, n in [('n',2,1),('nswap',1,2),('h',3,0),('g',3,3),('four',4,4),('long',7,2),('huge',2147483647,0)]:
                expected = set()
                for df, dr in {(a*s,b*t) for a,b in [(m,n),(n,m)] for s in [-1,1] for t in [-1,1]}:
                    f,r = 3+df,4+dr
                    if 0 <= f < 8 and 1 <= r <= 8:
                        to = chr(97+f)+str(r)
                        if to not in board or board[to].isupper() != (side == 'w'): expected.add('d4'+to)
                got = {s for s in self.moves('coord-'+name,board,side) if s.startswith('d4')}
                self.assertEqual(got,expected,(name,side))
            self.assertEqual(self.moves('coord-n',board,side),self.moves('coord-native',board,side))
            expected = {'d4h8'} if side == 'w' else set()
            self.assertEqual({s for s in self.moves('coord-forward',board,side) if s.startswith('d4')},expected)
        board = {'d4':'FE','e6':'p','b5':'P','a8':'k','h1':'K'}
        self.assertEqual({s for s in self.moves('coord-capture',board) if s.startswith('d4')},{'d4e6'})
        self.assertNotIn('d4e6',self.moves('coord-quiet',board))
        self.assertIn('d4f5',self.moves('coord-quiet',board))

    def test_compulsory_length_empty_squares_and_same_ray_tail(self):
        board = {'a1':'FE','a2':'p','a4':'p','a7':'p','h1':'K','h8':'k'}
        moves = self.moves('sweep',board)
        expected = self.oracle(board,'a1','w')
        self.assertEqual({s for s in moves if s.startswith('a1')},set(expected))
        self.assertIn('a1a2a3a4',moves)
        self.assertIn('a1a2a3a4a7',moves)
        self.assertNotIn('a1a2a3',moves)
        self.assertNotIn('a1a2a3a4a8',moves)
        self.after('sweep',board,'a1a2a3a4a7',{'a7':'FE','h1':'K','h8':'k'})
        board = {'a1':'FE','b2':'p','c3':'p','d4':'p','e5':'p','g7':'p','h1':'K','a8':'k'}
        self.assertNotIn('a1b2c3d4',self.moves('sweep',board))
        self.after('sweep',board,'a1b2c3d4e5g7',{'g7':'FE','h1':'K','a8':'k'})

    def test_random_sweeps_against_independent_oracle(self):
        rng = random.Random(4043)
        squares=[chr(97+f)+str(r) for f in range(8) for r in range(1,9)]
        for side in ['w','b']:
            for _ in range(12):
                board={'d4':'FE' if side=='w' else 'fe','h1':'K','a8':'k'}
                for s in rng.sample([s for s in squares if s not in board],12):board[s]=rng.choice(['p','P','sh','SH','*'])
                expected=self.oracle(board,'d4',side,{'sh'})
                moves={m for m in self.moves('sweep-prohibited',board,side) if m.startswith('d4')}
                self.assertEqual(moves,set(expected),board)
                if expected:
                    move=rng.choice(list(expected));to,victims=expected[move]
                    after={s:p for s,p in board.items() if s not in victims and s!='d4'};after[to]=board['d4']
                    self.after('sweep-prohibited',board,move,after,side)

    def test_friendly_prohibited_wall_freeze_and_mobility(self):
        for victim in ['P','sh','*']:
            board={'a1':'FE','a2':'p','a3':victim,'h1':'K','h8':'k'}
            self.assertNotIn('a1a2a3a4',self.moves('sweep-prohibited',board))
        board={'a1':'FE','a2':'p','a5':'P','h1':'K','h8':'k'}
        moves=self.moves('sweep',board)
        self.assertIn('a1a2a3a4',moves)
        self.assertNotIn('a1a2a3a4a5',moves)
        self.assertNotIn('a1a2a3a4a6',moves)
        board={'d4':'FE','d5':'p','h1':'K','h8':'k'}
        self.assertNotIn('d4d5d6d7',self.moves('sweep-mobility',board))
        board['e4']='fd'
        self.assertFalse(any(m.startswith('d4') for m in self.moves('sweep-freeze',board)))

    def test_genuine_capture_hands_promotion_and_victim_states(self):
        board={'a1':'FE','a2':'p','a4':'p','h1':'K','h8':'k'}
        out=self.after('sweep-hands',board,'a1a2a3a4a6',{'a6':'FE','h1':'K','h8':'k'})
        self.assertRegex(out,r'\[P,P\]')
        five={'a1':'FE','b2':'p','c3':'p','d4':'p','e5':'p','g7':'p','h1':'K','a8':'k'}
        out=self.after('sweep-hands',five,'a1b2c3d4e5g7',{'g7':'FE','h1':'K','a8':'k'})
        self.assertRegex(out,r'\[P,P,P,P,P\]')
        moves=self.moves('sweep-promotion',board)
        self.assertIn('a1a2a3a4a6+',moves)
        self.assertNotIn('a1a2a3a4a6',moves)
        moves=self.moves('sweep-split',board)
        self.assertIn('a1a2a3a4a6',moves);self.assertIn('a1a2a3a4a6+',moves)
        board['a4']='+p'
        moves=self.moves('sweep-split',board)
        self.assertNotIn('a1a2a3a4a6',moves);self.assertIn('a1a2a3a4a6+',moves)
        out=self.output('sweep-loop',board,move='a1a2a3a4a6')
        self.assertRegex(re.search(r'^Fen: (.+)',out,re.M).group(1),r'\[(?:\+P,P|P,\+P)\]')

    def test_capture_order_transformations_and_trading(self):
        board={'a1':'FE','a2':'p','a3':'bs','a4':'tk','h1':'K','h8':'k'}
        route='a1a2a3a4a6'
        moves=self.moves('sweep-transform',board)
        self.assertIn(route+'bs',moves);self.assertIn(route+'tk',moves);self.assertNotIn(route,moves)
        self.assertIn(route+'bs',self.moves('sweep-first',board))
        self.assertNotIn(route+'tk',self.moves('sweep-first',board))
        self.assertIn(route+'tk',self.moves('sweep-last',board))
        for square in ['b2','c3','d4','e5','g7']:
            board={'a1':'FE','b2':'p','c3':'p','d4':'p','e5':'p','g7':'p','h1':'K','a8':'k'}
            board[square]='sh'
            self.assertNotIn('a1b2c3d4e5g7',self.moves('sweep-trading',board))
            board['h7']='fd'
            self.assertNotIn('a1b2c3d4e5g7',self.moves('sweep-trading-protected',board))

    def test_prefix_passive_burners_are_directly_captured(self):
        board={'a1':'FE','a3':'fd','h1':'K','h8':'k'}
        self.after('sweep-burn',board,'a1a2a3a4',{'a4':'FE','h1':'K','h8':'k'})
        board['b4']='fd'
        self.after('sweep-burn',board,'a1a2a3a4',{'b4':'fd','h1':'K','h8':'k'})

    def test_sweep_active_and_transformation_burn_threats(self):
        board={'a1':'fe','a2':'P','a3':'FD','b4':'K','h8':'k'}
        self.assertRegex(self.output('sweep-active-royal',board),r'Checkers: a1')
        board={'a1':'fe','b2':'P','c3':'P','d4':'BS','f5':'K','h8':'k'}
        self.assertRegex(self.output('sweep-transformed-burn-royal',board),r'Checkers: a1')

    def test_sweep_and_jump_same_endpoint_remain_distinct(self):
        board={'a1':'FE','a2':'p','a3':'p','h1':'K','h8':'k'}
        moves=self.moves('eagle',board)
        self.assertIn('a1a4',moves);self.assertIn('a1a2a3a4',moves)
        self.after('eagle',board,'a1a4',{'a4':'FE','a2':'p','a3':'p','h1':'K','h8':'k'})
        self.after('eagle',board,'a1a2a3a4',{'a4':'FE','h1':'K','h8':'k'})
        board['a2']='sh'
        moves=self.moves('eagle-prohibited',board)
        self.assertIn('a1a4',moves)
        self.assertNotIn('a1a2a3a4',moves)
        board={'a1':'FE','h1':'K','h8':'k'}
        moves=self.moves('eagle',board)
        self.assertIn('a1a4',moves);self.assertNotIn('a1a2a3a4',moves)
        board['a2']='p';board['a3']='p';board['a4']='p'
        moves=self.moves('sweep-duplicate',board)
        self.assertIn('a1a2a3a4',moves)  # Supplied once by Lion Dog's identical route.
        board={'a1':'FE','a3':'p','h1':'K','h8':'k'}
        moves=self.moves('sweep-dog-identity',board)
        self.assertIn('a1a3a4',moves)
        self.assertIn('a1a2a3a4',moves)  # Different compound paths remain distinct.

    def test_royal_threat_and_check_evasions(self):
        board={'a1':'fe','a2':'P','a3':'K','h8':'k'}
        out=self.output('sweep-royal',board)
        self.assertRegex(out,r'Checkers: a1')
        self.assertNotIn('a3a4',self.moves('sweep-royal',board))
        self.assertIn('a3b3',self.moves('sweep-royal',board))

    def test_reset_and_invalid_syntax(self):
        board={'a1':'FE','a2':'p','h1':'K','h8':'k'}
        for name in ['sweep-clear','sweep-dash']:
            self.assertFalse(any(m.startswith('a1') for m in self.moves(name,board)))
        for atom in ['(2,)','(,1)','(2,1','(2,1))','(-2,1)','(0,0)','(2147483648,1)','n(4,4)','p(4,4)','(2,1)3','(Q)']:
            path=Path(self.temp.name)/'bad.ini';path.write_text(self.config.read_text()+'\n[bad:sweep-clear]\npiece = fe:'+atom+'\n')
            p=subprocess.run([self.engine,'check',str(path)],capture_output=True,text=True,timeout=90)
            self.assertIn('coordinate',p.stderr.lower(),atom+p.stderr)
        path.write_text(self.config.read_text()+'\n[bad:sweep]\ntaikyokuFreeEagleMultiCapturePieces = {missing}\n')
        p=subprocess.run([self.engine,'check',str(path)],capture_output=True,text=True,timeout=90)
        self.assertIn('taikyokuFreeEagleMultiCapturePieces - Invalid',p.stderr)

    def test_documented_configuration_and_royal_capture_search(self):
        fixture=Path(__file__).with_name('fixtures')/'taikyoku-free-eagle.ini'
        board={'a1':'FE','b2':'p','c3':'p','d4':'p','e5':'p','g7':'p','h1':'K','a8':'k'}
        out=self.output('taikyoku-free-eagle-test',board,config=fixture)
        self.assertRegex(out,r'(?m)^a1b2c3d4e5g7: 1$')
        self.assertRegex(out,r'(?m)^a1b2a1: 1$')
        board['b2']='k';board.pop('a8')
        with subprocess.Popen([self.engine,'load',str(self.config)],stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True) as p:
            timer=threading.Timer(60,p.kill);timer.start()
            try:
                p.stdin.write('setoption name Use NNUE value false\nsetoption name UCI_Variant value sweep\n'
                              +'position fen '+fen(board)+'\ngo depth 2 searchmoves a1b2c3d4e5g7\n')
                p.stdin.flush();lines=[]
                for line in p.stdout:
                    lines.append(line)
                    if line.startswith('bestmove'):break
                p.stdin.write('quit\n');p.stdin.flush();p.wait(timeout=10)
                out=''.join(lines)
                self.assertEqual(p.returncode,0,out)
                self.assertIn('score mate 1',out)
                self.assertIn('bestmove a1b2c3d4e5g7',out)
            finally:timer.cancel()

    def test_wide_board_high_slot_and_long_leaps(self):
        size=int(os.environ.get('BOARD_SIZE','8'));slots=int(os.environ.get('PIECE_SLOTS','64'))
        if size < 19 or slots < 128:self.skipTest('Wide board and piece catalogue only')
        def file_name(n):
            out=''
            while True:
                out=chr(97+n%26)+out;n=n//26-1
                if n<0:return out
        def position(board):
            rows=[]
            for r in range(size,0,-1):
                row=[];empty=0
                for f in range(size):
                    p=board.get(file_name(f)+str(r))
                    if p:
                        if empty:row.append(str(empty));empty=0
                        row.append(p)
                    else:empty+=1
                if empty:row.append(str(empty))
                rows.append(','.join(row))
            return '/'.join(rows)+' w - - 0 1'
        path=Path(self.temp.name)/'wide.ini'
        path.write_text(f'''[wide-eagle]
maxFile = {size}
maxRank = {size}
commoner = k
customPiece1 = p:W
customPiece{slots-39} = fe:({size-1},1)
castling = false
taikyokuFreeEagleMultiCapturePieces = {{fe}}
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
''')
        edge=file_name(size-1)+str(size)
        board={'a1':'FE','b2':'p','c3':'p','d4':'p','e5':'p',edge:'p',
               'a'+str(size):'k',file_name(size-1)+'1':'K'}
        root=self.output('wide-eagle',position(board),config=path)
        moves=set(re.findall(r'^(\S+): \d+$',root,re.M))
        self.assertIn('a1b'+str(size),moves)
        self.assertIn('a1'+file_name(size-1)+'2',moves)
        route='a1b2c3d4e5'+edge
        self.assertIn(route,moves)
        after=self.output('wide-eagle',position(board),move=route,config=path)
        expected={edge:'FE','a'+str(size):'k',file_name(size-1)+'1':'K'}
        actual=re.search(r'^Fen: (.+)',after,re.M).group(1)
        self.assertEqual(actual.split()[0],position(expected).split()[0])
        fresh=self.output('wide-eagle',actual,config=path)
        self.assertEqual(re.search(r'^Key: (\S+)',after,re.M).group(1),
                         re.search(r'^Key: (\S+)',fresh,re.M).group(1))


if __name__ == '__main__':
    unittest.main()
