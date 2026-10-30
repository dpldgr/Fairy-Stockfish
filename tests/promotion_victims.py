#!/usr/bin/env python3
"""Promotion policy selection by each victim's pre-capture promoted flag."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from hook_moves import fen


class PromotionVictims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'promotion-victims.ini'
        cls.config.write_text('''[base]
commoner = k
queen = q
gold = g
piece = em:U +em:<queen>
piece = v:W +v:<gold>
castling = false
extinctionValue = loss
extinctionPieceTypes = k
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{iicu} mandatory:{iicp}
startFen = 7k/8/8/8/3,EM,4/8/8/7K w - - 0 1
[limited:base]
promotionLimit = q:1
[pawn-choice:base]
piece = d:U
promotionPawnTypes = d
promotionPieceTypes = q
queen = q
[native-pawn:base]
pawn = p
promotionPieceTypes = q
queen = q
[lion:base]
piece = em:KADGH +em:<queen>
lionMovePieces = em:FFFFFFFFFFFFFFFF
[dog:base]
piece = em:KADGH +em:<queen>
lionDogMovePieces = em:FFFFFFFFFFFF
[hook:base]
piece = em:R +em:<queen>
hookMovePieces = em:R-sR:2
[double:base]
piece = em:K +em:<queen>
piece = s:K
doubleMovePieces = em:s-s:2
[hook-choice:pawn-choice]
piece = d:R
hookMovePieces = d:R-sR:2
[demotion:hook]
pieceDemotion = true
hookMovePieces = q:R-sR:2
[last-base:base]
piece = em:fW +em:<queen>
promotionRegionOptionalWhite = *8
promotionRegionOptionalBlack = *1
[inherit:base]
promotionPolicyWhite<em> = optional:{inherit,iicp} mandatory:{}
''')
        with cls.config.open('a') as out:
            for stem in ('oi', 'ii', 'io'):
                for suffix in ('c', 'cu', 'cp'):
                    out.write(f'''[{stem}{suffix}:base]
promotionRegionOptionalWhite = *5 *6 *7 *8
promotionRegionOptionalBlack = *1 *2 *3 *4
promotionPolicy = optional:{{{stem}{suffix}}} mandatory:{{}}
''')
            for token in ('lastc', 'lastcu', 'lastcp', 'last', 'all'):
                out.write(f'[{token}:last-base]\npromotionPolicy = optional:{{{token}}} mandatory:{{}}\n')
            out.write('[split:base]\npromotionPolicy = optional:{iicu,iicp} mandatory:{}\n'
                      '[unsplit:base]\npromotionPolicy = optional:{iic} mandatory:{}\n')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, name, board, side='w', moves='', commands='d\ngo perft 1\n'):
        result = subprocess.run([self.engine, 'load', str(self.config)],
                                input=f'setoption name UCI_Variant value {name}\n'
                                      f'position fen {fen(board, side)} moves {moves}\n' + commands + 'quit\n',
                                text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def moves(self, *args, **kwargs):
        output = self.output(*args, **kwargs)
        self.assertIn('Nodes searched:', output)
        return set(re.findall(r'^(\S+): \d+$', output, re.M))

    def test_each_transition_and_victim_state_both_colours(self):
        for side in ('w', 'b'):
            ranks = {'oi': (4, 5), 'ii': (5, 6), 'io': (5, 4)} if side == 'w' else {
                'oi': (5, 4), 'ii': (4, 3), 'io': (4, 5)}
            for stem, (start, end) in ranks.items():
                origin, target = 'd' + str(start), 'd' + str(end)
                for promoted in (False, True):
                    victim = ('+' if promoted else '') + ('v' if side == 'w' else 'V')
                    board = {origin: 'EM' if side == 'w' else 'em', target: victim}
                    for suffix in ('c', 'cu', 'cp'):
                        with self.subTest(side=side, stem=stem, promoted=promoted, suffix=suffix):
                            moves = self.moves(stem + suffix, board, side)
                            self.assertIn(origin + target, moves)
                            self.assertEqual(origin + target + '+' in moves,
                                             suffix == 'c' or (suffix == 'cp') == promoted)

    def test_conditional_optional_and_mandatory(self):
        for side in ('w', 'b'):
            for promoted in (False, True):
                board = {'d4': 'EM' if side == 'w' else 'em',
                         'f6': ('+' if promoted else '') + ('v' if side == 'w' else 'V')}
                moves = self.moves('base', board, side)
                self.assertIn('d4f6+', moves)
                self.assertEqual('d4f6' in moves, not promoted)
                self.assertIn('d4a1', moves)
                self.assertNotIn('d4a1+', moves)
                output = self.output('base', board, side, 'd4f6+')
                self.assertIn('+EM' if side == 'w' else '+em', output)

    def test_pawn_style_and_native_pawn(self):
        for name, origin, target, mover, suffix in (('pawn-choice','d4','f6','D','q'),
                                                    ('native-pawn','d4','e5','P','q')):
            for victim in ('v', '+v'):
                moves = self.moves(name, {origin: mover, target: victim})
                self.assertIn(origin + target + suffix, moves)
                self.assertEqual(origin + target in moves, victim == 'v')

    def test_status_is_not_inferred_from_the_piece_type(self):
        # Both victims occupy the Gold slot; only +v carries promotion metadata.
        for victim, optional in (('g', True), ('v', True), ('g~', False), ('v~', False), ('+v', False)):
            moves = self.moves('base', {'d4': 'EM', 'f6': victim})
            self.assertIn('d4f6+', moves)
            self.assertEqual('d4f6' in moves, optional)

    def test_promoted_status_is_preserved_in_fen_and_hash(self):
        keys = []
        for victim in ('g', 'g~', '+v'):
            output = self.output('base', {'d4':'EM', 'f6':victim}, commands='d\n')
            keys.append(re.search(r'^Key: (\S+)', output,re.M).group(1))
            self.assertIn(victim, re.search(r'^Fen: (.+)', output,re.M).group(1))
        self.assertNotEqual(keys[0],keys[1])
        self.assertEqual(keys[1],keys[2])
        output = self.output('base', {'d4':'EM','f6':'g~'}, side='b', moves='f6f5', commands='d\n')
        final = re.search(r'^Fen: (.+)',output,re.M).group(1)
        result = subprocess.run([self.engine,'load',str(self.config)],
                                input=f'setoption name UCI_Variant value base\nposition fen {final}\nd\nquit\n',
                                text=True,capture_output=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(re.search(r'^Key: (\S+)',output,re.M).group(1),
                         re.search(r'^Key: (\S+)',result.stdout,re.M).group(1))

    def test_promotion_limit_does_not_allow_declining_mandatory(self):
        for victim in ('v', '+v'):
            moves = self.moves('limited', {'d4': 'EM', 'f6': victim, 'a1': 'Q'})
            self.assertNotIn('d4f6+', moves)
            self.assertEqual('d4f6' in moves, victim == 'v')

    def test_last_capture_suffixes_both_colours(self):
        for side in ('w', 'b'):
            origin, target = ('d7','d8') if side == 'w' else ('d2','d1')
            for promoted in (False, True):
                board = {origin: 'EM' if side == 'w' else 'em',
                         target: ('+' if promoted else '') + ('v' if side == 'w' else 'V')}
                for name in ('lastc','lastcu','lastcp','last','all'):
                    moves = self.moves(name, board, side)
                    self.assertEqual(origin + target + '+' in moves,
                                     name in ('lastc','last','all') or (name == 'lastcp') == promoted)

    def test_capture_alias_and_inherit(self):
        for victim in ('v', '+v'):
            board = {'d4': 'EM', 'f6': victim}
            self.assertEqual(self.moves('split', board), self.moves('unsplit', board))
            moves = self.moves('inherit', board)
            self.assertIn('d4f6', moves)
            self.assertIn('d4f6+', moves)

    def test_all_multi_capture_routes_mandatory_wins(self):
        routes = (('lion','d4d5d6',('d5','d6')), ('dog','d4d5d6d7',('d5','d6','d7')),
                  ('dog','d4d5d6d5',('d5','d6')), ('dog','d4d6d7',('d6','d7')),
                  ('dog','d4d6d5',('d6','d5')), ('hook','d4d6f6',('d6','f6')),
                  ('double','d4d5e6',('d5','e6')))
        for name, route, victims in routes:
            for promoted_index in range(-1, len(victims)):
                with self.subTest(name=name, route=route, promoted_index=promoted_index):
                    board = {'d4': 'EM', **{s: '+v' if i == promoted_index else 'v' for i,s in enumerate(victims)}}
                    moves = self.moves(name, board)
                    self.assertIn(route + '+', moves)
                    self.assertEqual(route in moves, promoted_index == -1)
                    output = self.output(name, board, moves=route+'+', commands='d\ngo perft 2\nd\n')
                    positions = re.findall(r'^Fen: (.+)', output, re.M)
                    keys = re.findall(r'^Key: (\S+)', output, re.M)
                    self.assertEqual(positions[0], positions[1])
                    self.assertEqual(keys[0], keys[1])
                    fresh = subprocess.run([self.engine,'load',str(self.config)],
                                           input=f'setoption name UCI_Variant value {name}\nposition fen {positions[0]}\nd\nquit\n',
                                           text=True,capture_output=True,timeout=120)
                    self.assertEqual(fresh.returncode, 0, fresh.stderr)
                    self.assertEqual(keys[0], re.search(r'^Key: (\S+)', fresh.stdout,re.M).group(1))

    def test_hook_choice_and_demotion_keep_the_route(self):
        for name, mover, suffix in (('hook-choice','D','q'), ('demotion','+EM','-')):
            for victim in ('v', '+v'):
                board = {'d4': mover, 'd6': victim, 'f6': 'v'}
                route = 'd4d6f6'
                moves = self.moves(name, board)
                self.assertIn(route + suffix, moves)
                self.assertEqual(route in moves, victim == 'v')
                output = self.output(name, board, moves=route+suffix, commands='d\ngo perft 2\nd\n')
                keys = re.findall(r'^Key: (\S+)', output, re.M)
                self.assertEqual(keys[0], keys[1])

    def test_invalid_tokens_and_mandatory_last_rejected(self):
        valid = subprocess.run([self.engine,'check',str(self.config)],capture_output=True,text=True,timeout=120)
        self.assertEqual(valid.returncode,0,valid.stderr)
        self.assertNotIn('Invalid promotion policy', valid.stderr)
        for policy in ('mandatory:{lastcu}', 'mandatory:{lastcp}', 'optional:{iiqu}', 'optional:{iicx}'):
            path = Path(self.temp.name) / 'bad.ini'
            path.write_text(self.config.read_text() + '\n[bad:base]\npromotionPolicy = ' + policy + '\n')
            result = subprocess.run([self.engine,'check',str(path)],capture_output=True,text=True,timeout=120)
            self.assertIn('promotionPolicy',result.stderr)
            self.assertIn('Invalid', result.stderr)


if __name__ == '__main__':
    unittest.main()
