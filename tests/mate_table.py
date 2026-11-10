#!/usr/bin/env python3
"""Exact K+X/K tables, independently checked against the CVP applet."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

from uci_verbosity import Engine


ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'fixtures/mate-table-reference.json').read_text())
REFERENCE = DATA['cases']
for case in REFERENCE.values():
    case['samples'] = [dict(zip(DATA['sample_fields'], row)) for row in case['samples']]
PREFIX = 'info string mate-table '


def fields(line):
    tokens = line.split()
    return {tokens[i]: int(tokens[i + 1]) for i in range(0, len(tokens), 2)}


def fen(sample, piece, color='white'):
    board = ['1'] * 64
    places = [sample['wk'], sample['x'], sample['bk']]
    if color == 'black':
        places = [63 - s for s in places]
    for square, symbol in zip(places, ['K', piece.upper(), 'k']):
        board[square] = symbol if color == 'white' else symbol.swapcase()
    rows = [','.join(board[start:start + 8]) for start in range(56, -1, -8)]
    stm = ('w' if color == 'white' else 'b') if sample['turn'] == 0 else ('b' if color == 'white' else 'w')
    return '/'.join(rows) + f' {stm} - - 0 1'


class MateTables(unittest.TestCase):
    binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'mate.ini'
        cls.config.write_text((ROOT / 'fixtures/metal-chess.ini').read_text() + '''
[metal-alias:metal-chess]
piece = gr:<r>
[mate-quiet:chess]
piece = x:mR
[mate-capture:chess]
piece = x:cR
[mate-extinction:metal-chess]
extinctionValue = loss
extinctionPieceTypes = k
[mate-burn:metal-chess]
burnActivePieceTypes = {r}
[mate-lion:metal-chess]
lionMovePieces = r(FFFFFFFFFFFFFFFF)
[mate-promotion:metal-chess]
piece = x:W +x:F
[mate-royal-promotion:chess]
promotedPieceType = k:q
[mate-stale-loss:chess]
stalemateValue = loss
[mate-stale-win:chess]
stalemateValue = win
''')
        if int(os.environ.get('BOARD_SIZE', '8')) >= 14:
            with cls.config.open('a') as config:
                config.write('''
[mate-large:chess]
maxFile = 14
maxRank = 14
piece = x:K
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def engine(self, variant):
        engine = Engine(self.binary, ('load', str(self.config)))
        engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value ' + variant)
        return engine

    def build(self, engine, piece, extra='', api=False):
        engine.send(('api ' if api else '') + f'mate-table build piece {piece} {extra}')
        lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'complete')
                                          or s.startswith(PREFIX + 'error'), timeout=120)]
        self.assertTrue(lines[-1].startswith(PREFIX + 'complete'), '\n'.join(lines))
        return lines

    def compare(self, lines, reference, color='white', signature=True):
        if signature:
            self.assertEqual(re.search(r' signature (\d+)', lines[-1])[1], reference['signature'])
        summaries = [s for s in lines if s.startswith(PREFIX + 'summary')]
        self.assertEqual(len(summaries), 2)
        for turn, line in enumerate(summaries):
            stm = color if turn == 0 else ('black' if color == 'white' else 'white')
            self.assertIn('stm ' + stm, line)
            self.assertEqual(fields('legal ' + line.split(' legal ', 1)[1]), reference['summary'][turn])
        histogram = {}
        for line in lines:
            if line.startswith(PREFIX + 'dtm '):
                row = fields(line[len(PREFIX + 'dtm '):])
                histogram[str(row['plies'])] = [row[k] for k in ('strong_wins', 'strong_losses', 'weak_wins', 'weak_losses')]
        self.assertEqual(histogram, reference['histogram'])

    def probe(self, engine, position, moves=''):
        engine.send(f'position fen {position}' + (' moves ' + moves if moves else '') + '\nmate-table probe')
        lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'probe') or s.startswith(PREFIX + 'error'))]
        self.assertTrue(lines[-1].startswith(PREFIX + 'probe'), '\n'.join(lines))
        return lines[-1]

    def test_metal_complete_tables_and_engine_legal_probes(self):
        with self.engine('metal-chess') as engine:
            for piece in ('r', 'b', 'n'):
                with self.subTest(piece=piece):
                    reference = REFERENCE[piece]
                    self.compare(self.build(engine, piece), reference)
                    for sample in reference['samples']:
                        position = fen(sample, piece)
                        line = self.probe(engine, position)
                        result = {2: 'draw', 3: 'win', 4: 'loss'}[sample['result']]
                        self.assertIn('result ' + result, line)
                        if result != 'draw':
                            self.assertIn('dtm_plies ' + str(sample['dtm']) + ' ', line)
                        best = line.rsplit(' bestmove ', 1)[1]
                        engine.send('go perft 1')
                        divided = [s for _, s in engine.until(lambda s: s.startswith('Nodes searched:'))]
                        legal = {s.split(':')[0] for s in divided if re.match(r'^\S+: 1$', s)}
                        if not legal:
                            self.assertEqual(best, '0000')
                            continue
                        self.assertIn(best, legal)
                        x = sample['x']
                        x_square = chr(97 + x % 8) + str(x // 8 + 1)
                        if sample['turn'] == 1 and best.endswith(x_square):
                            self.assertEqual(result, 'draw')  # Bare K/K drawing exit.
                            continue
                        child = self.probe(engine, position, best)
                        if result == 'draw':
                            self.assertIn('result draw ', child)
                        else:
                            self.assertIn('result ' + ('loss' if result == 'win' else 'win'), child)
                            self.assertIn('dtm_plies ' + str(sample['dtm'] - 1) + ' ', child)

    def test_orthodox_controls(self):
        with self.engine('chess') as engine:
            for piece, name in [('r', 'orthodoxR'), ('b', 'orthodoxB'), ('n', 'orthodoxN')]:
                with self.subTest(piece=piece):
                    self.compare(self.build(engine, piece, api=True), REFERENCE[name])

    def test_black_orientation_and_multichar_symbols(self):
        with self.engine('metal-chess') as engine:
            for piece in ('r', 'b', 'n'):
                self.compare(self.build(engine, piece, 'color black'), REFERENCE[piece], 'black', False)
                for sample in REFERENCE[piece]['samples'][::5]:
                    line = self.probe(engine, fen(sample, piece, 'black'))
                    self.assertIn('result ' + {2: 'draw', 3: 'win', 4: 'loss'}[sample['result']], line)
                    if sample['result'] != 2:
                        self.assertIn('dtm_plies ' + str(sample['dtm']) + ' ', line)
        with self.engine('metal-alias') as engine:
            self.compare(self.build(engine, 'gr'), REFERENCE['r'])

    def test_modality_and_stalemate(self):
        with self.engine('mate-quiet') as engine:
            lines = self.build(engine, 'x')
            for line in lines:
                if 'summary' in line:
                    self.assertIn(' wins 0 ', line)
                    self.assertIn(' losses 0 ', line)
        with self.engine('mate-capture') as engine:
            self.build(engine, 'x')
            self.assertIn('result loss dtm_plies 0 bestmove 0000',
                          self.probe(engine, 'k7/2K5/8/8/8/8/8/X7 b - - 0 1'))
        for variant, result in [('chess', 'draw'), ('mate-stale-loss', 'loss'), ('mate-stale-win', 'win')]:
            with self.engine(variant) as engine:
                self.build(engine, 'r')
                line = self.probe(engine, 'k7/1R6/2K5/8/8/8/8/8 b - - 0 1')
                self.assertIn('result ' + result, line)
                self.assertIn('bestmove 0000', line)

    def test_lifecycle_errors_and_search(self):
        with self.engine('metal-chess') as engine:
            for command in ('mate-table stats', 'mate-table probe', 'mate-table piece unknown',
                            'mate-table piece k', 'mate-table piece r memory 0',
                            'mate-table piece r memory nope', 'mate-table piece r color green',
                            'mate-table piece r memory 1'):
                engine.send(command)
                engine.until(lambda s: s.startswith(PREFIX + 'error'))
            self.build(engine, 'r')
            engine.send('mate-table probe')  # Full starting army is not KX/K.
            engine.until(lambda s: s.startswith(PREFIX + 'error'))
            engine.ready('setoption name UCI_Variant value chess')
            engine.send('mate-table stats')
            engine.until(lambda s: s.startswith(PREFIX + 'error'))
            engine.ready('setoption name UCI_Variant value metal-chess')
            started = time.monotonic()
            engine.send('mate-table piece b\nstop\nisready')
            stopped = [s for _, s in engine.until(lambda s: s == 'readyok')]
            self.assertTrue(any('cancelled' in s or s.startswith(PREFIX + 'complete') for s in stopped))
            self.assertLess(time.monotonic() - started, 10)
            engine.ready('mate-table clear')
            engine.send('mate-table status')
            engine.until(lambda s: s == PREFIX + 'status empty')
            engine.ready('setoption name UCI_Variant value chess\nposition startpos')
            for command in ('go infinite', 'go tds-minimax 6'):
                engine.send(command)
                output = self.build(engine, 'r')
                self.assertTrue(any(s.startswith('bestmove ') for s in output), output)
            lines = engine.search('go depth 4')
            self.assertTrue(any(s.startswith('bestmove ') for _, s in lines))
        for variant, piece in [('mate-extinction', 'r'), ('mate-burn', 'r'), ('mate-lion', 'r'),
                               ('mate-promotion', 'x'), ('mate-royal-promotion', 'r'), ('chess', 'p')]:
            with self.engine(variant) as engine:
                engine.send('mate-table piece ' + piece)
                engine.until(lambda s: s.startswith(PREFIX + 'error unsupported:'))

    def test_command_line_waits_for_completion(self):
        for prefix in ([], ['api']):
            result = subprocess.run([self.binary, *prefix, 'mate-table', 'piece', 'r'],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(PREFIX + 'complete ', result.stdout)
            self.assertIn('signature ' + REFERENCE['orthodoxR']['signature'], result.stdout)

    @unittest.skipUnless(int(os.environ.get('BOARD_SIZE', '8')) >= 14, 'requires a 14x14-capable build')
    def test_larger_board_and_long_distance(self):
        with self.engine('mate-large') as engine:
            start = time.monotonic()
            engine.send('mate-table piece x memory 256\nisready')
            first = [s for _, s in engine.until(lambda s: s == 'readyok')]
            self.assertLess(time.monotonic() - start, 5)
            rest = [] if any(s.startswith(PREFIX + 'complete') for s in first) else [
                s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'complete'), timeout=120)]
            lines = first + rest
            summaries = [fields('legal ' + s.split(' legal ', 1)[1]) for s in lines if ' summary ' in s]
            self.assertEqual(summaries[0]['wins'], summaries[0]['legal'])
            self.assertEqual([s['max_dtm_plies'] for s in summaries], [123, 124])
            self.assertIn('states 15059072 table_bytes 120472576', lines[-1])


if __name__ == '__main__':
    unittest.main()
