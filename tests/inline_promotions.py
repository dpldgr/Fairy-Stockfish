#!/usr/bin/env python3
"""Referenced promotion targets must remain playable after promotion and reload."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def variant(name, definitions):
    return f'''
[{name}]
commoner = k
{definitions}
castling = false
promotionRegionOptionalWhite = *6 *7 *8
promotionRegionOptionalBlack = *1 *2 *3
promotionRegionMandatoryWhiteShogiPawn = *8
promotionRegionMandatoryBlackShogiPawn = *1
promotionRegionMandatoryWhiteCustomPiece1 = *8
promotionRegionMandatoryBlackCustomPiece1 = *1
promotionPolicy = optional:{{oi,iic,ioc}} mandatory:{{oi}}
extinctionValue = loss
extinctionPieceTypes = k
startFen = 7,k/8/8/8/8/8/8/7,K w - - 0 1
'''


RULES = ''.join((
    variant('inline-alias', '''customPiece1 = sp:<shogiPawn> +sp:<gold>
customPiece2 = sw:WrlR +sw:<rook>
customPiece3 = vw:WfF +vw:<commoner>'''),
    variant('inline-raw', '''customPiece1 = sp:fW +sp:<gold>
customPiece2 = sw:WrlR +sw:<rook>'''),
    variant('inline-existing', '''gold = gg
customPiece1 = sp:<shogiPawn> +sp:<gold>'''),
    variant('inline-late', '''customPiece1 = sp:<shogiPawn> +sp:<gold>
customPiece2 = gg:<gold>'''),
    variant('inline-shared', '''customPiece1 = sp:<shogiPawn> +sp:<gold>
customPiece2 = si:<silver> +si:<gold>'''),
    variant('inline-slots', '\n'.join(
        ['customPiece1 = aa:fW +aa:WfF']
        + [f'customPiece{i} = d{chr(ord("a") + i - 2)}:K' for i in range(2, 25)]
        + ['customPiece25 = sp:<shogiPawn> +sp:<gold>'])),
    variant('inline-symbol', '''customPiece14 = ln:KNAD
customPiece15 = kn:FD +kn:<ln>'''),
    variant('inline-symbol-forward', '''customPiece15 = ln:KNAD
customPiece14 = kn:FD +kn:<LN>'''),
    variant('inline-symbol-reordered', '''customPiece15 = kn:FD +kn:<ln>
customPiece14 = ln:KNAD'''),
    variant('inline-slot-forward', '''customPiece14 = kn:FD +kn:<customPiece15>
customPiece15 = ln:KNAD'''),
    variant('inline-symbol-legacy', '''customPiece14 = ln:KNAD
customPiece15 = kn:FD
promotedPieceType = kn:ln'''),
    '''[inline-symbol-inherited:inline-symbol-legacy]
customPiece15 = kn:FD +kn:<ln>
[inline-symbol-lion:inline-symbol-forward]
lionMovePieces = ln:FFFFFFFFFFFFFFFF
tradingRule = ln:[dist!,{ln}] ln:[dist2c!,{ln},{kn}]
[inline-legacy-lion:inline-symbol-legacy]
lionMovePieces = ln:FFFFFFFFFFFFFFFF
tradingRule = ln:[dist!,{ln}] ln:[dist2c!,{ln},{kn}]
''',
    variant('inline-symbol-native', '''customPiece1 = sp:<shogiPawn> +sp:<gg>
customPiece2 = gg:<gold>'''),
    variant('inline-name-precedence', '''customPiece1 = sp:<shogiPawn> +sp:<gold>
customPiece2 = gold:KNAD'''),
    variant('inline-mapping-order', '''gold = gg
customPiece1 = sp:<shogiPawn> +sp:<gold>
customPiece2 = sp:<shogiPawn> +sp:KNAD'''),
    variant('inline-symbol-full', '\n'.join(
        [f'customPiece{i} = d{chr(ord("a") + i - 1)}:K' for i in range(1, 24)]
        + ['customPiece24 = ln:KNAD', 'customPiece25 = kn:FD +kn:<ln>'])),
))


def fen(pieces, side='w', size=8):
    edge = chr(ord('a') + size - 1)
    pieces = {f'{edge}1': 'K', f'{edge}{size}': 'k', **pieces}
    rows = []
    for rank in range(size, 0, -1):
        cells, empty = [], 0
        for file in range(size):
            piece = pieces.get(chr(ord('a') + file) + str(rank))
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


class InlinePromotions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'inline.ini'
        cls.config.write_text(RULES)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, name, position, moves='', config=None):
        result = subprocess.run([self.engine, 'load', str(config or self.config)],
            input=f'setoption name UCI_Variant value {name}\n'
                  f'position fen {position} moves {moves}\nd\ngo perft 1\nquit\n',
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('Nodes searched:', result.stdout)
        return result.stdout

    def moves(self, name, position, moves='', config=None):
        output = self.output(name, position, moves, config)
        return {m.group(1) for line in output.splitlines()
                if (m := re.fullmatch(r'(\S+): \d+', line))}

    def gold_moves(self, square, side, size=8):
        file, rank = ord(square[0]) - ord('a'), int(square[1:])
        direction = 1 if side == 'w' else -1
        return {square + chr(ord('a') + file + df) + str(rank + dr)
                for df, dr in ((0, direction), (0, -direction), (-1, 0),
                               (1, 0), (-1, direction), (1, direction))
                if 0 <= file + df < size and 1 <= rank + dr <= size}

    def check_pawn(self, name, side, last=False, size=8, config=None):
        source_rank = size - 1 if last else size - 3
        target_rank = source_rank + 1
        if side == 'b':
            source_rank, target_rank = size + 1 - source_rank, size + 1 - target_rank
        source, target = f'c{source_rank}', f'c{target_rank}'
        position = fen({source: 'SP' if side == 'w' else 'sp'}, side, size)
        initial = self.moves(name, position, config=config)
        self.assertIn(source + target + '+', initial)
        self.assertEqual(source + target in initial, not last)
        edge, next_file = chr(ord('a') + size - 1), chr(ord('a') + size - 2)
        reply_rank = size if side == 'w' else 1
        moves = source + target + f'+ {edge}{reply_rank}{next_file}{reply_rank}'
        after = self.moves(name, position, moves, config)
        self.assertEqual({m for m in after if m.startswith(target)},
                         self.gold_moves(target, side, size))

    def test_pawn_optional_entry_activates_gold(self):
        for name in ('inline-alias', 'inline-raw'):
            for side in ('w', 'b'):
                with self.subTest(name=name, side=side):
                    self.check_pawn(name, side)

    def test_mandatory_last_rank_gold_can_move_back(self):
        for name in ('inline-alias', 'inline-raw'):
            for side in ('w', 'b'):
                with self.subTest(name=name, side=side):
                    self.check_pawn(name, side, last=True)

    def test_referenced_rook_is_active(self):
        for name in ('inline-alias', 'inline-raw'):
            with self.subTest(name=name):
                moves = self.moves(name, fen({'c5': 'SW'}), 'c5c6+ h8g8')
                expected = {f'c6c{r}' for r in range(1, 9) if r != 6}
                expected |= {f'c6{f}6' for f in 'abdefgh'}
                self.assertEqual({m for m in moves if m.startswith('c6')}, expected)

    def test_existing_commoner_symbol_is_preserved(self):
        output = self.output('inline-alias', fen({'c5': 'VW'}), 'c5c6+ h8g8')
        board = next(line[5:].split()[0] for line in output.splitlines() if line.startswith('Fen: '))
        self.assertIn('K', re.findall(r'\+?[A-Za-z]+', board))
        self.assertIn('h1g1', self.moves('inline-alias', fen({'c5': 'VW'}), 'c5c6+ h8g8'))

    def test_existing_gold_definition_is_preserved(self):
        for name in ('inline-existing', 'inline-late'):
            with self.subTest(name=name):
                position = fen({'c5': 'SP', 'e3': 'GG'})
                output = self.output(name, position, 'c5c6+ h8g8')
                board = next(line[5:].split()[0] for line in output.splitlines() if line.startswith('Fen: '))
                self.assertIn('GG', re.findall(r'\+?[A-Za-z]+', board))
                moves = self.moves(name, position, 'c5c6+ h8g8')
                self.assertEqual({m for m in moves if m.startswith('c6')}, self.gold_moves('c6', 'w'))
                self.assertIn('e3e4', moves)

    def test_multiple_pieces_share_referenced_target(self):
        for piece in ('SP', 'SI'):
            with self.subTest(piece=piece):
                moves = self.moves('inline-shared', fen({'c5': piece}), 'c5c6+ h8g8')
                self.assertEqual({m for m in moves if m.startswith('c6')}, self.gold_moves('c6', 'w'))

    def test_promoted_fen_reload_keeps_gold_movement(self):
        output = self.output('inline-alias', fen({'c5': 'SP'}), 'c5c6+ h8g8')
        position = next(line[5:] for line in output.splitlines() if line.startswith('Fen: '))
        moves = self.moves('inline-alias', position)
        self.assertEqual({m for m in moves if m.startswith('c6')}, self.gold_moves('c6', 'w'))

    def test_unused_native_alias_slot_is_reused_only_when_needed(self):
        # All 25 custom keys are present, but the final key aliases a native
        # type. The first promotion can borrow that slot without being erased
        # when the alias is parsed later, and the alias still promotes to Gold.
        for piece in ('AA', 'SP'):
            with self.subTest(piece=piece):
                moves = self.moves('inline-slots', fen({'c5': piece}), 'c5c6+ h8g8')
                self.assertEqual({m for m in moves if m.startswith('c6')}, self.gold_moves('c6', 'w'))

    def test_symbol_and_slot_references_match_explicit_mapping(self):
        names = ('inline-symbol', 'inline-symbol-forward', 'inline-symbol-reordered',
                 'inline-slot-forward', 'inline-symbol-inherited', 'inline-symbol-full')
        for side in ('w', 'b'):
            source, target, reply = ('c5', 'd6', 'h8g8') if side == 'w' else ('c4', 'd3', 'h1g1')
            position = fen({source: 'KN' if side == 'w' else 'kn',
                            'a3' if side == 'w' else 'a6': 'LN' if side == 'w' else 'ln'}, side)
            promotion = source + target + '+'
            moves = promotion + ' ' + reply
            expected = self.moves('inline-symbol-legacy', position, moves)
            self.assertEqual(len({m for m in expected if m.startswith(target)}), 24)
            for name in names:
                with self.subTest(name=name, side=side):
                    self.assertIn(promotion, self.moves(name, position))
                    self.assertEqual(self.moves(name, position, moves), expected)
                    output = self.output(name, position, moves)
                    reloaded = next(line[5:] for line in output.splitlines() if line.startswith('Fen: '))
                    self.assertIn('+KN' if side == 'w' else '+kn', reloaded)
                    self.assertIn('LN' if side == 'w' else 'ln', reloaded)
                    self.assertEqual(self.moves(name, reloaded), expected)

    def test_symbol_reference_preserves_lion_rules(self):
        position = fen({'c5': 'KN', 'e6': 'ln', 'e7': 'kn'})
        moves = 'c5d6+ h8g8'
        expected = self.moves('inline-legacy-lion', position, moves)
        self.assertTrue(any(m.startswith('d6') and len(m) > 4 for m in expected))
        self.assertEqual(self.moves('inline-symbol-lion', position, moves), expected)

    def test_symbol_reference_to_native_alias(self):
        for side in ('w', 'b'):
            with self.subTest(side=side):
                self.check_pawn('inline-symbol-native', side)
                self.check_pawn('inline-symbol-native', side, last=True)

    def test_type_name_takes_precedence_over_symbol(self):
        self.check_pawn('inline-name-precedence', 'w')

    def test_later_raw_mapping_overrides_reference_for_same_base(self):
        moves = self.moves('inline-mapping-order', fen({'c5': 'SP'}), 'c5c6+ h8g8')
        self.assertIn('c6e7', moves)
        self.assertIn('c6a6', moves)

    def test_unknown_and_ambiguous_reference_diagnostics(self):
        for target, definitions, diagnostic in (
            ('missing', '', 'Unknown'),
            ('ln', 'customPiece14 = ln:KNAD\ncustomPiece16 = ln:K', 'Ambiguous'),
        ):
            with self.subTest(target=target):
                config = Path(self.temp.name) / 'invalid.ini'
                config.write_text(variant('inline-invalid', definitions
                                  + f'\ncustomPiece15 = kn:FD +kn:<{target}>'))
                result = subprocess.run([self.engine, 'check', str(config)],
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'customPiece15 - {diagnostic} promotion reference: <{target}>', result.stderr)
                self.assertNotIn('No free custom piece slot', result.stderr)
                initial = self.moves('inline-invalid', fen({'c5': 'KN'}), config=config)
                self.assertNotIn('c5d6+', initial)

    @unittest.skipUnless(os.environ.get('FSF_TEST_11X11') == '1',
                         'set FSF_TEST_11X11=1 with an 11x11-capable build')
    def test_reported_wa_shogi_configuration(self):
        config = Path(__file__).resolve().parent / 'fixtures' / 'wa-shogi.ini'
        check = subprocess.run([self.engine, 'check', str(config)], text=True,
                               capture_output=True, timeout=30)
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertFalse(any(line and not line.startswith('Parsing variant:')
                             for line in check.stderr.splitlines()), check.stderr)
        for side in ('w', 'b'):
            for last in (False, True):
                with self.subTest(side=side, last=last):
                    self.check_pawn('wa-shogi', side, last, size=11, config=config)
        moves = self.moves('wa-shogi', fen({'c8': 'SW'}, size=11), 'c8c9+ k11j11', config)
        self.assertIn('c9c1', moves)
        self.assertIn('c9k9', moves)
        moves = self.moves('wa-shogi', fen({'c8': 'LH'}, size=11), 'c8c9+ k11j11', config)
        self.assertEqual({m for m in moves if m.startswith('c9')},
                         {'c9b7', 'c9d7', 'c9b11', 'c9d11'})


if __name__ == '__main__':
    unittest.main()
