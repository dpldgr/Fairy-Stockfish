#!/usr/bin/env python3
"""Classical Emperor evaluation, narrow/wide score boundaries and search."""
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import unittest


def fen(board, size, side='w'):
    rows = []
    for rank in range(size - 1, -1, -1):
        row, empty = [], 0
        for file in range(size):
            pc = board.get((file, rank))
            if pc:
                if empty:
                    row.append(str(empty))
                    empty = 0
                row.append(pc)
            else:
                empty += 1
        if empty:
            row.append(str(empty))
        rows.append(','.join(row))
    return '/'.join(rows) + f' {side} - - 0 1'


class EmperorEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.size = int(os.environ.get('BOARD_SIZE', '8'))
        n = cls.size
        cls.temp = tempfile.TemporaryDirectory()
        path = Path(cls.temp.name) / 'emperors.ini'
        path.write_text(f'''[emperor-evaluation]
maxFile = {n}
maxRank = {n}
piece = k:<commoner>
piece = em:U
piece = mc:mU
piece = cc:cU
piece = x:<immobile>
castling = false
doubleStep = false
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionCondition = and(k=0,em=0)
nMoveRule = 0
[emperor-trading:emperor-evaluation]
tradingRule = em:[any!,{{k,em}}]
''')
        cls.engine = subprocess.Popen([os.environ['STOCKFISH'], 'load', str(path)],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True)
        cls.lines = queue.Queue()
        def reader():
            try:
                for line in cls.engine.stdout:
                    cls.lines.put(line)
            finally:
                cls.lines.put(None)
        cls.reader = threading.Thread(target=reader, daemon=True)
        cls.reader.start()
        out = cls.command('setoption name UCI_Variant value emperor-evaluation\n'
                          'setoption name Use NNUE value false\nisready\n')
        assert not re.search(r' - (?:Invalid|Expected|No free)', out), out

    @classmethod
    def command(cls, text, marker='readyok'):
        cls.engine.stdin.write(text)
        cls.engine.stdin.flush()
        lines = []
        while True:
            line = cls.lines.get(timeout=120)
            if line is None:
                raise AssertionError('Engine exited:\n' + ''.join(lines))
            lines.append(line)
            if line.startswith(marker):
                return ''.join(lines)

    @classmethod
    def tearDownClass(cls):
        if cls.engine.poll() is None:
            cls.engine.stdin.write('quit\n')
            cls.engine.stdin.flush()
            cls.engine.wait(timeout=30)
        cls.engine.stdin.close()
        cls.engine.stdout.close()
        cls.reader.join(timeout=5)
        cls.temp.cleanup()

    def royals(self):
        n = self.size
        return {(0, 0): 'K', (n - 1, n - 1): 'k'}

    def evaluate(self, board, side='w'):
        out = self.command('position fen ' + fen(board, self.size, side) + '\neval\nisready\n')
        self.assertRegex(out, r'Final evaluation\s+[+-]?\d')
        self.assertNotRegex(out, r'(?i)\b(?:nan|inf)\b|Assertion|runtime error:')
        return out

    def mobility(self, board):
        # Coordinate oracle for the quiet/capture destinations included by the
        # mobility term. Occupied friendly squares count as defended squares.
        totals = [[0, 0], [0, 0]]
        n = self.size
        for (file, rank), pc in board.items():
            if pc == '*':
                continue
            side = 0 if pc.isupper() else 1
            kind = pc.lower()
            destinations = 0
            for r in range(n):
                for f in range(n):
                    if (f, r) == (file, rank) or board.get((f, r)) == '*':
                        continue
                    occupied = (f, r) in board
                    if kind == 'k':
                        available = max(abs(f - file), abs(r - rank)) == 1
                    else:
                        available = kind == 'em' or (kind == 'mc' and not occupied) or (kind == 'cc' and occupied)
                    destinations += available
            # Integer division truncates towards zero for the negative corner
            # case of an immobile or capture-only piece with no destinations.
            for phase, weight in enumerate((150, 200)):
                totals[side][phase] += math.trunc(weight * (destinations - 2) / (8 + destinations))
        return [v / 208 for row in totals for v in row]

    def assert_mobility(self, board):
        out = self.evaluate(board)
        line = re.search(r'^\|\s+Mobility\s+\|([^\n]+)', out, re.M)
        self.assertIsNotNone(line, out)
        actual = [float(x) for x in re.findall(r'[+-]?\d+\.\d+', line[1])][:4]
        self.assertEqual(len(actual), 4, out)
        for measured, expected in zip(actual, self.mobility(board)):
            self.assertAlmostEqual(measured, expected, delta=0.006, msg=out)

    def test_open_board_both_colours_and_modalities(self):
        for kind in ('em', 'mc', 'cc'):
            for colour in ('w', 'b'):
                piece = kind.upper() if colour == 'w' else kind
                self.assert_mobility({**self.royals(), (1, 0): piece})

    def test_walls_and_crowded_board(self):
        n = self.size
        for kind in ('EM', 'MC', 'CC'):
            board = {**self.royals(), (1, 0): kind, (2, 1): '*', (3, 2): 'X', (4, 3): 'x'}
            self.assert_mobility(board)
        board = {(f, r): ('X' if (f + r) % 2 else 'x') for r in range(n) for f in range(n)}
        board.update(self.royals())
        board[1, 0] = 'EM'
        self.assert_mobility(board)

    def test_multiple_emperors_and_colour_symmetry(self):
        n = self.size
        board = {**self.royals(), (1, 0): 'EM', (2, 1): 'EM', (n - 2, n - 1): 'em', (n - 3, n - 2): 'em'}
        self.assert_mobility(board)
        mirror = {(n - 1 - f, n - 1 - r): pc.swapcase() for (f, r), pc in board.items()}
        a = self.evaluate(board, 'w')
        b = self.evaluate(mirror, 'b')
        pattern = r'Final evaluation\s+([+-]?\d+(?:\.\d+)?)'
        self.assertAlmostEqual(float(re.search(pattern, a)[1]), -float(re.search(pattern, b)[1]), delta=0.01)

    def test_shallow_search_with_trading_rule(self):
        n = self.size
        board = {**self.royals(), (1, 0): 'EM', (n - 2, n - 1): 'em'}
        self.command('setoption name UCI_Variant value emperor-trading\n'
                     'position fen ' + fen(board, n) + '\nisready\n')
        out = self.command('go depth 2\n', marker='bestmove ')
        self.assertRegex(out, r'info depth 2 ')
        self.assertRegex(out, r'(?m)^bestmove [a-z]\d+[a-z]\d+')
        self.command('setoption name UCI_Variant value emperor-evaluation\nisready\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
