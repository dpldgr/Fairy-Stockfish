#!/usr/bin/env python3
"""Independent ray oracle and engine integration for arbitrary range jumpers."""
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import threading
import unittest

DIRECTIONS = ((0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1))
ORDINARY = {'gg': range(8), 'vg': (1, 3, 5, 7), 'rg': (0, 2, 4, 6), 'bg': (1, 3, 5, 7)}
BLOCKERS = {'gg': {'k', 'gg'}, 'vg': {'k', 'gg', 'vg'},
            'rg': {'k', 'gg', 'vg', 'rg', 'bg'}, 'bg': {'k', 'gg', 'vg', 'rg', 'bg'}}
SPECS = 'gg:cQ:{k,gg} vg:cB:{k,gg,vg} rg:cR:{k,gg,vg,rg,bg} bg:cB:{k,gg,vg,rg,bg}'


def fen(board, side='w', size=8):
    rows = []
    for r in range(size, 0, -1):
        row, empty = [], 0
        for f in range(size):
            p = board.get(chr(97 + f) + str(r))
            if p:
                if empty:
                    row.append(str(empty))
                    empty = 0
                row.append(p)
            else:
                empty += 1
        if empty:
            row.append(str(empty))
        rows.append(','.join(row))
    return '/'.join(rows) + f' {side} - - 0 1'


def oracle(board, mover, side, blockers, jumping=None, prohibited=()):
    """Walk individual squares, independently of the engine's bitboard method."""
    result = set()
    origin = 'd4'
    ordinary = ORDINARY[mover]
    jumping = ordinary if jumping is None else jumping
    for d, (df, dr) in enumerate(DIRECTIONS):
        if side == 'b':
            df, dr = -df, -dr
        ordinary_open = True
        f, r = 3 + df, 4 + dr
        while 0 <= f < 8 and 1 <= r <= 8:
            to = chr(97 + f) + str(r)
            piece = board.get(to)
            if piece == '*':
                break
            if piece:
                enemy = piece.isupper() != (side == 'w')
                if enemy and piece.lower() not in prohibited and ((d in ordinary and ordinary_open) or (d in jumping and not ordinary_open)):
                    result.add(origin + to)
                ordinary_open = False
                if piece.lower() in blockers and d in jumping:
                    # This ends the jumping ray; ordinary movement was blocked too.
                    break
                if d not in jumping:
                    break
            elif ordinary_open and d in ordinary:
                result.add(origin + to)
            f, r = f + df, r + dr
    return result


class RangeJumps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'range.ini'
        cls.config.write_text(f'''[generals]
commoner = k
piece = gg:Q
piece = rg:R +rg:<gg>
piece = vg:B
piece = bg:B +bg:<vg>
piece = lo:W
piece = sh:<immobile>
castling = false
doubleStep = false
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
promotionRegionOptionalWhite = -
promotionRegionOptionalBlack = -
promotionRegionMandatoryWhite = -
promotionRegionMandatoryBlack = -
promotionPolicy = optional:{{}} mandatory:{{}}
rangeJumpPieces = {SPECS}
startFen = 7,k/8/8/8/3,RG,4/8/8/7,K w - - 0 1
[clear:generals]
rangeJumpPieces = -
[arbitrary:generals]
rangeJumpPieces = rg:cR:{{sh}} bg:cB:{{lo}}
[shield:generals]
rangeJumpPieces = rg:cR:{{sh}}
prohibitedCaptures = rg:sh
[transparent-shield:shield]
rangeJumpPieces = rg:cR:{{}}
[forward:generals]
rangeJumpPieces = rg:cfR:{{k,gg}}
[hybrid:generals]
rangeJumpPieces = rg:cB:{{sh}}
[capture-only:generals]
piece = rg:cR
rangeJumpPieces = rg:cR:{{sh}}
[promote:generals]
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{{}} mandatory:{{iic}}
[royal:generals]
commoner = -
king = k
extinctionValue = none
rangeJumpPieces = {SPECS}
[royal-shield:royal]
rangeJumpPieces = rg:cR:{{k,sh,gg}} gg:cQ:{{k,gg}}
[royal-promote:royal]
promotedPieceType = lo:gg
promotionRegionMandatoryWhite = *
promotionPolicy = optional:{{}} mandatory:{{iiq}}
[burn-royal:royal]
piece = fd:K
burnActivePieceTypes = {{fd}}
prohibitedCaptures = fd:k
mobilityRegionWhiteCustomPiece6 = d4 d5
[castle:chess]
rangeJumpPieces = r:cR:{{k,r}}
[trading:generals]
rangeJumpPieces = rg:cR:{{k,sh,gg,vg,rg,bg}}
tradingRule = lo:[any!,{{sh}}]
[no-trade:generals]
tradingRule = lo:[any,{{sh}}]
[pawn-source:generals]
pawn = p
queen = q
promotionPawnTypes = p
promotionPieceTypes = q
promotionRegionMandatoryWhite = *8
promotionPolicy = optional:{{}} mandatory:{{oi}}
rangeJumpPieces = p:cR:{{sh}}
[pseudo:generals]
extinctionPseudoRoyal = true
[pseudo-expression:pseudo]
extinctionCondition = k=0
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, variant='generals', board=None, side='w', moves='', depth=1, commands=None, config=None):
        position = board if isinstance(board, str) else fen({'h1': 'K', 'h8': 'k', **(board or {'d4': 'RG'})}, side)
        result = subprocess.run([self.engine, 'load', str(config or self.config)],
                                input=f'setoption name UCI_Variant value {variant}\nposition fen {position} moves {moves}\n'
                                      + (commands or f'd\ngo perft {depth}\n') + 'quit\n',
                                text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def moves(self, *args, **kwargs):
        out = self.output(*args, **kwargs)
        self.assertIn('Nodes searched:', out)
        return re.findall(r'^(\S+): \d+$', out, re.M)

    def final(self, variant, board, move, config=None):
        out = self.output(variant, board, moves=move, depth=2, config=config)
        position = re.search(r'^Fen: (.+)', out, re.M).group(1)
        key = re.search(r'^Key: (\S+)', out, re.M).group(1)
        fresh = self.output(variant, position, config=config)
        self.assertEqual(key, re.search(r'^Key: (\S+)', fresh, re.M).group(1))
        return position

    def test_valid_parser_and_whitespace(self):
        path = Path(self.temp.name) / 'spaces.ini'
        path.write_text(self.config.read_text() + '\n[spaces:generals]\nrangeJumpPieces = rg : R : { k, sh, gg }   bg:cB:{}\n')
        out = subprocess.run([self.engine, 'check', str(path)], input='quit\n', text=True, capture_output=True, timeout=120)
        self.assertEqual(out.returncode, 0)
        self.assertNotIn(' - ', out.stderr)

    def test_all_generals_against_independent_random_oracle(self):
        rng = random.Random(240173)
        squares = [chr(97 + f) + str(r) for f in range(8) for r in range(1, 9) if (f, r) not in ((3, 4), (7, 1), (7, 8))]
        for side in ('w', 'b'):
            for mover in ORDINARY:
                for case in range(6):
                    board = {'h1': 'K', 'h8': 'k', 'd4': mover.upper() if side == 'w' else mover}
                    for square in rng.sample(squares, 13):
                        piece = rng.choice(('lo', 'gg', 'vg', 'rg', 'bg', 'sh', '*'))
                        board[square] = piece.upper() if rng.randrange(2) else piece
                    actual = [m for m in self.moves(board=board, side=side) if m.startswith('d4')]
                    with self.subTest(side=side, mover=mover, case=case):
                        self.assertEqual(len(actual), len(set(actual)))
                        self.assertEqual(set(actual), oracle(board, mover, side, BLOCKERS[mover]))

    def test_capture_blocker_but_not_beyond_for_both_colours(self):
        for low in ('lo', 'LO'):
            for high in ('gg', 'GG'):
                moves = self.moves(board={'d4': 'RG', 'd5': low, 'd6': high, 'd7': 'lo'})
                self.assertEqual('d4d6' in moves, high.islower())
                self.assertNotIn('d4d7', moves)
                self.assertNotIn('d4d5d6', moves)

    def test_zero_hurdles_and_ordinary_capture_deduplication(self):
        moves = self.moves(board={'d4': 'RG', 'd7': 'lo'})
        self.assertEqual(moves.count('d4d7'), 1)
        self.assertIn('d4d6', moves)
        moves = self.moves(board={'d4': 'RG', 'd5': 'LO', 'd7': 'lo'})
        self.assertIn('d4d7', moves)
        self.assertNotIn('d4d6', moves)  # Jumping grants no quiet destinations.

    def test_passage_over_king_when_not_in_configured_set(self):
        moves = self.moves('arbitrary', {'d4': 'RG', 'd5': 'k', 'd7': 'lo'})
        self.assertIn('d4d7', moves)
        self.assertNotIn('d4d7', self.moves('generals', {'d4': 'RG', 'd5': 'k', 'd7': 'lo'}))

    def test_shield_blocks_without_being_capturable(self):
        moves = self.moves('shield', {'d4': 'RG', 'd5': 'lo', 'd6': 'sh', 'd7': 'lo'})
        self.assertNotIn('d4d6', moves)
        self.assertNotIn('d4d7', moves)
        moves = self.moves('transparent-shield', {'d4': 'RG', 'd5': 'sh', 'd7': 'lo'})
        self.assertNotIn('d4d5', moves)
        self.assertIn('d4d7', moves)  # Capture prohibition alone does not block passage.

    def test_independent_sets_and_inheritance_clear(self):
        board = {'d4': 'RG', 'd5': 'gg', 'd7': 'lo'}
        self.assertIn('d4d7', self.moves('arbitrary', board))
        self.assertNotIn('d4d7', self.moves('generals', board))
        self.assertNotIn('d4d7', self.moves('clear', board))
        # Only RG's inherited row changes; GG's own blocker set is preserved.
        self.assertNotIn('d4d7', self.moves('arbitrary', {'d4': 'GG', 'd5': 'gg', 'd7': 'lo'}))

    def test_directional_rays_for_both_colours(self):
        for side in ('w', 'b'):
            piece = 'RG' if side == 'w' else 'rg'
            soft = 'lo' if side == 'w' else 'LO'
            board = {'h1': 'K', 'h8': 'k', 'd4': piece, 'd5': soft, 'd7': soft, 'd3': soft, 'd1': soft}
            actual = {m for m in self.moves('forward', board, side=side) if m.startswith('d4')}
            self.assertEqual(actual, oracle(board, 'rg', side, {'k', 'gg'}, jumping=(0,)))

    def test_jump_geometry_is_independent_of_base_movement(self):
        self.assertNotIn('d4e5', self.moves('hybrid', {'d4': 'RG'}))
        self.assertNotIn('d4e5', self.moves('hybrid', {'d4': 'RG', 'e5': 'lo'})) # No screen for the added diagonal jump.
        self.assertIn('d4f6', self.moves('hybrid', {'d4': 'RG', 'e5': 'LO', 'f6': 'lo'}))
        self.assertNotIn('d4f4', self.moves('capture-only', {'d4': 'RG'}))
        self.assertIn('d4f4', self.moves('capture-only', {'d4': 'RG', 'e4': 'lo', 'f4': 'lo'}))

    def test_walls_always_block_and_mobility_limits_destinations(self):
        self.assertNotIn('d4d7', self.moves(board={'d4': 'RG', 'd5': '*', 'd7': 'lo'}))
        path = Path(self.temp.name) / 'mobility.ini'
        path.write_text(self.config.read_text() + '\n[limited:generals]\nmobilityRegionWhiteCustomPiece2 = d4 d5 d6\n')
        self.assertNotIn('d4d7', self.moves('limited', {'d4': 'RG', 'd5': 'lo', 'd7': 'lo'}, config=path))

    def test_capture_only_removes_destination_and_preserves_hash(self):
        final = self.final('generals', {'d4': 'RG', 'd5': 'lo', 'd6': 'LO', 'd7': 'lo'}, 'd4d7')
        self.assertEqual(final.split()[0].count('lo'), 1)
        self.assertIn('LO', final)
        self.assertIn('RG', final)

    def test_capture_promotion_and_undo(self):
        board = {'d4': 'RG', 'd5': 'LO', 'd7': 'lo'}
        moves = self.moves('promote', board)
        self.assertIn('d4d7+', moves)
        self.assertNotIn('d4d7', moves)
        self.assertIn('+RG', self.final('promote', board, 'd4d7+'))
        out = self.output('promote', board, commands='d\ngo perft 3\nd\n')
        self.assertEqual(*re.findall(r'^Key: (\S+)', out, re.M))
        self.assertEqual(*re.findall(r'^Fen: (.+)', out, re.M))

    def test_native_pawn_can_gain_rays_and_promote(self):
        board = {'d6': 'P', 'd7': 'LO', 'd8': 'lo'}
        moves = self.moves('pawn-source', board)
        self.assertIn('d6d8q', moves)
        self.assertNotIn('d6d8', moves)
        self.final('pawn-source', board, 'd6d8q')

    def test_same_ray_double_check_can_be_blocked_by_nonking(self):
        board = {'a1': 'K', 'h1': None, 'h8': None, 'h7': 'k', 'b2': 'GG', 'c1': 'rg', 'e1': 'gg'}
        moves = self.moves('royal', board)
        self.assertIn('b2b1', moves)
        self.assertNotIn('b2c2', moves)
        self.final('royal', board, 'b2b1')

    def test_capturing_a_blocker_with_soft_piece_exposes_king(self):
        board = {'a1': 'K', 'h1': None, 'd2': 'LO', 'd1': 'sh', 'e1': 'rg'}
        self.assertNotIn('d2d1', self.moves('royal-shield', board))

    def test_capturing_a_soft_piece_with_blocker_evades_check(self):
        board = {'a1': 'K', 'h1': None, 'd2': 'GG', 'd1': 'lo', 'e1': 'rg'}
        self.assertIn('d2d1', self.moves('royal', board))
        self.final('royal', board, 'd2d1')

    def test_promotion_changes_blocker_status_during_legality(self):
        board = {'a1': 'K', 'h1': None, 'd2': 'LO', 'e1': 'rg'}
        moves = self.moves('royal-promote', board)
        self.assertIn('d2d1+', moves)
        self.assertNotIn('d2d1', moves)
        self.final('royal-promote', board, 'd2d1+')

    def test_trading_recapture_looks_through_soft_pieces(self):
        board = {'d4': 'LO', 'd5': 'sh', 'd6': 'lo', 'd8': 'rg'}
        self.assertNotIn('d4d5', self.moves('trading', board))
        self.assertIn('d4d5', self.moves('generals', board))
        board['d6'] = 'sh'
        self.assertIn('d4d5', self.moves('trading', board))
        self.assertNotIn('d4d5', self.moves('no-trade', board))

    def test_pseudo_royals_use_range_attacks(self):
        board = {'d1': 'K', 'h1': None, 'd4': 'rg', 'd2': 'LO'}
        for variant in ('pseudo', 'pseudo-expression'):
            self.assertNotIn('d2d3', self.moves(variant, board))
            self.assertIn('d1c1', self.moves(variant, board))

    def test_burn_threats_remain_independent_of_direct_capture_restrictions(self):
        board = {'d4': 'FD', 'e6': 'k', 'h8': None}
        out = self.output('burn-royal', board, side='b')
        self.assertIn('Checkers: d4', out)
        self.assertNotIn('e6e5', self.moves('burn-royal', board, side='b'))
        self.assertIn('e6f7', self.moves('burn-royal', board, side='b'))

    def test_cannot_castle_out_of_range_jump_check(self):
        position = 'k7/8/8/8/8/8/8/r3K2R w K - 0 1'
        self.assertNotIn('e1g1', self.moves('castle', position))

    def test_range_jumps_coexist_with_area_routes(self):
        if int(os.environ.get('BOARD_SIZE', '8')) < 16:
            self.skipTest('64-bit move build only')
        path = Path(self.temp.name) / 'area.ini'
        path.write_text(self.config.read_text() +
                        '\n[area:generals]\ntenjikuTripleStepPieceTypes = {vg}\n')
        moves = self.moves('area', {'d4': 'VG', 'e5': 'LO', 'g7': 'lo', 'f7': 'lo'}, config=path)
        self.assertIn('d4g7', moves)
        self.assertIn('d4d5e6f7', moves)
        self.assertNotIn('d4f6', moves)
        self.assertEqual(len(moves), len(set(moves)))

    def test_high_slots_on_full_19x19_board(self):
        slots = int(os.environ.get('PIECE_SLOTS', '64'))
        if os.environ.get('BOARD_SIZE') != '19' or slots < 128:
            self.skipTest('19x19 build with a wide piece catalogue only')
        path = Path(self.temp.name) / 'high.ini'
        path.write_text(f'''[high]
maxFile = 19
maxRank = 19
commoner = k
customPiece1 = lo:W
customPiece{slots - 40} = sh:K
customPiece{slots - 39} = hx:R
castling = false
rangeJumpPieces = hx:cR:{{sh}}
prohibitedCaptures = hx:sh
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
''')
        board = {'a1': 'K', 'a19': 'k', 'j10': 'HX', 'j11': 'LO',
                 'j15': 'lo', 'j16': 'sh', 'j18': 'lo', 'r10': 'lo'}
        position = fen(board, size=19)
        moves = self.moves('high', position, config=path)
        self.assertIn('j10j15', moves)
        self.assertIn('j10r10', moves)
        self.assertNotIn('j10j16', moves)
        self.assertNotIn('j10j18', moves)
        self.assertNotIn('j10j12', moves)
        final = self.output('high', position, moves='j10j15', config=path)
        final_fen = re.search(r'^Fen: (.+)', final, re.M).group(1)
        fresh = self.output('high', final_fen, config=path)
        self.assertEqual(re.search(r'^Key: (\S+)', final, re.M).group(1),
                         re.search(r'^Key: (\S+)', fresh, re.M).group(1))
        board['j16'] = '*'
        self.assertNotIn('j10j18', self.moves('high', fen(board, size=19), config=path))
        # Full-width diagonal traverses all six bitboard words, with the
        # high-slot blocker added only in the second position.
        path.write_text(path.read_text() + '\n[diagonal:high]\nrangeJumpPieces = hx:cB:{sh}\n')
        board = {'s1': 'K', 's19': 'k', 'a1': 'HX', 'b2': 'LO', 'r18': 'lo'}
        self.assertIn('a1r18', self.moves('diagonal', fen(board, size=19), config=path))
        board['q17'] = 'sh'
        self.assertNotIn('a1r18', self.moves('diagonal', fen(board, size=19), config=path))

    def test_invalid_options_are_rejected(self):
        invalid = ('rg:N:{k}', 'rg:R:k', 'missing:R:{k}', 'rg:R:{missing}',
                   'rg:R:{k} rg:B:{sh}', 'rg:pR:{k}', 'rg:R3:{k}', 'rg:R:{k', 'rg::{}')
        path = Path(self.temp.name) / 'invalid.ini'
        for value in invalid:
            with self.subTest(value=value):
                path.write_text(self.config.read_text() + '\n[invalid:generals]\nrangeJumpPieces = ' + value + '\n')
                out = subprocess.run([self.engine, 'load', str(path)], input='uci\nquit\n', text=True, capture_output=True, timeout=120)
                self.assertEqual(out.returncode, 0)
                self.assertIn('rangeJumpPieces - ', out.stderr)
                self.assertNotIn(' var invalid', out.stdout)

    def test_search_can_select_a_jump_capture(self):
        board = fen({'h1': 'K', 'h8': 'k', 'd4': 'RG', 'd5': 'LO', 'd7': 'lo'})
        with subprocess.Popen([self.engine, 'load', str(self.config)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as engine:
            timer = threading.Timer(60, engine.kill)
            timer.start()
            try:
                engine.stdin.write(f'setoption name UCI_Variant value generals\nposition fen {board}\ngo depth 3 searchmoves d4d7\n')
                engine.stdin.flush()
                output = []
                for line in engine.stdout:
                    output.append(line)
                    if line.startswith('bestmove'):
                        break
                engine.stdin.write('quit\n'); engine.stdin.flush(); engine.wait(timeout=10)
                self.assertEqual(engine.returncode, 0, ''.join(output) + engine.stderr.read())
                self.assertIn('bestmove d4d7', ''.join(output))
            finally:
                timer.cancel()

    def test_search_keeps_quiet_general_extinction_threat(self):
        if (int(os.environ.get('BOARD_SIZE', '8')) < 16
                or int(os.environ.get('PIECE_SLOTS', '64')) < 128):
            self.skipTest('Tenjiku search fixture needs 16x16 and at least 128 slots')

        config = Path(__file__).with_name('fixtures') / 'tenjiku-range-search.ini'
        cases = (
            ('c3b2 l11l10', 'depth 4 searchmoves h4h14', -2, 'h4h14 i13h14'),
            ('c3b2 l11l10 h4h14', 'depth 3', 2, 'i13h14'),
        )
        for moves, go, mate, pv in cases:
            with self.subTest(moves=moves):
                with subprocess.Popen([self.engine, 'load', str(config)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as engine:
                    timer = threading.Timer(90, engine.kill)
                    timer.start()
                    try:
                        engine.stdin.write('setoption name Threads value 1\n'
                                           'setoption name Hash value 16\n'
                                           'setoption name Use NNUE value false\n'
                                           'setoption name UCI_Variant value tenjiku-search\n'
                                           f'position startpos moves {moves}\ngo {go}\n')
                        engine.stdin.flush()
                        output = []
                        for line in engine.stdout:
                            output.append(line)
                            if line.startswith('bestmove'):
                                break
                        if engine.poll() is None:
                            engine.stdin.write('quit\n')
                            engine.stdin.flush()
                        engine.wait(timeout=10)
                        text = ''.join(output)
                        self.assertEqual(engine.returncode, 0, text)
                        self.assertIn('bestmove ', text)
                        info = [line for line in output if line.startswith('info depth')][-1]
                        self.assertIn(f' score mate {mate} ', info)
                        self.assertIn(f' pv {pv} ', info)
                        self.assertIn('h14h1', info)
                    finally:
                        timer.cancel()


if __name__ == '__main__':
    unittest.main()
