#!/usr/bin/env python3
"""Exercise configured drop destinations through move generation and protocols."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


RULES = '''
[drop-base:crazyhouse]
castling = false
[drop-regions:drop-base]
dropRegionWhite = *1 *2
dropRegionBlack = *7 *8
dropRegionWhiteKnight = a3 b3
dropRegionBlackKnight = g6 h6
[drop-child:drop-regions]
dropRegionWhite = *4
[drop-cleared:drop-child]
dropRegionWhiteKnight = -
[drop-replaced:drop-regions]
dropRegionWhiteKnight = c5
[drop-opt-in:drop-base]
dropRegionWhite = -
dropRegionBlack = -
dropRegionWhiteKnight = a3
[drop-custom:drop-base]
knight = -
customPiece1 = n:N
dropRegionWhiteCustomPiece1 = c4
dropRegionBlackCustomPiece1 = f5
[drop-mobility:drop-base]
dropRegionWhiteKnight = a2 b2 a3 b3
mobilityRegionWhiteKnight = b2 a3
[drop-placed:drop-base]
promotedPieceType = n:r
dropPromoted = true
dropRegionWhiteKnight = a2
dropRegionBlackKnight = h7
dropRegionWhiteRook = b4
dropRegionBlackRook = g5
mobilityRegionWhiteKnight = a2
mobilityRegionBlackKnight = h7
mobilityRegionWhiteRook = b4
mobilityRegionBlackRook = g5
[drop-promoted-only:drop-placed]
dropRegionWhiteKnight = -
dropRegionBlackKnight = -
[drop-promoted-disabled:drop-placed]
dropRegionWhiteRook = -
dropRegionBlackRook = -
[drop-alias]
king = k
customPiece2 = p:<shogiPawn> +p:<gold>
pieceDrops = true
castling = false
dropRegionWhiteShogiPawn = a4
dropRegionWhiteCustomPiece2 = b4
[drop-gating:seirawan]
dropRegionWhiteArchbishop = g1
dropRegionWhiteChancellor = -
[drop-anyside:cfour-anyside]
dropRegionWhite = *1
dropRegionWhiteImmobile = -
[drop-xboard:drop-base]
dropRegionWhiteKnight = *1 *2
dropRegionBlackKnight = *7 *8
[drop-xboard-equivalent:drop-base]
mobilityRegionWhiteKnight = *1 *2
mobilityRegionBlackKnight = *7 *8
dropRegionWhiteKnight = *1 *2 *3
dropRegionBlackKnight = *7 *8
[drop-xboard-placed:drop-base]
promotedPieceType = n:r
dropPromoted = true
dropRegionWhiteKnight = *1 *2
dropRegionBlackKnight = *7 *8
dropRegionWhiteRook = *1 *2 *3
dropRegionBlackRook = *6 *7 *8
[drop-xboard-asymmetric:drop-base]
dropRegionWhiteKnight = *1 *2
dropRegionBlackKnight = *6 *7 *8
[drop-legacy:drop-base]
whiteDropRegion = *2
blackDropRegion = *7
[drop-pawn:drop-base]
dropRegionWhitePawn = *1 *7 *8
dropRegionBlackPawn = *1 *2 *8
[drop-pawn-unrestricted:drop-pawn]
firstRankPawnDrops = true
promotionZonePawnDrops = true
[drop-shogi:minishogi]
dropRegionWhiteShogiPawn = a4 a5 b4 b5
dropRegionWhiteShogiKnight = a4 b4 a5 b5
shogiKnight = n
[drop-sittuyin:sittuyin]
dropRegionWhiteRook = *1 *2
'''


def fen(pieces=None, pocket='N', side='w', size=8):
    pieces = {'h1': 'K', 'h8': 'k', **(pieces or {})}
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
    return '/'.join(rows) + f'[{pocket}] {side} - - 0 1'


class DropRegions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'drops.ini'
        # Load the actual insertion-game definitions without pulling in
        # unrelated variants that exceed an 8x8 executable's board capacity.
        examples = Path('variants.ini').read_text()
        insertion_rules = ''.join(re.search(r'(?ms)^\[' + re.escape(name)
                                            + r'\]\n.*?(?=^\[|\Z)', examples).group(0)
                                  for name in ('cfour', 'cfour-anyside:cfour'))
        cls.config.write_text(insertion_rules + RULES)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_engine(self, commands, config=None):
        result = subprocess.run([self.engine, 'load', str(config or self.config)],
                                input=commands + '\nquit\n', text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return result.stdout

    def moves(self, variant, position, depth=1, config=None):
        output = self.run_engine(f'setoption name UCI_Variant value {variant}\n'
                                 f'position fen {position}\ngo perft {depth}', config)
        self.assertIn('Nodes searched:', output)
        return {m.group(1) for line in output.splitlines()
                if (m := re.fullmatch(r'(\S+): \d+', line))}

    def destinations(self, variant, position, symbol='N'):
        return {move.split('@')[1] for move in self.moves(variant, position)
                if move.startswith(symbol + '@')}

    def test_colours_and_piece_overrides(self):
        for side, pocket, expected in [('w', 'NR', {'a3', 'b3'}),
                                       ('b', 'nr', {'g6', 'h6'})]:
            with self.subTest(side=side):
                moves = self.moves('drop-regions', fen(pocket=pocket, side=side))
                self.assertEqual({m[2:] for m in moves if m.startswith('N@')}, expected)
                self.assertIn('R@a1' if side == 'w' else 'R@a8', moves)
                self.assertNotIn('R@a4', moves)

    def test_inheritance_replacement_and_empty_override(self):
        self.assertEqual(self.destinations('drop-child', fen()), {'a3', 'b3'})
        self.assertEqual(self.destinations('drop-replaced', fen()), {'c5'})
        self.assertEqual(self.destinations('drop-cleared', fen()), set())
        self.assertEqual(self.destinations('drop-child', fen(pocket='R'), 'R'),
                         {f'{f}4' for f in 'abcdefgh'})
        self.assertEqual(self.destinations('drop-child', fen(pocket='n', side='b')),
                         {'g6', 'h6'})

    def test_line_order_independence(self):
        config = Path(self.temp.name) / 'reordered.ini'
        config.write_text('[ordered:crazyhouse]\ndropRegionWhiteKnight = a3\n'
                          'dropRegionWhite = *2\n')
        moves = self.moves('ordered', fen(), config=config)
        self.assertEqual({m for m in moves if m.startswith('N@')}, {'N@a3'})

    def test_default_global_and_disabled_global_regions(self):
        expected = {f'{f}{r}' for f in 'abcdefgh' for r in range(1, 9)} - {'h1', 'h8'}
        self.assertEqual(self.destinations('drop-base', fen()), expected)
        moves = self.moves('drop-opt-in', fen(pocket='NR'))
        self.assertEqual({m for m in moves if '@' in m}, {'N@a3'})
        self.assertEqual(self.destinations('drop-opt-in', fen(pocket='n', side='b')), set())

    def test_real_custom_piece_has_independent_regions(self):
        self.assertEqual(self.destinations('drop-custom', fen()), {'c4'})
        self.assertEqual(self.destinations('drop-custom', fen(pocket='n', side='b')), {'f5'})

    def test_board_mobility_walls_and_occupancy(self):
        self.assertEqual(self.destinations('drop-mobility', fen()), {'b2', 'a3'})
        self.assertEqual(self.destinations('drop-mobility', fen({'a3': '*'})), {'b2'})
        self.assertEqual(self.destinations('drop-mobility', fen({'b2': 'P'})), {'a3'})
        self.assertEqual(self.destinations('drop-mobility', fen({'b2': 'p'})), {'a3'})

    def test_promoted_form_uses_its_own_region_and_mobility(self):
        for side, pocket, normal, promoted in [('w', 'N', 'a2', 'b4'),
                                                ('b', 'n', 'h7', 'g5')]:
            with self.subTest(side=side):
                moves = self.moves('drop-placed', fen(pocket=pocket, side=side), depth=2)
                self.assertEqual({m for m in moves if '@' in m},
                                 {'N@' + normal, '+N@' + promoted})
                moves = self.moves('drop-promoted-only', fen(pocket=pocket, side=side))
                self.assertEqual({m for m in moves if '@' in m}, {'+N@' + promoted})
                moves = self.moves('drop-promoted-disabled', fen(pocket=pocket, side=side))
                self.assertEqual({m for m in moves if '@' in m}, {'N@' + normal})

    def test_piece_reference_uses_original_type(self):
        self.assertEqual(self.destinations('drop-alias', fen(pocket='P'), 'P'), {'a4'})

    def test_legacy_region_aliases(self):
        self.assertEqual(self.destinations('drop-legacy', fen()),
                         {f'{f}2' for f in 'abcdefgh'})
        self.assertEqual(self.destinations('drop-legacy', fen(pocket='n', side='b')),
                         {f'{f}7' for f in 'abcdefgh'})

    def test_pawn_restrictions_still_apply(self):
        self.assertEqual(self.destinations('drop-pawn', fen(pocket='P'), 'P'),
                         {f'{f}7' for f in 'abcdefgh'})
        self.assertEqual(self.destinations('drop-pawn', fen(pocket='p', side='b'), 'P'),
                         {f'{f}2' for f in 'abcdefgh'})
        self.assertIn('P@a1', self.moves('drop-pawn-unrestricted', fen(pocket='P')))
        self.assertIn('P@a8', self.moves('drop-pawn-unrestricted', fen(pocket='P')))

    def test_shogi_dead_and_doubled_drops(self):
        position = '4k/5/P4/5/4K[PN] w - - 0 1'
        moves = self.moves('drop-shogi', position)
        self.assertEqual({m for m in moves if m.startswith('P@')}, {'P@b4'})
        self.assertFalse(any(m.startswith('N@') for m in moves))

    def test_sittuyin_rook_restriction(self):
        moves = self.moves('drop-sittuyin', fen(pocket='R'))
        self.assertEqual({m[2:] for m in moves if m.startswith('R@')},
                         {f'{f}1' for f in 'abcdefg'})

    def test_gating_uses_the_piece_region(self):
        position = '4k3/8/8/8/8/8/8/4K1N1[HE] w G - 0 1'
        moves = self.moves('drop-gating', position)
        self.assertIn('g1f3h', moves)
        self.assertNotIn('g1f3e', moves)

    def test_anyside_behaviour_is_unchanged(self):
        position = '7/7/7/7/7/7/7[PPpp] w - - 0 1'
        expected = {f'P@{f}{r}' for f in 'abcdefg' for r in range(1, 8)
                    if f in 'ag' or r in (1, 7)}
        for variant in ('cfour-anyside', 'drop-anyside'):
            with self.subTest(variant=variant):
                self.assertEqual(self.moves(variant, position), expected)

    def test_xboard_filters_resolved_regions_and_rejects_selection(self):
        output = self.run_engine('xboard\nprotover 2\nvariant drop-regions\nping 1')
        advertised = re.search(r'variants="([^"]+)"', output).group(1).split(',')
        for variant in ('drop-base', 'drop-xboard', 'drop-xboard-equivalent',
                        'drop-xboard-placed', 'cfour-anyside', 'drop-anyside'):
            self.assertIn(variant, advertised)
        for variant in ('drop-regions', 'drop-cleared', 'drop-xboard-asymmetric', 'drop-gating'):
            self.assertNotIn(variant, advertised)
        self.assertIn('Error (unsupported variant): drop-regions', output)
        self.assertIn('pong 1', output)
        uci = self.run_engine('uci')
        self.assertIn(' var drop-regions ', uci.replace('\n', ' ') + ' ')

    def test_xboard_per_type_rank_descriptions(self):
        output = self.run_engine('xboard\nprotover 2\nvariant drop-xboard')
        self.assertRegex(output, r'piece N& [^\n]*@2\n')
        output = self.run_engine('xboard\nprotover 2\nvariant drop-xboard-placed')
        self.assertRegex(output, r'piece N& [^\n]*@2\n')
        self.assertRegex(output, r'piece \+N& [^\n]*@3\n')


if __name__ == '__main__':
    unittest.main()
