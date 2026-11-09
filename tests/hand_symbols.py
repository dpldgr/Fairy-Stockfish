#!/usr/bin/env python3
"""FEN/SFEN whole-symbol hands, captures and search-root cloning regressions."""
from collections import Counter
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import unittest

import range_jumps as rj
import skip_rays as sr


class HandSymbols(unittest.TestCase):
    command = classmethod(sr.SkipRays.command.__func__)
    tearDownClass = classmethod(sr.SkipRays.tearDownClass.__func__)

    @classmethod
    def setUpClass(cls):
        cls.binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.slots = int(os.environ.get('PIECE_SLOTS', '64'))
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'hands.ini'
        cls.config.write_text(f'''
[hands]
commoner = k
piece = r:<rook>
piece = p:<shogiPawn>
piece = rr:K +rr:Q
piece = rh:fB
piece = rrh:N
customPiece{cls.slots - 39} = hz:W
castling = false
doubleStep = false
pieceDrops = true
capturesToHand = true
promotionRegionOptionalWhite = -
promotionRegionOptionalBlack = -
promotionRegionMandatoryWhite = -
promotionRegionMandatoryBlack = -
promotionPolicy = optional:{{}} mandatory:{{}}
extinctionValue = loss
extinctionPieceTypes = k
nMoveRule = 0
startFen = 7,k/8/8/8/8/8/8/K,7[] w - - 0 1
[promoted-drops:hands]
dropPromoted = true
[hand-loop:hands]
piece = rr:K +rr:<qq>
piece = qq:Q
dropLoop = true
''')
        if int(os.environ.get('BOARD_SIZE', '8')) >= 16 and cls.slots >= 128:
            cls.config.write_text(cls.config.read_text() + '\n' +
                                  (Path(__file__).parent / 'fixtures/dai-seireigi.ini').read_text())
        cls.engine = subprocess.Popen([cls.binary, 'load', str(cls.config)], text=True,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT)
        cls.lines = queue.Queue()
        def reader():
            for line in cls.engine.stdout:
                cls.lines.put(line)
            cls.lines.put(None)
        cls.reader = threading.Thread(target=reader, daemon=True)
        cls.reader.start()
        startup = cls.command('setoption name Use NNUE value false\nisready\n')
        assert 'piece -' not in startup, startup

    def fen(self, hand='', side='w', pieces=None, size=8):
        board = pieces or {'a1': 'K', chr(96 + size) + str(size): 'k'}
        value = rj.fen(board, side, size=size)
        return value.replace(' ', '[' + hand + '] ', 1)

    def position(self, value, variant='hands', sfen=False, moves='', perft=True):
        commands = (f'setoption name UCI_Variant value {variant}\n'
                    f'position {"sfen" if sfen else "fen"} {value} moves {moves}\nd\n')
        if perft:
            commands += 'go perft 1\n'
        out = self.command(commands + 'isready\n')
        # The synchronous helper waits for a perft result whenever requested.
        if perft:
            self.assertIn('Nodes searched:', out)
        return out

    @staticmethod
    def field(out, label):
        return re.search(r'^' + label + r': *(.*)', out, re.M)[1]

    @staticmethod
    def moves(out):
        return set(re.findall(r'^(\S+): \d+$', out, re.M))

    def roundtrip(self, out, variant='hands'):
        for label in ('Fen', 'Sfen'):
            with self.subTest(format=label):
                again = self.position(self.field(out, label), variant, sfen=label == 'Sfen')
                self.assertEqual(self.field(out, 'Key'), self.field(again, 'Key'))
                expected = self.field(out, 'Fen').split()
                actual = self.field(again, 'Fen').split()
                if label == 'Sfen':
                    # Standard SFEN does not carry the halfmove clock.
                    expected[-2] = actual[-2]
                self.assertEqual(expected, actual)
                self.assertEqual(self.moves(out), self.moves(again))

    def search(self, go):
        self.engine.stdin.write(go + '\n')
        self.engine.stdin.flush()
        output = []
        while True:
            line = self.lines.get(timeout=90)
            self.assertIsNotNone(line, ''.join(output))
            output.append(line)
            if line.startswith('bestmove '):
                return ''.join(output)

    def test_ambiguous_whole_symbols_and_separators(self):
        for hand, prefixes in [('RR', {'RR@'}), ('R,R', {'R@'}),
                               ('RRH', {'RRH@'}), ('R,RH', {'R@', 'RH@'}),
                               ('RR,R,RH,RRH', {'RR@', 'R@', 'RH@', 'RRH@'})]:
            with self.subTest(hand=hand):
                out = self.position(self.fen(hand))
                actual = {move.split('@')[0] + '@' for move in self.moves(out) if '@' in move}
                self.assertEqual(actual, prefixes)
                self.roundtrip(out)
        out = self.position(self.fen('R,R'))
        self.assertEqual(re.search(r'\[(.*?)\]', self.field(out, 'Fen'))[1], 'R,R')
        self.assertIn(' 2R ', self.field(out, 'Sfen'))

    def test_mixed_colours_repeated_entries_and_counted_sfen(self):
        hand = 'RR,R,RR,RH,rh,rh,r,r,RRH'
        out = self.position(self.fen(hand))
        self.assertEqual(Counter(re.search(r'\[(.*?)\]', self.field(out, 'Fen'))[1].split(',')),
                         Counter(hand.split(',')))
        self.assertIn('2RR', self.field(out, 'Sfen'))
        self.assertIn('2rh', self.field(out, 'Sfen'))
        self.roundtrip(out)
        black = self.position(self.fen(hand, 'b'))
        self.assertEqual({m.split('@')[0] for m in self.moves(black) if '@' in m}, {'R', 'RH'})
        self.roundtrip(black)

    def test_unknown_entries_are_not_split_into_known_prefixes(self):
        for hand in ('RRR', 'RRP', 'RHXYZ', 'RRHXYZ'):
            with self.subTest(hand=hand):
                out = self.position(self.fen(hand))
                self.assertIn('[]', self.field(out, 'Fen'))
                self.assertFalse(any('@' in m for m in self.moves(out)))
        out = self.position(self.fen('RRR,R'))
        self.assertEqual(re.search(r'\[(.*?)\]', self.field(out, 'Fen'))[1], 'R')

    def test_empty_hands_and_bounded_invalid_sfen_counts(self):
        for hand in ('', '-'):
            out = self.position(self.fen(hand))
            self.assertIn('[]', self.field(out, 'Fen'))
            self.roundtrip(out)
        base = self.position(self.fen())
        sfen = self.field(base, 'Sfen').split()
        for count in ('0', '999999999999999999999999999999999'):
            sfen[2] = count + 'RR,R'
            out = self.position(' '.join(sfen), sfen=True)
            self.assertEqual(re.search(r'\[(.*?)\]', self.field(out, 'Fen'))[1], 'R')

    def test_real_capture_root_clone_and_drop(self):
        pieces = {'a1':'K', 'h8':'k', 'b2':'R', 'b4':'rh'}
        out = self.position(self.fen(pieces=pieces), moves='b2b4 h8g8')
        self.assertIn('[RH]', self.field(out, 'Fen'))
        self.assertIn('RH@c3', self.moves(out))
        self.assertNotIn('R@c3', self.moves(out))
        self.roundtrip(out)
        again = self.position(self.fen(pieces=pieces), moves='b2b4 h8g8 RH@c3')
        self.assertIn('RH', self.field(again, 'Fen').split('[')[0])
        self.assertIn('[]', self.field(again, 'Fen'))
        self.roundtrip(again)

    def test_promoted_capture_demotes_to_original_symbol(self):
        pieces = {'a1':'K', 'h8':'k', 'b2':'R', 'b4':'+rr'}
        out = self.position(self.fen(pieces=pieces), moves='b2b4 h8g8')
        self.assertIn('[RR]', self.field(out, 'Fen'))
        self.assertIn('RR@c3', self.moves(out))
        self.roundtrip(out)
        loop = self.position(self.fen(pieces=pieces), 'hand-loop', moves='b2b4 h8g8')
        self.assertIn('[QQ]', self.field(loop, 'Fen'))
        self.assertIn('QQ@c3', self.moves(loop))
        self.roundtrip(loop, 'hand-loop')

    def test_drop_promoted_and_high_slot_symbols(self):
        out = self.position(self.fen('RR,HZ'), 'promoted-drops')
        self.assertTrue({'RR@c3', '+RR@c3', 'HZ@c3'} <= self.moves(out))
        self.roundtrip(out, 'promoted-drops')
        black = self.position(self.fen('hz', 'b'))
        self.assertIn('HZ@c3', self.moves(black))
        self.roundtrip(black)

    def test_search_can_use_multi_character_hand_after_reload(self):
        pieces = {'a1':'K', 'h8':'k', 'b2':'R', 'b4':'rh'}
        out = self.position(self.fen(pieces=pieces), moves='b2b4 h8g8')
        before = self.field(out, 'Fen'), self.field(out, 'Key')
        result = self.search('go depth 2 searchmoves RH@c3')
        self.assertIn('info depth 2 ', result)
        self.assertIn('bestmove RH@c3', result)
        after = self.command('d\nisready\n')
        self.assertEqual(before, (self.field(after, 'Fen'), self.field(after, 'Key')))

    def test_existing_single_character_fen_sfen_and_seirawan(self):
        out = self.position(self.fen('RRpp'), 'crazyhouse')
        self.assertIn('[RRpp]', self.field(out, 'Fen'))
        self.assertIn(' 2R2p ', self.field(out, 'Sfen'))
        self.roundtrip(out, 'crazyhouse')
        # Explicit separators also work without any multi-character types.
        explicit = self.position(self.fen('R,R,p,p'), 'crazyhouse')
        self.assertEqual(self.field(out, 'Fen'), self.field(explicit, 'Fen'))
        self.assertEqual(self.field(out, 'Key'), self.field(explicit, 'Key'))
        for variant in ('shogi', 'seirawan'):
            if variant == 'shogi' and int(os.environ.get('BOARD_SIZE', '8')) < 9:
                continue
            if variant == 'seirawan' and os.environ.get('GATING', 'yes') == 'no':
                continue
            answer = self.command(f'setoption name UCI_Variant value {variant}\nposition startpos\nd\nisready\n')
            hand = re.search(r'\[(.*?)\]', self.field(answer, 'Fen'))[1]
            self.assertNotIn(',', hand)
            again = self.position(self.field(answer, 'Fen'), variant)
            self.assertEqual(self.field(answer, 'Fen'), self.field(again, 'Fen'))

    def test_dai_seireigi_real_capture_and_search(self):
        if int(os.environ.get('BOARD_SIZE', '8')) < 16 or self.slots < 128:
            self.skipTest('requires 16x16 and 128 slots')
        pieces = {'a1':'K', 'o2':'k', 'b8':'R', 'b10':'rh'}
        out = self.position(self.fen(pieces=pieces, size=15), 'dai-seireigi-drops', moves='b8b10 o2o3')
        self.assertIn('[RH]', self.field(out, 'Fen'))
        self.assertIn('RH@h1', self.moves(out))
        self.assertNotIn('R@h1', self.moves(out))
        self.roundtrip(out, 'dai-seireigi-drops')
        result = self.search('go depth 2 searchmoves RH@h1')
        self.assertIn('bestmove RH@h1', result)


if __name__ == '__main__':
    unittest.main()
