#!/usr/bin/env python3
"""Order-independent, color-sensitive mate-table material-list integration."""
import itertools
import os
from pathlib import Path
import tempfile
import unittest

from mate_table_four import build, native_checks
from uci_verbosity import Engine

PREFIX = 'info string mate-table '


class MaterialLists(unittest.TestCase):
    binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'material.ini'
        cls.config.write_text((Path(__file__).parent / 'fixtures/metal-chess.ini').read_text() + '''
[material-tiny:metal-chess]
maxFile = 3
maxRank = 3
[material-small:metal-chess]
maxFile = 4
maxRank = 4
[material-multi:material-tiny]
king = ck
piece = sb:<b>
piece = in:<n>
[material-promoted:chess]
maxFile = 3
maxRank = 3
piece = x:W +x:F
[material-ambiguous:chess]
customPiece1 = zz:W
customPiece2 = zz:F
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def engine(self, variant='material-tiny'):
        engine = Engine(self.binary, ('load', str(self.config)))
        engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value ' + variant)
        return engine

    def same_result(self, actual, expected):
        self.assertEqual(actual['summary'], expected['summary'])
        self.assertEqual(actual['signature'], expected['signature'])

    def test_all_five_piece_permutations_and_multiplicity(self):
        with self.engine() as engine:
            expected, _, _ = build(engine, 'mate-table piece b partner n partner n memory 512 format info')
            self.assertEqual(expected['signature'], 15909068724154616127)
            permutations = sorted(set(itertools.permutations(('K', 'B', 'N', 'N', 'k'))))
            self.assertEqual(len(permutations), 60)
            for i, material in enumerate(permutations):
                with self.subTest(material=material):
                    contents = ', '.join(material) + (',' if i % 2 else '')
                    actual, _, _ = build(engine, 'mate-table pieces { ' + contents + ' } memory 512 format info')
                    self.same_result(actual, expected)
                    self.assertEqual(actual['table_bytes'], expected['table_bytes'])
            four, _, _ = build(engine, 'mate-table pieces {K,B,N,k} format info')
            self.assertNotEqual(four['table_bytes'], expected['table_bytes'])
            self.assertNotEqual(four['summary'], expected['summary'])

    def test_four_piece_armies_and_order(self):
        with self.engine() as engine:
            cases = [('piece b opponent n', ('K', 'B', 'k', 'n')),
                     ('piece n opponent b', ('K', 'N', 'k', 'b')),
                     ('piece b partner n', ('K', 'B', 'N', 'k')),
                     ('piece b color black partner n', ('K', 'k', 'b', 'n'))]
            for legacy, pieces in cases:
                expected, _, _ = build(engine, 'mate-table ' + legacy + ' format info')
                for material in itertools.permutations(pieces):
                    with self.subTest(material=material):
                        actual, _, _ = build(engine, 'mate-table pieces {' + ','.join(material) + '} format info')
                        self.same_result(actual, expected)

    def test_three_piece_colors_and_aliases(self):
        with self.engine() as engine:
            for color, material in [('white', '{k,B,K}'), ('black', '{b,K,k,}')]:
                expected, _, _ = build(engine, 'mate-table piece b color ' + color + ' format info')
                actual, _, _ = build(engine, 'mate-table pieces ' + material + ' format info')
                self.same_result(actual, expected)
                actual, _, _ = build(engine, 'mate-table pieces ' + material)
                self.same_result(actual, expected)
        with self.engine('material-multi') as engine:
            expected, _, _ = build(engine, 'mate-table piece sb partner in partner in memory 512 format info')
            for material in ('{CK,SB,IN,IN,ck}', '{IN,ck,SB,CK,IN,}'):
                actual, _, _ = build(engine, 'mate-table pieces ' + material + ' memory 512 format info')
                self.same_result(actual, expected)
            expected, _, _ = build(engine, 'mate-table piece sb color black format info')
            actual, _, _ = build(engine, 'mate-table pieces {sb,CK,ck} format info')
            self.same_result(actual, expected)
        with self.engine('material-promoted') as engine:
            expected, _, _ = build(engine, 'mate-table piece +x format info')
            actual, _, _ = build(engine, 'mate-table pieces {+X,k,K} format info')
            self.same_result(actual, expected)

    def test_malformed_material_preserves_cached_result(self):
        invalid = ['pieces', 'pieces K,B,k', 'pieces {}', 'pieces { }',
                   'pieces {K,B,k', 'pieces {K,,B,k}', 'pieces {,K,B,k}',
                   'pieces {K,B,k,,}', 'pieces {K,B,k, ,}', 'pieces {K,k}',
                   'pieces {K,K,B,k}', 'pieces {K,B}', 'pieces {K,B,N}',
                   'pieces {K,B,N,N,N,k}', 'pieces {K,missing,k}',
                   'pieces {K,123,k}', 'pieces {K,B,k}format info',
                   'pieces {K,B,k} color white', 'pieces {K,B,k} partner n',
                   'pieces {K,B,k} opponent n', 'pieces {K,B,k}}',
                   'pieces {K,B,k} pieces {K,N,k}']
        with self.engine() as engine:
            expected, _, _ = build(engine, 'mate-table pieces {K,B,k} format info')
            for material in invalid:
                with self.subTest(material=material):
                    engine.send('mate-table ' + material)
                    lines = [s for _, s in engine.until(lambda s: s.startswith(PREFIX + 'error '))]
                    self.assertFalse(any('building ' in s for s in lines))
                    raw = [s for _, s in engine.ready('mate-table stats raw')]
                    self.assertIn('signature ' + str(expected['signature']), '\n'.join(raw))
        with self.engine('material-multi') as engine:
            engine.send('mate-table pieces {CK,Sb,ck}')
            engine.until(lambda s: s.startswith(PREFIX + 'error '))
        with self.engine('material-ambiguous') as engine:
            engine.send('mate-table pieces {K,ZZ,k}')
            engine.until(lambda s: s == PREFIX + 'error unknown or ambiguous piece symbol: ZZ')

    def test_build_api_and_format_table(self):
        with self.engine('material-small') as engine:
            expected, _, _ = build(engine, 'mate-table piece b partner n partner n memory 512 format info')
            for prefix in ('mate-table', 'mate-table build', 'api mate-table', 'api mate-table build'):
                with self.subTest(prefix=prefix):
                    actual, lines, _ = build(engine, prefix + ' pieces {N,k,B,K,N,} memory 512 format table')
                    self.same_result(actual, expected)
                    self.assertFalse(any(s.startswith(PREFIX) for s in lines))
            native_checks(engine, 100, 4, ('b', 'n', 'n'), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
