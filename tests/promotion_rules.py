#!/usr/bin/env python3
"""Regression tests for promotion rules through the engine's real move lists."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

RULES = '''
[chu:shogi]
promotionRegionOptionalWhite = *7 *8 *9
promotionRegionOptionalBlack = *1 *2 *3
promotionRegionMandatoryWhite = -
promotionRegionMandatoryBlack = -
promotionPolicy = optional:{oi,iic,ioc} mandatory:{}
promotionPolicyWhite<shogiPawn> = optional:{inherit,last}
promotionPolicyBlack<shogiPawn> = optional:{inherit,last}
immobilityIllegal = false
pieceDrops = false
capturesToHand = false
[explicit-shogi:shogi]
promotionRegionOptionalWhite = *7 *8 *9
promotionRegionOptionalBlack = *1 *2 *3
promotionRegionMandatoryWhite<shogiPawn> = *9
promotionRegionMandatoryBlack<shogiPawn> = *1
promotionRegionMandatoryWhite<lance> = *9
promotionRegionMandatoryBlack<lance> = *1
promotionRegionMandatoryWhite<shogiKnight> = *8 *9
promotionRegionMandatoryBlack<shogiKnight> = *1 *2
promotionPolicy = optional:{all} mandatory:{oi}
[empty:chu]
promotionRegionOptionalWhite<shogiPawn> = -
promotionRegionOptionalBlack<shogiPawn> = -
[clear:chu]
promotionPolicyWhite<shogiPawn> = optional:{}
promotionPolicyBlack<shogiPawn> = optional:{}
[white-only:chu]
promotionPolicyBlack = optional:{}
promotionPolicyBlack<shogiPawn> = optional:{}
[parent:chu]
promotionPolicyWhite = optional:{oi}
[child:parent]
promotionPolicyWhite<shogiPawn> = optional:{inherit,last}
[last-only:chu]
promotionPolicy = optional:{last} mandatory:{}
promotionPolicyWhite<shogiPawn> = optional:{inherit}
promotionPolicyBlack<shogiPawn> = optional:{inherit}
[last-quiet:last-only]
promotionPolicyWhite<shogiPawn> = optional:{lastq}
[last-capture:last-only]
promotionPolicyWhite<shogiPawn> = optional:{lastc}
[mobility:last-only]
mobilityRegionWhiteShogiPawn = *1 *2 *3 *4 *5 *6 *7 *8
[capture-only:last-only]
shogiPawn = -
customPiece1 = p:cfW
promotedPieceType = p:g
promotionPolicyWhite<customPiece1> = optional:{last}
promotionPolicyBlack<customPiece1> = optional:{last}
[mandatory-capture:chess]
promotionPieceTypes = -
promotionPawnTypes = -
promotedPieceType = n:q
promotionRegionOptionalWhite = *7 *8
promotionRegionMandatoryWhite = *7 *8
promotionPolicy = optional:{oiq} mandatory:{oic,iic}
[silver-zone:chu]
promotionRegionOptionalWhite<silver> = *8 *9
[mandatory-silver:chu]
promotionRegionMandatoryWhite<silver> = *8 *9
promotionPolicyWhite<silver> = mandatory:{oi}
[legacy-new-mix]
maxRank = 8
maxFile = 8
king = k
shogiPawn = p
gold = g
promotedPieceType = p:g
promotionRegionWhite = *7 *8
promotionPolicy = optional:{oi}
castling = false
[normal-pawn:chess]
promotionRegionMandatoryWhite<pawn> = *8
promotionRegionMandatoryBlack<pawn> = *1
promotionPolicy = mandatory:{oi}
[inside-pawn:normal-pawn]
promotionPolicy = mandatory:{ii}
[standalone]
maxRank = 8
maxFile = 8
king = k
shogiPawn = p
gold = g
promotedPieceType = p:g
promotionRegionOptionalWhite = *7 *8
promotionPolicy = optional:{oi}
castling = false
immobilityIllegal = false
'''


def fen(pieces, side='w', size=9):
    rows = []
    for rank in range(size, 0, -1):
        row, empty = '', 0
        for file in range(size):
            piece = pieces.get(chr(ord('a') + file) + str(rank))
            if piece:
                row += (str(empty) if empty else '') + piece
                empty = 0
            else:
                empty += 1
        rows.append(row + (str(empty) if empty else ''))
    return '/'.join(rows) + f'[] {side} - - 0 1'


class PromotionRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'promotion.ini'
        cls.config.write_text(RULES)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, variant, position, commands='go perft 1', config=None):
        result = subprocess.run([self.engine, 'load', str(config or self.config)],
            input=f'setoption name UCI_Variant value {variant}\nposition fen {position}\n{commands}\nquit\n',
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def moves(self, variant, position, config=None):
        output = self.output(variant, position, config=config)
        self.assertIn('Nodes searched:', output)
        return {m.group(1) for line in output.splitlines()
                if (m := re.fullmatch(r'(\S+): \d+', line))}

    def position(self, pieces, side='w'):
        return fen({'i1': 'K', 'i9': 'k', **pieces}, side)

    def test_chu_matrix_both_colours(self):
        for side in ('w', 'b'):
            for start, end in ((4, 5), (6, 7), (7, 8), (7, 6)):
                for capture in (False, True):
                    with self.subTest(side=side, start=start, end=end, capture=capture):
                        sr, tr = (start, end) if side == 'w' else (10-start, 10-end)
                        source = f'c{sr}'
                        dest = f'{"b" if end < start else "c"}{tr}'
                        pieces = {source: 'S' if side == 'w' else 's'}
                        if capture: pieces[dest] = 'p' if side == 'w' else 'P'
                        move = source + dest
                        moves = self.moves('chu', self.position(pieces, side))
                        self.assertIn(move, moves)
                        self.assertEqual(move+'+' in moves, start == 6 or (start >= 7 and capture))

    def test_pawn_extra_lance_no_extra(self):
        for side in ('w', 'b'):
            source, dest = ('c8','c9') if side == 'w' else ('c2','c1')
            for piece, promote in (('P',True),('L',False)):
                with self.subTest(side=side, piece=piece):
                    moves = self.moves('chu', self.position({source: piece if side == 'w' else piece.lower()},side))
                    self.assertIn(source+dest, moves)
                    self.assertEqual(source+dest+'+' in moves, promote)

    def test_empty_overrides(self):
        for variant in ('empty','clear'):
            moves = self.moves(variant, self.position({'c8':'P'}))
            self.assertIn('c8c9', moves)
            self.assertNotIn('c8c9+', moves)

    def test_colour_override(self):
        self.assertIn('c6c7+', self.moves('white-only',self.position({'c6':'S'})))
        self.assertNotIn('c4c3+', self.moves('white-only',self.position({'c4':'s'},'b')))

    def test_inherit_uses_colour_parent(self):
        self.assertNotIn('c7c8+', self.moves('child',self.position({'c7':'P','c8':'p'})))
        self.assertIn('c8c9+', self.moves('child',self.position({'c8':'P'})))

    def test_shogi_matches_explicit_mandatory_regions(self):
        for side in ('w','b'):
            for piece, rank in (('P',8),('L',8),('N',6),('N',7)):
                with self.subTest(side=side,piece=piece):
                    rank = rank if side == 'w' else 10-rank
                    position = self.position({f'c{rank}':piece if side == 'w' else piece.lower()},side)
                    self.assertEqual(self.moves('shogi',position),self.moves('explicit-shogi',position))

    def test_walls_but_not_other_pieces(self):
        for blocker, promote in (('*',True),('p',False),('P',False)):
            with self.subTest(blocker=blocker):
                moves = self.moves('last-only',self.position({'c7':'P','c9':blocker}))
                self.assertIn('c7c8', moves)
                self.assertEqual('c7c8+' in moves, promote)

    def test_mobility_region(self):
        moves = self.moves('mobility',self.position({'c7':'P'}))
        self.assertIn('c7c8',moves)
        self.assertIn('c7c8+',moves)

    def test_last_quiet_and_capture_are_independent(self):
        for variant, quiet_allowed, capture_allowed in (
                ('last-quiet', True, False), ('last-capture', False, True)):
            with self.subTest(variant=variant):
                quiet = self.moves(variant,self.position({'c8':'P'}))
                capture = self.moves(variant,self.position({'c8':'P','c9':'p'}))
                self.assertEqual('c8c9+' in quiet,quiet_allowed)
                self.assertEqual('c8c9+' in capture,capture_allowed)

    def test_capture_only_future_movement(self):
        moves = self.moves('capture-only',self.position({'c7':'P','c8':'p'}))
        self.assertIn('c7c8',moves)
        self.assertNotIn('c7c8+',moves)
        moves = self.moves('capture-only',self.position({'c8':'P','c9':'p'}))
        self.assertIn('c8c9',moves)
        self.assertIn('c8c9+',moves)

    def test_piece_zone_override_and_mandatory_precedence(self):
        self.assertNotIn('c6c7+',self.moves('silver-zone',self.position({'c6':'S'})))
        self.assertIn('c7c8+',self.moves('silver-zone',self.position({'c7':'S'})))
        self.assertIn('c4c3+',self.moves('silver-zone',self.position({'c4':'s'},'b')))
        moves = self.moves('mandatory-silver',self.position({'c7':'S'}))
        self.assertIn('c7c8+',moves)
        self.assertNotIn('c7c8',moves)

    def test_inside_mandatory_capture(self):
        moves = self.moves('mandatory-capture','7k/2N5/8/8/8/8/8/4K3 w - - 0 1')
        self.assertIn('c7e6',moves)
        self.assertNotIn('c7e6+',moves)
        moves = self.moves('mandatory-capture','4p2k/2N5/8/8/8/8/8/4K3 w - - 0 1')
        self.assertNotIn('c7e8',moves)
        self.assertIn('c7e8+',moves)

    def test_legacy_region_with_new_policy(self):
        position = fen({'h1':'K','h8':'k','c6':'P'},size=8)
        self.assertIn('c6c7+',self.moves('legacy-new-mix',position))
        position = fen({'h1':'K','h8':'k','c7':'P'},size=8)
        self.assertNotIn('c7c8+',self.moves('legacy-new-mix',position))

    def test_new_standalone_defaults(self):
        moves = self.moves('standalone',fen({'h1':'K','h8':'k','c7':'P'},size=8))
        self.assertIn('c7c8',moves)
        self.assertNotIn('c7c8+',moves)

    def test_wolf_elgam_encodings(self):
        config = Path('variants.ini').resolve()
        cases = [('wolf','4k3/P7/8/8/8/8/8/8/8/4K3 w - - 0 1', {'+','q','w','f','r','b'}),
                 ('elgam','5k5/S10/11/11/11/11/11/11/11/5K5[] w - - 0 1', {'+','w'})]
        for variant, position, suffixes in cases:
            with self.subTest(variant=variant):
                output = self.output(variant,position,config=config)
                found = {m.group(1)[5:] for line in output.splitlines()
                         if (m := re.fullmatch(r'(a9a10\S*): \d+',line))}
                self.assertEqual(found,suffixes)
                for suffix in suffixes:
                    output = self.output(variant,position,f'position fen {position} moves a9a10{suffix}\nd',config)
                    result = next(line[5:] for line in output.splitlines() if line.startswith('Fen: '))
                    expected = ('+P' if variant=='wolf' else '+S') if suffix=='+' else suffix.upper()+('~' if variant=='elgam' else '')
                    self.assertTrue(result.startswith(expected),result)

    @unittest.skipUnless(os.environ.get('FSF_TEST_12X12') == '1',
                         'set FSF_TEST_12X12=1 with a 12x12-capable build')
    def test_chu_twelve_rank_board(self):
        config = Path(self.temp.name)/'chu12.ini'
        config.write_text(RULES + """
[chu12:chu]
maxRank = 12
maxFile = 12
promotionRegionOptionalWhite = *9 *10 *11 *12
promotionRegionOptionalBlack = *1 *2 *3 *4
""")
        probe = subprocess.run([self.engine,'load',str(config)],input='uci\nquit\n',
                               text=True,capture_output=True,timeout=30)
        self.assertEqual(probe.returncode,0,probe.stderr)
        if ' var chu12 ' not in probe.stdout.replace('\n',' ') + ' ':
            self.skipTest('requires a build with at least 12x12 capacity')
        for side in ('w','b'):
            for piece, start, end, capture, promote in (
                    ('P',11,12,False,True), ('L',11,12,False,False),
                    ('S',8,9,False,True), ('S',9,10,False,False),
                    ('S',9,10,True,True)):
                with self.subTest(side=side,piece=piece,capture=capture):
                    sr,tr = (start,end) if side=='w' else (13-start,13-end)
                    source,dest = f'c{sr}',f'c{tr}'
                    pieces = {'l1':'K','l12':'k',source:piece if side=='w' else piece.lower()}
                    if capture: pieces[dest] = 'p' if side=='w' else 'P'
                    moves = self.moves('chu12',fen(pieces,side,size=12),config)
                    self.assertIn(source+dest,moves)
                    self.assertEqual(source+dest+'+' in moves,promote)

    def test_bitbase_guard_respects_entry_policy(self):
        # Only an eight-rank build uses the KPK bitbase; larger builds take
        # the existing fallback for both definitions.
        position = '7k/5P2/5K2/8/8/8/8/8 w - - 0 1'
        normal = self.output('normal-pawn',position,'eval')
        inside = self.output('inside-pawn',position,'eval')
        normal_score = re.search(r'Final evaluation\s+([+-]?[0-9.]+)',normal)
        inside_score = re.search(r'Final evaluation\s+([+-]?[0-9.]+)',inside)
        self.assertIsNotNone(normal_score,normal)
        self.assertIsNotNone(inside_score,inside)
        self.assertLess(abs(float(inside_score.group(1))),10)
        self.assertGreaterEqual(float(normal_score.group(1)),float(inside_score.group(1)))
        if os.environ.get('FSF_EXPECT_KPK_BITBASE') == '1':
            self.assertGreater(float(normal_score.group(1)),20)

    def test_invalid_policies(self):
        for policy in ('mandatory:{last}','optional:{bad}','optional:{oi,}','optional:{oi} optional:{ii}'):
            with self.subTest(policy=policy):
                invalid = Path(self.temp.name)/'invalid.ini'
                invalid.write_text(f'[invalid:chess]\npromotionPolicy = {policy}\n')
                result = subprocess.run([self.engine,'check',str(invalid)],text=True,capture_output=True,timeout=30)
                self.assertIn('Invalid promotion policy',result.stderr)

    def test_line_order_independence(self):
        section = RULES.split('[chu:shogi]\n',1)[1].split('[explicit-shogi:',1)[0].strip()
        reordered = Path(self.temp.name)/'reordered.ini'
        reordered.write_text('[reordered:shogi]\n'+'\n'.join(reversed(section.splitlines()))+'\n')
        position = self.position({'c8':'P'})
        expected = self.output('chu',position)
        actual = self.output('reordered',position,config=reordered)
        pattern = r'^\S+: \d+$'
        self.assertEqual(re.findall(pattern,expected,re.M),re.findall(pattern,actual,re.M))


if __name__ == '__main__':
    unittest.main()
