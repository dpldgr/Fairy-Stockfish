#!/usr/bin/env python3
"""Hook capture modes through the real parser, move generator and do/undo."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def fen(pieces, side='w'):
    board = {'h1': 'K', 'h8': 'k', **pieces}
    rows = []
    for rank in range(8, 0, -1):
        row, empty = [], 0
        for file in 'abcdefgh':
            piece = board.get(file + str(rank))
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


class HookMoves(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'hooks.ini'
        cls.config.write_text('''[hook-base]
commoner = k
customPiece1 = h:R
customPiece2 = l:WB
customPiece3 = v:W
castling = false
extinctionValue = loss
extinctionPieceTypes = k
startFen = 7k/8/8/8/3H4/8/8/7K w - - 0 1
''')
        with cls.config.open('a') as out:
            for mode, suffix in (('default', ''), ('one', ':1'), ('two', ':2'), ('stop', ':1!')):
                out.write(f'[hook-{mode}:hook-base]\nhookMovePieces = h:R-sR{suffix} l:B-sB{suffix}\n')
            out.write('[hook-inherited:hook-stop]\n')
            out.write('''[hook-named:hook-base]
piece = hm:<rook>
piece = lo:WB
hookMovePieces = hm:R-sR:1! lo:B-sB:1!
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, mode, position, commands='go perft 1\n'):
        result = subprocess.run([self.engine, 'load', str(self.config)],
                                input=f'setoption name UCI_Variant value hook-{mode}\n'
                                      f'position fen {position}\n' + commands + 'quit\n',
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Invalid piece/spec', result.stderr)
        return result.stdout

    def moves(self, mode, position):
        output = self.output(mode, position)
        self.assertIn('Nodes searched:', output)
        return set(re.findall(r'^(\S+): \d+$', output, re.M))

    def test_all_capture_combinations_for_both_pieces_and_colours(self):
        for piece, corner, final in (('H', 'd5', 'f5'), ('L', 'e5', 'g3')):
            for side in ('w', 'b'):
                mover, enemy = (piece, 'v') if side == 'w' else (piece.lower(), 'V')
                for first in (False, True):
                    for second in (False, True):
                        board = {'d4': mover}
                        if first:
                            board[corner] = enemy
                        if second:
                            board[final] = enemy
                        for mode in ('default', 'one', 'two', 'stop'):
                            with self.subTest(piece=piece, side=side, first=first, second=second, mode=mode):
                                moves = self.moves(mode, fen(board, side))
                                allowed = not first or (mode != 'stop' and (not second or mode == 'two'))
                                self.assertEqual('d4' + corner + final in moves, allowed)
                                # Voluntary first-leg stops and forced capture stops
                                # retain their ordinary move identity in every mode.
                                self.assertIn('d4' + corner, moves)

    def test_cannot_traverse_a_captured_turn_square(self):
        moves = self.moves('stop', fen({'d4': 'H', 'd5': 'v'}))
        self.assertIn('d4d5', moves)
        self.assertFalse(any(m.startswith('d4d5') and m != 'd4d5' for m in moves))
        self.assertNotIn('d4d6e6', moves)

    def test_second_leg_stops_at_capture_in_every_mode(self):
        for mode in ('default', 'one', 'two', 'stop'):
            with self.subTest(mode=mode):
                moves = self.moves(mode, fen({'d4': 'H', 'f5': 'v'}))
                self.assertIn('d4d5f5', moves)
                self.assertNotIn('d4d5g5', moves)

    def test_friendly_turn_square_blocks_all_modes(self):
        for mode in ('default', 'one', 'two', 'stop'):
            moves = self.moves(mode, fen({'d4': 'H', 'd5': 'V'}))
            self.assertNotIn('d4d5e5', moves)
            self.assertNotIn('d4d6e6', moves)

    def test_stop_mode_is_inherited(self):
        moves = self.moves('inherited', fen({'d4': 'H', 'd5': 'v'}))
        self.assertIn('d4d5', moves)
        self.assertNotIn('d4d5e5', moves)

    def test_named_piece_definitions_and_multiple_entries(self):
        for piece, corner, final in (('HM', 'd5', 'f5'), ('LO', 'e5', 'g3')):
            with self.subTest(piece=piece):
                moves = self.moves('named', fen({'d4': piece, corner: 'v'}))
                self.assertIn('d4' + corner, moves)
                self.assertNotIn('d4' + corner + final, moves)
                self.assertIn('d4' + corner + final,
                              self.moves('named', fen({'d4': piece, final: 'v'})))

    def test_perft_undo_restores_fen_and_key(self):
        output = self.output('stop', fen({'d4': 'H', 'f5': 'v', 'b6': 'l'}),
                             'd\ngo perft 3\nd\n')
        self.assertGreater(int(re.search(r'Nodes searched: (\d+)', output).group(1)), 0)
        for pattern in (r'^Fen: (.+)', r'^Key: (\S+)'):
            values = re.findall(pattern, output, re.M)
            self.assertEqual(len(values), 2)
            self.assertEqual(values[0], values[1])

    def test_parser_accepts_only_the_supported_modes(self):
        result = subprocess.run([self.engine, 'check', str(self.config)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Invalid piece/spec', result.stderr)
        for suffix in (':2!', ':1!!', ':0'):
            config = Path(self.temp.name) / 'invalid.ini'
            config.write_text(self.config.read_text() + '\n[invalid:hook-base]\nhookMovePieces = h:R-sR' + suffix + '\n')
            result = subprocess.run([self.engine, 'check', str(config)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('hookMovePieces - Invalid piece/spec', result.stderr)


if __name__ == '__main__':
    unittest.main()
