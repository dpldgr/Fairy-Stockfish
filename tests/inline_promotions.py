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
promotionRegionMandatoryWhite<shogiPawn> = *8
promotionRegionMandatoryBlack<shogiPawn> = *1
promotionRegionMandatoryWhite<customPiece1> = *8
promotionRegionMandatoryBlack<customPiece1> = *1
promotionPolicy = optional:{{oi,iic,ioc}} mandatory:{{oi}}
extinctionValue = loss
extinctionPieceTypes = k
startFen = 7,k/8/8/8/8/8/8/7,K w - - 0 1
'''


RULES = ''.join((
    variant('inline-alias', """piece = sp:<shogiPawn> +sp:<gold>
piece = sw:WrlR +sw:<rook>
piece = vw:WfF +vw:<commoner>"""),
    variant('inline-raw', """piece = sp:fW +sp:<gold>
piece = sw:WrlR +sw:<rook>"""),
    variant('inline-existing', """gold = gg
piece = sp:<shogiPawn> +sp:<gold>"""),
    variant('inline-late', """piece = sp:<shogiPawn> +sp:<gold>
piece = gg:<gold>"""),
    variant('inline-shared', """piece = sp:<shogiPawn> +sp:<gold>
piece = si:<silver> +si:<gold>"""),
    variant('inline-slots', '\n'.join(
        ['piece = aa:fW +aa:WfF']
        + [f'customPiece{i} = d{chr(ord("a") + i - 1)}:K' for i in range(1, 24)]
        + ['piece = sp:<shogiPawn> +sp:<gold>'])),
    variant('inline-symbol', """piece = ln:KNAD
piece = kn:FD +kn:<ln>"""),
    variant('inline-symbol-forward', """piece = kn:FD +kn:<LN>
piece = ln:KNAD"""),
    variant('inline-symbol-reordered', """piece = kn:FD +kn:<ln>
piece = ln:KNAD"""),
    variant('inline-slot-forward', """piece = kn:FD +kn:<customPiece15>
customPiece15 = ln:KNAD"""),
    variant('inline-symbol-legacy', """customPiece14 = ln:KNAD
customPiece15 = kn:FD
promotedPieceType = kn:ln"""),
    """[inline-symbol-inherited:inline-symbol-legacy]
piece = kn:FD +kn:<ln>
[inline-symbol-lion:inline-symbol-forward]
lionMovePieces = ln:FFFFFFFFFFFFFFFF
tradingRule = ln:[dist!,{ln}] ln:[dist2c!,{ln},{kn}]
[inline-legacy-lion:inline-symbol-legacy]
lionMovePieces = ln:FFFFFFFFFFFFFFFF
tradingRule = ln:[dist!,{ln}] ln:[dist2c!,{ln},{kn}]
""",
    variant('inline-symbol-native', """piece = sp:<shogiPawn> +sp:<gg>
piece = gg:<gold>"""),
    variant('inline-name-precedence', """piece = sp:<shogiPawn> +sp:<gold>
piece = gold:KNAD"""),
    variant('inline-symbol-full', '\n'.join(
        [f'customPiece{i} = d{chr(ord("a") + i - 1)}:K' for i in range(1, 24)]
        + ['piece = ln:KNAD', 'piece = kn:FD +kn:<ln>'])),
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

    def checked_config(self, rules, diagnostic=None):
        config = Path(self.temp.name) / 'declarations.ini'
        config.write_text(rules)
        result = subprocess.run([self.engine, 'check', str(config)],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        if diagnostic:
            self.assertIn(diagnostic, result.stderr)
        else:
            self.assertFalse(any(line and not line.startswith('Parsing variant:')
                                 for line in result.stderr.splitlines()), result.stderr)
        return config

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

    def test_explicit_slots_are_reserved_before_automatic_allocation(self):
        # Explicit slots 1-23 are reserved even though the new declaration
        # appears first. Its raw base and promoted form fill slots 24 and 25.
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

    def test_unknown_and_ambiguous_reference_diagnostics(self):
        for target, definitions, diagnostic in (
            ('missing', '', 'Unknown'),
            ('ln', 'customPiece14 = ln:KNAD\ncustomPiece16 = ln:K', 'Ambiguous'),
        ):
            with self.subTest(target=target):
                config = Path(self.temp.name) / 'invalid.ini'
                config.write_text(variant('inline-invalid', definitions
                                  + f'\npiece = kn:FD +kn:<{target}>'))
                result = subprocess.run([self.engine, 'check', str(config)],
                                        text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f'piece - {diagnostic} piece reference: <{target}>', result.stderr)
                self.assertNotIn('No free custom piece slot', result.stderr)
                initial = self.moves('inline-invalid', fen({'c5': 'KN'}), config=config)
                self.assertNotIn('c5d6+', initial)

    def test_bracketed_regions_and_policies_resolve_symbols_and_slots(self):
        for base, references in (('fW', ('sp', 'customPiece2')),
                                 ('<shogiPawn>', ('sp', 'shogiPawn'))):
            for reference in references:
                with self.subTest(base=base, reference=reference):
                    rules = variant('brackets', f'''piece = sp:{base} +sp:<gold>
customPiece1 = aa:K''')
                    rules = rules.replace('promotionRegionMandatoryWhite<shogiPawn> = *8\n', '')
                    rules = rules.replace('promotionRegionMandatoryBlack<shogiPawn> = *1\n', '')
                    rules += f'''
promotionRegionOptionalWhite = -
promotionRegionOptionalBlack = -
promotionPolicy = optional:{{}} mandatory:{{}}
promotionRegionOptionalWhite<{reference}> = *6
promotionRegionOptionalBlack<{reference}> = *3
promotionRegionMandatoryWhite<{reference}> = *8
promotionRegionMandatoryBlack<{reference}> = *1
promotionPolicyWhite<{reference}> = optional:{{oi}} mandatory:{{oi}}
promotionPolicyBlack<{reference}> = optional:{{oi}} mandatory:{{oi}}
'''
                    config = self.checked_config(rules)
                    for side in ('w', 'b'):
                        self.check_pawn('brackets', side, config=config)
                        self.check_pawn('brackets', side, last=True, config=config)

    def test_child_keeps_allocated_base_and_promoted_slots(self):
        rules = variant('allocated-parent', 'piece = sp:fW +sp:WfF') + '''
[allocated-child:allocated-parent]
piece = zz:K
piece = sp:fW +sp:Q
promotionPolicy = optional:{} mandatory:{}
promotionPolicyWhite<customPiece1> = optional:{oi}
'''
        config = self.checked_config(rules)
        position = fen({'c5': 'SP'})
        self.assertIn('c5c6+', self.moves('allocated-child', position, config=config))
        moves = self.moves('allocated-child', position, 'c5c6+ h8g8', config)
        self.assertIn('c6g6', moves)
        self.assertIn('c6e8', moves)

    def test_identical_betza_bases_remain_independent(self):
        rules = variant('independent', '''piece = aa:WfF +aa:<rook>
piece = bb:WfF +bb:<bishop>
promotionPolicyWhite<aa> = optional:{} mandatory:{}''')
        config = self.checked_config(rules)
        self.assertNotIn('c5c6+', self.moves('independent', fen({'c5': 'AA'}), config=config))
        self.assertIn('c5c6+', self.moves('independent', fen({'c5': 'BB'}), config=config))

    def test_shogi_sources_share_gold_without_custom_slots(self):
        definitions = '\n'.join(f'customPiece{i} = d{chr(ord("a") + i - 1)}:K'
                                for i in range(1, 26)) + '''
piece = p:<shogiPawn> +p:<g>
piece = l:<lance> +l:<g>
piece = n:<shogiKnight> +n:<g>
piece = s:<silver> +s:<g>
piece = g:<gold>
'''
        config = self.checked_config(variant('shared-gold', definitions))
        for piece, source, target in (('P', 'c5', 'c6'), ('L', 'c5', 'c6'),
                                      ('N', 'c4', 'd6'), ('S', 'c5', 'd6')):
            with self.subTest(piece=piece):
                position = fen({source: piece})
                promotion = source + target + '+'
                self.assertIn(promotion, self.moves('shared-gold', position, config=config))
                moves = self.moves('shared-gold', position, promotion + ' h8g8', config)
                self.assertEqual({m for m in moves if m.startswith(target)},
                                 self.gold_moves(target, 'w'))

    def test_tenjiku_declaration_chain_and_inline_comments(self):
        definitions = '''piece = gg:QcppQ              # Great General
piece = rg:RcppR +rg:<gg>     # Rook General
piece = se:RbBfFfA +se:<rg>   # Soaring Eagle
piece = dk:<bers> +dk:<se>    # Dragon King
piece = r:<rook> +r:<dk>      # Rook
piece = g:<gold> +g:<r>       # Gold General
piece = p:<shogiPawn> +p:<g>  # Pawn
'''
        config = self.checked_config(variant('tenjiku-chain', definitions))
        for piece in ('P', 'G', 'R', 'DK', 'SE', 'RG'):
            with self.subTest(piece=piece):
                position = fen({'c5': piece})
                self.assertIn('c5c6+', self.moves('tenjiku-chain', position, config=config))
        self.assertIn('c6c1', self.moves('tenjiku-chain', fen({'c5': 'G'}),
                                       'c5c6+ h8g8', config))

    def test_invalid_declarations_and_duplicate_bases(self):
        for definitions, diagnostic in (
            ('customPiece1 = aa:K +aa:Q', 'Single-slot definition required'),
            ('customPiece1 = aa:<gold>', 'Single-slot definition required'),
            ('piece = aa:K +bb:Q', 'Invalid definition'),
            ('piece = aa:K +aa:Q +aa:R', 'Invalid definition'),
            ('piece = aa:<missing>', 'Unknown piece reference'),
            ('piece = aa:<bers>\npiece = bb:<bers>', 'Duplicate base slot'),
            ('piece = aa:K\npiece = aa:Q', 'Duplicate or ambiguous base symbol'),
        ):
            with self.subTest(definitions=definitions):
                self.checked_config(variant('invalid-declaration', definitions), diagnostic)
        full = '\n'.join(f'customPiece{i} = d{chr(ord("a") + i - 1)}:K'
                         for i in range(1, 26))
        self.checked_config(variant('exhausted-base', full + '\npiece = aa:K'),
                            'No free custom piece slot for base')
        almost_full = '\n'.join(full.splitlines()[:-1])
        self.checked_config(variant('exhausted-promotion', almost_full + '\npiece = aa:K +aa:Q'),
                            'No free custom piece slot for promoted piece')

    def test_legacy_single_slots_accept_inline_comments(self):
        config = self.checked_config(variant('legacy-comments', '''customPiece1 = aa:K # King movement
customPiece2 = bb:Q # Queen movement'''))
        moves = self.moves('legacy-comments', fen({'c5': 'AA'}), config=config)
        self.assertEqual(len({m for m in moves if m.startswith('c5')}), 8)
        self.assertIn('c5c1', self.moves('legacy-comments', fen({'c5': 'BB'}), config=config))

    def test_old_promotion_suffixes_and_bad_references_are_reported(self):
        for option, diagnostic in (
            ('promotionPolicyWhiteShogiPawn', 'Invalid option'),
            ('promotionRegionOptionalWhiteShogiPawn', 'Invalid option'),
            ('promotionRegionMandatoryWhiteShogiPawn', 'Invalid option'),
            ('promotionPolicyWhite<missing>', 'Unknown piece reference'),
            ('promotionRegionOptionalWhite<missing>', 'Unknown piece reference'),
        ):
            with self.subTest(option=option):
                value = 'optional:{oi}' if option.startswith('promotionPolicy') else '*6'
                self.checked_config(variant('invalid-option', 'piece = sp:<shogiPawn> +sp:<gold>')
                                    + f'\n{option} = {value}\n', diagnostic)

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
