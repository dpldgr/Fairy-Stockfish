#!/usr/bin/env python3
"""Engine regressions for high-ID movement, promotion, drops and capabilities.

STOCKFISH selects the engine; PIECE_SLOTS and GATING describe its build.
The same tests work on an 8x8 or larger executable.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class PieceSlots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.slots = (int(os.environ.get('PIECE_SLOTS', '64')) + 63) // 64 * 64
        cls.gating = os.environ.get('GATING', 'yes') == 'yes'
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'slots.ini'
        # The last non-royal custom slot, immediately below the reserved one.
        last = cls.slots - 39
        cls.config.write_text(f'''
[slot-promotion]
commoner = k
customPiece{last} = h:W
piece = l:fW +l:<h>
castling = false
promotionRegionMandatoryWhite = *8
promotionRegionMandatoryBlack = *1
promotionPolicy = optional:{{}} mandatory:{{oi}}
extinctionValue = loss
extinctionPieceTypes = k
startFen = 7,k/8/8/8/8/8/8/7,K w - - 0 1
[slot-drop:slot-promotion]
pieceDrops = true
capturesToHand = true
dropRegionWhiteCustomPiece{last} = a1
dropRegionBlackCustomPiece{last} = a8
[slot-flip:slot-drop]
dropPromoted = true
dropRegionWhiteCustomPiece1 = b1
dropRegionBlackCustomPiece1 = b8
[slot-gating:chess]
gating = true
seirawanGating = true
''')
        if os.environ.get('BOARD_SIZE') == '19':
            with cls.config.open('a') as config:
                config.write('[slot-large:slot-promotion]\nmaxFile = 19\nmaxRank = 19\n'
                             'promotionRegionMandatoryWhite = *19\n'
                             'startFen = ' + '/'.join(['18,k'] + ['19'] * 17 + ['18,K'])
                             + ' w - - 0 1\n')
                dense_fen = '/'.join(['18,k'] + [','.join(['A'] * 19)] * 7
                                     + ['19'] * 10 + ['18,K']) + ' w - - 0 1'
                config.write('[slot-nnue-limit]\nmaxFile=19\nmaxRank=19\n'
                             'commoner=k\nimmobile=a\ncastling=false\n'
                             'extinctionValue=loss\nextinctionPieceTypes=k\n'
                             'startFen=' + dense_fen + '\n')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_engine(self, commands, args=()):
        result = subprocess.run([self.engine, *args], input=commands,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def moves(self, variant, fen, played=''):
        output = self.run_engine(f'setoption name UCI_Variant value {variant}\n'
                                 f'position fen {fen} moves {played}\nd\ngo perft 2\nquit\n',
                                 ('load', str(self.config)))
        self.assertIn('Nodes searched:', output)
        return {m.group(1) for m in re.finditer(r'^(\S+): \d+$', output, re.M)}, output

    def test_both_colours_promote_to_high_slot_and_move(self):
        for side, fen, promotion, reply, target, expected in (
            ('w', '7,k/2,L,5/8/8/8/8/8/7,K w - - 0 1',
             'c7c8+', 'h8g8', 'c8', {'c8b8', 'c8d8', 'c8c7'}),
            ('b', '7,k/8/8/8/8/8/2,l,5/7,K b - - 0 1',
             'c2c1+', 'h1g1', 'c1', {'c1b1', 'c1d1', 'c1c2'})):
            with self.subTest(side=side):
                moves, _ = self.moves('slot-promotion', fen)
                self.assertIn(promotion, moves)
                self.assertNotIn(promotion[:-1], moves)
                after, output = self.moves('slot-promotion', fen, promotion + ' ' + reply)
                self.assertEqual({m for m in after if m.startswith(target)}, expected)
                resulting_fen = re.search(r'^Fen: (.+)$', output, re.M).group(1)
                reloaded, _ = self.moves('slot-promotion', resulting_fen)
                self.assertEqual(after, reloaded)

    def test_high_slot_drop_regions(self):
        for side, hand, square in (('w', 'H', 'a1'), ('b', 'h', 'a8')):
            fen = f'7,k/8/8/8/8/8/8/7,K[{hand}] {side} - - 0 1'
            moves, _ = self.moves('slot-drop', fen)
            self.assertEqual({m for m in moves if '@' in m}, {f'H@{square}'})

    def test_placed_type_region_for_promoted_drop(self):
        for side, hand, square, promoted in (('w', 'L', 'b1', 'a1'), ('b', 'l', 'b8', 'a8')):
            fen = f'7,k/8/8/8/8/8/8/7,K[{hand}] {side} - - 0 1'
            moves, _ = self.moves('slot-flip', fen)
            self.assertEqual({m for m in moves if '@' in m},
                             {f'L@{square}', f'+L@{promoted}'})

    def test_gating_capability(self):
        output = self.run_engine('uci\nquit\n', ('load', str(self.config)))
        variants = re.search(r'^option name UCI_Variant .*$', output, re.M).group(0).split(' var ')[1:]
        for name in ('seirawan', 'shouse', 'slot-gating'):
            self.assertEqual(name in variants, self.gating, name)
        self.assertIn('cambodian', variants)
        self.assertIn('crazyhouse', variants)
        if not self.gating:
            self.assertIn('requires Seirawan gating', output)

    def test_automatic_allocation_fills_every_ordinary_custom_slot(self):
        symbols = ['x' + chr(97 + i // 26) + chr(97 + i % 26)
                   for i in range(self.slots - 39)]
        definitions = '\n'.join(f'piece = {symbol}:K' for symbol in symbols)
        config = Path(self.temp.name) / 'full.ini'
        config.write_text('[slot-full]\ncommoner = k\ncastling = false\n'
                          + definitions + '\nextinctionValue = loss\nextinctionPieceTypes = k\n'
                          'startFen = 7,k/8/8/8/8/8/8/7,K w - - 0 1\n')
        output = self.run_engine('quit\n', ('check', str(config)))
        self.assertFalse(any(line and not line.startswith('Parsing variant:')
                             for line in output.splitlines()[1:]), output)
        with config.open('a') as stream:
            stream.write('piece = overflow:K\n')
        rejected = self.run_engine('quit\n', ('check', str(config)))
        self.assertIn('No free custom piece slot for base: overflow', rejected)

    @unittest.skipIf(int(os.environ.get('PIECE_SLOTS', '64')) <= 64, 'uses the wider move-list profile')
    def test_many_drop_types_exceed_the_old_move_list(self):
        symbols = ['x' + chr(97 + i // 26) + chr(97 + i % 26)
                   for i in range(self.slots - 39)]
        config = Path(self.temp.name) / 'many-drops.ini'
        # Ataxx supplies free drops. Replace its movement and enclosure rules
        # so each active type may be placed on any empty square.
        config.write_text('[many-drops:ataxx]\nmaxFile=8\nmaxRank=8\n'
                          'commoner=k\ncastling=false\nenclosingDrop=none\n'
                          'flipEnclosedPieces=none\n'
                          f'customPiece1 = {symbols[0]}:K\n'
                          + '\n'.join(f'piece = {symbol}:K' for symbol in symbols[1:])
                          + '\nstartFen = 7,k/8/8/8/8/8/8/7,K w - - 0 1\n')
        output = self.run_engine('setoption name UCI_Variant value many-drops\n'
                                 'position startpos\ngo perft 1\nquit\n',
                                 ('load', str(config)))
        expected = (self.slots - 38) * 62 + 3
        self.assertEqual(int(re.search(r'Nodes searched: (\d+)', output).group(1)), expected)

    @unittest.skipUnless(os.environ.get('BOARD_SIZE') == '19', 'requires a 19x19 build')
    def test_19x19_high_squares_and_high_types(self):
        fen = '/'.join(['18,k', 'L,18'] + ['19'] * 16 + ['18,K']) + ' w - - 0 1'
        moves, _ = self.moves('slot-large', fen)
        self.assertIn('a18a19+', moves)
        after, output = self.moves('slot-large', fen, 'a18a19+ s19r19')
        self.assertEqual({m for m in after if m.startswith('a19')}, {'a19a18', 'a19b19'})
        resulting_fen = re.search(r'^Fen: (.+)$', output, re.M).group(1)
        reloaded, _ = self.moves('slot-large', resulting_fen)
        self.assertEqual(after, reloaded)

    @unittest.skipUnless(os.environ.get('BOARD_SIZE') == '19', 'requires a 19x19 build')
    def test_nnue_feature_limit_falls_back_to_classical(self):
        output = self.run_engine('setoption name UCI_Variant value slot-nnue-limit\n'
                                 'setoption name Use NNUE value true\n'
                                 'setoption name EvalFile value slot-nnue-limit-missing.nnue\n'
                                 'position startpos\neval\nquit\n',
                                 ('load', str(self.config)))
        self.assertIn('Final evaluation', output)
        self.assertNotIn('NNUE evaluation using', output)


if __name__ == '__main__':
    unittest.main()
