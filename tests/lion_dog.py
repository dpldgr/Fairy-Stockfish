#!/usr/bin/env python3
"""Silverman Lion Dog routes through the engine's parser and real move generator."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest

DIRS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))


def fen(pieces=None, side='w'):
    pieces = {'h1': 'K', 'h8': 'k', **(pieces or {})}
    rows = []
    for rank in range(8, 0, -1):
        row, empty = [], 0
        for file in 'abcdefgh':
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


def route(bit, side='w', origin='d4'):
    direction, kind = divmod(bit, 6)
    df, dr = DIRS[(direction + (4 if side == 'b' else 0)) % 8]
    offsets = ((1, 2), (1, 0), (1, 2, 3), (1, 2, 1), (2, 3), (2, 1))[kind]
    return origin + ''.join(chr(ord(origin[0]) + df * n) + str(int(origin[1:]) + dr * n) for n in offsets)


class LionDog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'dog.ini'
        cls.config.write_text('''[dog]
commoner = k
customPiece1 = ld:KADGH
customPiece2 = v:W
castling = false
extinctionValue = loss
extinctionPieceTypes = k
lionDogMovePieces = ld:FFFFFFFFFFFF
startFen = 7,k/8/8/8/3,LD,4/8/8/7,K w - - 0 1
[dog-zero:dog]
lionDogMovePieces = ld:000000000000
[dog-turn:dog-zero]
lionMovePieces = ld:0000000000000002
[fiend:dog]
lionMovePieces = ld:FFFFFFFFFFFFFFFF
[dog-promote:dog]
gold = g
promotedPieceType = ld:g
promotionRegionOptionalWhite = -
promotionRegionOptionalBlack = -
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{} mandatory:{iic}
[dog-drop:dog]
pieceDrops = true
capturesToHand = true
[dog-prohibited:dog]
prohibitedCaptures = ld:v
[dog-mobility:dog]
mobilityRegionWhiteCustomPiece1 = d4 d5 d7
[dog-royal:dog]
commoner = -
king = k
extinctionPieceTypes = k
[dog-promoted-victims:dog-drop]
gold = g
promotedPieceType = v:g
[dog-pawn-choices:dog]
customPiece1 = d:KADGH
queen = q
rook = r
promotionPawnTypes = d
promotionPieceTypes = q r
promotionRegionOptionalWhite = -
promotionRegionMandatoryWhite = *
promotionPolicy = optional:{} mandatory:{iic}
[dog-limit:dog-promote]
promotionLimit = g:1
[dog-trading:dog]
tradingRule = ld:[any,{v}]
[dog-trading-double:dog]
tradingRule = ld:[dist2c,{v}]
[dog-attack:dog-royal]
customPiece1 = ld:W
lionDogMovePieces = ld:000000000004
''')
        with cls.config.open('a') as out:
            for bit in range(48):
                out.write(f'[dog-bit-{bit}:dog]\nlionDogMovePieces = ld:{1 << bit:012X}\n')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, name, position=None, moves='', depth=1, config=None):
        result = subprocess.run([self.engine, 'load', str(config or self.config)],
                                input=f'setoption name UCI_Variant value {name}\n'
                                      f'position fen {position or fen({"d4": "LD"})} moves {moves}\n'
                                      f'd\ngo perft {depth}\nquit\n',
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Nodes searched:', result.stdout)
        return result.stdout

    def moves(self, *args, **kwargs):
        output = self.output(*args, **kwargs)
        return re.findall(r'^(\S+): \d+$', output, re.M)

    def test_full_mask_has_all_48_routes_and_24_ordinary_moves(self):
        moves = self.moves('dog')
        dog = [m for m in moves if m.startswith('d4')]
        self.assertEqual(len(dog), 72)
        self.assertEqual(len(set(dog)), 72)
        self.assertEqual({m for m in dog if len(m) > 4}, {route(i) for i in range(48)})
        self.assertNotIn('d4d5d7', dog)  # no step followed by a two-square jump
        self.assertNotIn('d4d5d4d3', dog)  # no crossing the starting square

    def test_zero_mask_preserves_ordinary_piece_definition(self):
        moves = [m for m in self.moves('dog-zero') if m.startswith('d4')]
        self.assertEqual(len(moves), 24)
        self.assertTrue(all(len(m) == 4 for m in moves))

    def test_each_bit_and_colour(self):
        bits = [int(i) for i in os.environ.get('DOG_TEST_BITS', ','.join(map(str, range(48)))).split(',')]
        for side in ('w', 'b'):
            for bit in bits:
                with self.subTest(side=side, bit=bit):
                    moves = self.moves(f'dog-bit-{bit}', fen({'d4': 'LD' if side == 'w' else 'ld'}, side))
                    self.assertEqual({m for m in moves if m.startswith('d4') and len(m) > 4}, {route(bit, side)})

    def test_fiend_overlap_is_generated_once(self):
        moves = [m for m in self.moves('fiend') if m.startswith('d4')]
        self.assertEqual(len(moves), 120)  # 24 ordinary + 64 Lion + 32 additional
        self.assertEqual(len(set(moves)), len(moves))

    def test_lion_only_turn_can_coexist_with_zero_dog_mask(self):
        moves = [m for m in self.moves('dog-turn') if m.startswith('d4')]
        self.assertEqual(len(moves), 25)
        self.assertEqual([m for m in moves if len(m) > 4], ['d4d5e6'])

    def test_three_captures_and_retreat_capture_order_routes(self):
        position = fen({'d4': 'LD', 'd5': 'v', 'd6': 'v', 'd7': 'v'})
        for move in ('d4d5d6d7', 'd4d5d6d5', 'd4d6d7', 'd4d6d5'):
            with self.subTest(move=move):
                self.assertIn(move, self.moves('dog', position))
                output = self.output('dog', position, move)
                final = re.search(r'^Fen: (.+)$', output, re.M).group(1)
                self.assertIn('LD', final)
                expected_victims_left = 0 if move == 'd4d5d6d7' else 1
                self.assertEqual(final.split()[0].count('v'), expected_victims_left)

    def test_friend_blocks_steps_but_can_be_jumped_over(self):
        moves = self.moves('dog', fen({'d4': 'LD', 'd5': 'V'}))
        self.assertNotIn('d4d5d6d7', moves)
        self.assertIn('d4d6d7', moves)
        self.assertNotIn('d4d6d5', moves)
        moves = self.moves('dog', fen({'d4': 'LD', 'd6': 'V'}))
        self.assertNotIn('d4d5d6d7', moves)
        self.assertNotIn('d4d6d7', moves)
        self.assertIn('d4d7', moves)  # ordinary jump unaffected

    def test_capture_on_any_leg_forces_promotion(self):
        for victims in ({'d5': 'v'}, {'d6': 'v'}, {'d7': 'v'}):
            with self.subTest(victims=victims):
                position = fen({'d4': 'LD', **victims})
                moves = self.moves('dog-promote', position)
                self.assertIn('d4d5d6d7+', moves)
                self.assertNotIn('d4d5d6d7', moves)
                output = self.output('dog-promote', position, 'd4d5d6d7+')
                self.assertIn('+LD', re.search(r'^Fen: (.+)$', output, re.M).group(1))
        self.assertIn('d4d5d6d7', self.moves('dog-promote'))

    def test_intermediate_capture_prohibitions_and_mobility(self):
        self.assertNotIn('d4d5d6d7', self.moves('dog-prohibited', fen({'d4': 'LD', 'd6': 'v'})))
        self.assertNotIn('d4d5d6d7', self.moves('dog-mobility'))
        self.assertIn('d4d7', self.moves('dog-mobility'))

    def test_capture_to_hand_includes_all_three_victims(self):
        output = self.output('dog-drop', fen({'d4': 'LD', 'd5': 'v', 'd6': 'v', 'd7': 'v'}), 'd4d5d6d7')
        resulting_fen = re.search(r'^Fen: (.+)$', output, re.M).group(1)
        self.assertIn('[VVV]', resulting_fen)

    def test_mask_conflicts_rejected_during_load_and_check(self):
        for lion, dog in (('FFFFFFFFFFFFFFFF', '000000000000'), ('0000000000000000', 'FFFFFFFFFFFF')):
            config = Path(self.temp.name) / 'conflict.ini'
            config.write_text(self.config.read_text() + f'\n[conflict:dog]\nlionMovePieces=ld:{lion}\nlionDogMovePieces=ld:{dog}\n')
            for mode in ('load', 'check'):
                result = subprocess.run([self.engine, mode, str(config)], input='uci\nquit\n',
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Conflicting shared path', result.stderr)
                self.assertNotIn(' var conflict', result.stdout)

    def test_perft_undo_restores_position_and_key(self):
        position = fen({'d4': 'LD', 'd5': 'v', 'd6': 'v', 'd7': 'v'})
        result = subprocess.run([self.engine, 'load', str(self.config)],
                                input='setoption name UCI_Variant value dog\n'
                                      f'position fen {position}\nd\ngo perft 3\nd\nquit\n',
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = result.stdout
        self.assertGreater(int(re.search(r'Nodes searched: (\d+)', output).group(1)), 0)
        keys = re.findall(r'^Key: (\S+)', output, re.M)
        positions = re.findall(r'^Fen: (.+)', output, re.M)
        self.assertEqual(len(keys), 2)
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(positions[0], positions[1])

    def test_incremental_key_matches_fresh_position_after_every_route(self):
        for name, victims in (('dog', {'d5': 'v', 'd6': 'v', 'd7': 'v'}),
                              ('dog-promoted-victims', {'d5': '+v', 'd6': 'v', 'd7': '+v'}),
                              ('dog-promote', {'d5': 'v', 'd6': 'v', 'd7': 'v'})):
            for move in ('d4d5d6d7', 'd4d5d6d5', 'd4d6d7', 'd4d6d5'):
                with self.subTest(name=name, move=move):
                    output = self.output(name, fen({'d4': 'LD', **victims}), move + ('+' if name == 'dog-promote' else ''))
                    final = re.search(r'^Fen: (.+)', output, re.M).group(1)
                    key = re.search(r'^Key: (\S+)', output, re.M).group(1)
                    fresh = self.output(name, final)
                    self.assertEqual(key, re.search(r'^Key: (\S+)', fresh, re.M).group(1))

    def test_no_unpromoted_escape_when_promotion_limit_is_reached(self):
        moves = self.moves('dog-limit', fen({'d4': 'LD', 'd5': 'v', 'a1': 'G'}))
        self.assertNotIn('d4d5d6d7', moves)
        self.assertNotIn('d4d5d6d7+', moves)

    def test_pawn_style_choice_retains_route(self):
        position = fen({'d4': 'D', 'd5': 'v'})
        moves = self.moves('dog-pawn-choices', position)
        self.assertIn('d4d5d6d7q', moves)
        self.assertIn('d4d5d6d7r', moves)
        self.assertNotIn('d4d5d6d7', moves)
        for suffix in ('q', 'r'):
            output = self.output('dog-pawn-choices', position, 'd4d5d6d7' + suffix, depth=2)
            final = re.search(r'^Fen: (.+)', output, re.M).group(1)
            key = re.search(r'^Key: (\S+)', output, re.M).group(1)
            self.assertEqual(key, re.search(r'^Key: (\S+)', self.output('dog-pawn-choices', final), re.M).group(1))

    def test_search_preserves_ordered_route_and_promotion(self):
        position = fen({'d4': 'LD', 'd5': 'v', 'd6': 'v', 'd7': 'v', 'b5': 'ld'})
        for name, move in (('dog', 'd4d5d6d7'), ('dog-promote', 'd4d5d6d7+')):
            with self.subTest(name=name):
                with subprocess.Popen([self.engine, 'load', str(self.config)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as engine:
                    timer = threading.Timer(60, engine.kill)
                    timer.start()
                    try:
                        engine.stdin.write(f'setoption name UCI_Variant value {name}\n'
                                           f'position fen {position}\ngo depth 3 searchmoves {move}\n')
                        engine.stdin.flush()
                        lines = []
                        for line in engine.stdout:
                            lines.append(line)
                            if line.startswith('bestmove '):
                                break
                        engine.stdin.write('quit\n')
                        engine.stdin.flush()
                        _, errors = engine.communicate(timeout=10)
                        self.assertEqual(engine.returncode, 0, errors)
                        output = ''.join(lines)
                        self.assertIn('info depth 3 ', output)
                        self.assertRegex(output, r'(?m)^bestmove ' + re.escape(move) + r'(?: |$)')
                    finally:
                        timer.cancel()

    def test_trading_rule_sees_every_victim(self):
        for square in ('d5', 'd6', 'd7'):
            self.assertNotIn('d4d5d6d7', self.moves('dog-trading', fen({'d4': 'LD', square: 'v'})))
        self.assertIn('d4d5d6d7', self.moves('dog-trading-double', fen({'d4': 'LD', 'd7': 'v'})))
        for connectors in ({'d5': 'ld'}, {'d5': 'ld', 'd6': 'ld'}):
            self.assertNotIn('d4d5d6d7', self.moves('dog-trading-double',
                                                fen({'d4': 'LD', 'd7': 'v', **connectors})))

    def test_capture_removing_a_royal_shield_is_illegal(self):
        position = fen({'d4': 'LD', 'd5': 'v', 'a8': 'b'})
        # Declare a native bishop for this fixture's black attack on h1.
        config = Path(self.temp.name) / 'royal.ini'
        config.write_text(self.config.read_text() + '\n[dog-shield:dog-royal]\nbishop=b\n')
        moves = self.moves('dog-shield', position, config=config)
        self.assertNotIn('d4d5d6d7', moves)
        self.assertIn('d4d6d7', moves)

    def test_multi_leg_attack_and_discovered_check(self):
        position = fen({'d4': 'LD', 'h8': None, 'd7': 'k'}, 'b')
        output = self.output('dog-attack', position)
        self.assertRegex(output, r'Checkers:.*d4')
        config = Path(self.temp.name) / 'discovered.ini'
        config.write_text(self.config.read_text() + '\n[dog-discovered:dog-royal]\nrook=r\n')
        position = fen({'d4': 'LD', 'd5': 'v', 'a5': 'R', 'h8': None, 'h5': 'k'})
        output = self.output('dog-discovered', position, 'd4d5d6d7', config=config)
        self.assertRegex(output, r'Checkers:.*a5')

    def test_invalid_masks_are_rejected(self):
        for setting in ('ld:FFFF', 'ld:FFFFFFFFFFFFF', 'ld:FFFFFFFFFFFG', 'missing:FFFFFFFFFFFF'):
            config = Path(self.temp.name) / 'invalid.ini'
            config.write_text(self.config.read_text() + '\n[bad-dog:dog]\nlionDogMovePieces=' + setting + '\n')
            result = subprocess.run([self.engine, 'load', str(config)], input='uci\nquit\n',
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Invalid piece/mask', result.stderr)
            self.assertNotIn(' var bad-dog', result.stdout)


if __name__ == '__main__':
    unittest.main()
