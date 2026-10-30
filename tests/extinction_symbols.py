#!/usr/bin/env python3
"""Check symbol parsing through actual extinction outcomes, including legacy sets."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def fen(missing=None, side='w', only_kings=False):
    pieces = {'h1': 'K', 'h8': 'k'}
    if not only_kings:
        pieces.update({'a1': 'CK', 'b2': 'AD', 'c3': 'DH', 'd2': 'DR',
                       'a8': 'ck', 'b7': 'ad', 'c6': 'dh', 'd7': 'dr',
                       'e2': 'EM', 'e7': 'em',
                       'f2': 'P', 'f7': 'p', 'g2': 'Q', 'g7': 'q',
                       'd4': 'C', 'd5': 'c'})
    missing = [] if missing is None else ([missing] if isinstance(missing, str) else missing)
    # C is defined only by the ambiguity fixture; omit it otherwise.
    if not any(item.startswith('ambiguous:') for item in missing):
        pieces.pop('d4', None)
        pieces.pop('d5', None)
    for item in missing:
        pieces.pop(item.split(':')[-1], None)
    rows = []
    for rank in range(8, 0, -1):
        cells, empty = [], 0
        for file in 'abcdefgh':
            piece = pieces.get(f'{file}{rank}')
            if piece:
                if empty:
                    cells.append(str(empty))
                    empty = 0
                cells.append(piece)
            else:
                empty += 1
        if empty:
            cells.append(str(empty))
        rows.append(','.join(cells))
    return '/'.join(rows) + f' {side} - - 0 1'


RULES = f'''
[symbol-extinction:chess]
customPiece1 = ck:K
customPiece2 = ad:K
customPiece3 = dh:K
customPiece4 = dr:K
customPiece5 = em:K
extinctionValue = loss
extinctionPieceTypes = ck,ad,dh
castling = false
startFen = {fen()}
[symbol-single:symbol-extinction]
extinctionPieceTypes = ck
[symbol-mixed:symbol-extinction]
extinctionPieceTypes = q,ck
[symbol-any:symbol-extinction]
extinctionPieceTypes = any:{{ck,ad,dh}}
[symbol-all-condition:symbol-extinction]
extinctionPieceTypes = all:{{ck,em}}
[symbol-all-count:symbol-all-condition]
extinctionPieceCount = 1
[symbol-all-opponent-count:symbol-all-condition]
extinctionOpponentPieceCount = 2
[symbol-compact:symbol-extinction]
extinctionPieceTypes = pq
[symbol-compact-spaced:symbol-extinction]
extinctionPieceTypes = p q
[symbol-ambiguous:symbol-extinction]
customPiece6 = c:K
extinctionPieceTypes = ck
startFen = {fen('ambiguous:')}
[symbol-explicit:symbol-ambiguous]
extinctionPieceTypes = {{ck}}
[symbol-all:symbol-extinction]
extinctionPieceTypes = *
[symbol-clear:symbol-extinction]
extinctionPieceTypes = -
[symbol-empty:symbol-extinction]
extinctionPieceTypes = {{}}
[symbol-all-empty:symbol-extinction]
extinctionPieceTypes = all:{{}}
[group-promotion]
maxFile = 8
maxRank = 8
piece = em:K
piece = ck:K +ck:<em>
castling = false
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{{iiq}} mandatory:{{}}
extinctionValue = loss
extinctionPieceTypes = all:{{ck,em}}
startFen = 7,ck/8/8/8/8/8/8/CK,7 w - - 0 1
[group-promotion-legacy:group-promotion]
extinctionPieceTypes = ck
[group-promotion-pseudo:group-promotion]
extinctionPseudoRoyal = true
'''


class ExtinctionSymbols(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'extinction.ini'
        cls.config.write_text(RULES)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def nodes(self, variant, position, config=None, moves=''):
        result = subprocess.run([self.engine, 'load', str(config or self.config)],
            input=f'setoption name UCI_Variant value {variant}\nposition fen {position}'
                  f'{" moves " + moves if moves else ""}\n'
                  'go perft 1\nquit\n', text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        match = re.search(r'Nodes searched:\s*(\d+)', result.stdout)
        self.assertIsNotNone(match, result.stdout)
        return int(match.group(1))

    def test_comma_separated_symbols_trigger_each_extinction(self):
        self.assertGreater(self.nodes('symbol-extinction', fen()), 0)
        for side in ('w', 'b'):
            for missing in ('a1', 'b2', 'c3', 'a8', 'b7', 'c6'):
                with self.subTest(side=side, missing=missing):
                    self.assertEqual(self.nodes('symbol-extinction', fen(missing, side)), 0)
        # Losing an unlisted type does not cause extinction.
        self.assertGreater(self.nodes('symbol-extinction', fen('d2')), 0)
        self.assertGreater(self.nodes('symbol-extinction', fen('g2')), 0)

    def test_case_whitespace_and_duplicate_symbols(self):
        config = Path(self.temp.name) / 'spaced.ini'
        config.write_text(RULES + '\n[spaced:symbol-extinction]\n'
                          'extinctionPieceTypes = CK, ad , dH,CK\n')
        for missing in (None, 'a1', 'b2', 'c3', 'd2'):
            with self.subTest(missing=missing):
                self.assertEqual(self.nodes('spaced', fen(missing), config),
                                 self.nodes('symbol-extinction', fen(missing)))

    def test_single_unambiguous_symbol(self):
        self.assertEqual(self.nodes('symbol-single', fen('a1')), 0)
        self.assertGreater(self.nodes('symbol-single', fen('b2')), 0)

    def test_mixed_single_and_multi_character_symbols(self):
        for missing in ('a1', 'a8', 'g2', 'g7'):
            with self.subTest(missing=missing):
                self.assertEqual(self.nodes('symbol-mixed', fen(missing)), 0)
        self.assertGreater(self.nodes('symbol-mixed', fen('b2')), 0)

    def test_explicit_any_preserves_legacy_per_type_condition(self):
        for missing in (None, 'a1', 'b2', 'c3', 'd2'):
            with self.subTest(missing=missing):
                self.assertEqual(self.nodes('symbol-any', fen(missing)),
                                 self.nodes('symbol-extinction', fen(missing)))

    def test_all_uses_combined_piece_count(self):
        self.assertGreater(self.nodes('symbol-all-condition', fen()), 0)
        for side, first, second in (('w', 'a1', 'e2'), ('b', 'a8', 'e7')):
            with self.subTest(side=side, remaining='em'):
                self.assertGreater(self.nodes('symbol-all-condition', fen(first, side)), 0)
            with self.subTest(side=side, remaining='ck'):
                self.assertGreater(self.nodes('symbol-all-condition', fen(second, side)), 0)
            with self.subTest(side=side, remaining='none'):
                self.assertEqual(self.nodes('symbol-all-condition', fen((first, second), side)), 0)

    def test_all_applies_extinction_count_to_combined_group(self):
        self.assertGreater(self.nodes('symbol-all-count', fen()), 0)
        for side, missing in (('w', 'a1'), ('w', 'e2'), ('b', 'a8'), ('b', 'e7')):
            with self.subTest(side=side, missing=missing):
                self.assertEqual(self.nodes('symbol-all-count', fen(missing, side)), 0)

    def test_all_applies_opponent_count_to_combined_group(self):
        white_extinct = ('a1', 'e2')
        self.assertEqual(self.nodes('symbol-all-opponent-count', fen(white_extinct)), 0)
        self.assertGreater(self.nodes('symbol-all-opponent-count',
                                      fen(white_extinct + ('e7',))), 0)

    def test_promotion_between_group_types_preserves_the_group(self):
        position = '7,ck/8/8/8/8/8/8/CK,7 w - - 0 1'
        self.assertGreater(self.nodes('group-promotion', position, moves='a1b1+'), 0)
        self.assertGreater(self.nodes('group-promotion-pseudo', position, moves='a1b1+'), 0)
        self.assertEqual(self.nodes('group-promotion-legacy', position, moves='a1b1+'), 0)

    def test_legacy_compact_and_spaced_sets(self):
        for variant in ('symbol-compact', 'symbol-compact-spaced'):
            for missing in ('f2', 'f7', 'g2', 'g7'):
                with self.subTest(variant=variant, missing=missing):
                    self.assertEqual(self.nodes(variant, fen(missing)), 0)
            self.assertGreater(self.nodes(variant, fen('a1')), 0)

    def test_braces_disambiguate_single_symbol(self):
        self.assertGreater(self.nodes('symbol-ambiguous', fen('ambiguous:a1')), 0)
        self.assertEqual(self.nodes('symbol-ambiguous', fen('ambiguous:d4')), 0)
        self.assertEqual(self.nodes('symbol-explicit', fen('ambiguous:a1')), 0)
        self.assertGreater(self.nodes('symbol-explicit', fen('ambiguous:d4')), 0)

    def test_all_and_clearing_inherited_sets(self):
        for variant in ('symbol-all', 'symbol-clear', 'symbol-empty', 'symbol-all-empty'):
            with self.subTest(variant=variant):
                self.assertGreater(self.nodes(variant, fen(only_kings=True)), 0)

    def test_invalid_lists_are_diagnosed_and_do_not_partially_replace_parent(self):
        for value in ('ck,unknown', ',ck', 'ck,', 'ck,,ad', '{ck,}', '{ck', 'ck,*',
                      'any:ck,ad', 'all:ck,ad', 'any:{ck,}', 'all:{ck,unknown}',
                      'some:{ck,ad}'):
            with self.subTest(value=value):
                config = Path(self.temp.name) / 'invalid.ini'
                config.write_text(RULES + '\n[invalid:symbol-extinction]\n'
                                  f'extinctionPieceTypes = {value}\n')
                result = subprocess.run([self.engine, 'check', str(config)],
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('extinctionPieceTypes - Invalid piece set:', result.stderr)
                self.assertNotIn('Invalid option: extinctionPieceTypes', result.stderr)
                self.assertEqual(self.nodes('invalid', fen('b2'), config), 0)


if __name__ == '__main__':
    unittest.main()
