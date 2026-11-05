#!/usr/bin/env python3
"""Full-board ray oracle, high coordinates, compound routes and search smoke.

STOCKFISH=/path/to/engine BOARD_SIZE=36 python3 tests/large_boards.py
Run once at 25 and once at 36, with matching 512-slot executables.
"""
import os
from pathlib import Path
import queue
import random
import re
import subprocess
import tempfile
import threading
import unittest


def square(f, r):
    name = ''
    while f >= 0:
        name = chr(97 + f % 26) + name
        f = f // 26 - 1
    return name + str(r + 1)


def fen(board, size, side='w'):
    rows = []
    for r in range(size - 1, -1, -1):
        row, empty = [], 0
        for f in range(size):
            pc = board.get((f, r))
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


class LargeBoards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.size = int(os.environ.get('BOARD_SIZE', '36'))
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'large.ini'
        n = cls.size
        cls.config.write_text(f'''[large]
maxFile = {n}
maxRank = {n}
piece = k:<commoner>
piece = r:R
piece = b:B
piece = x:W
piece = s:j2Q6
piece = p:fW +p:<r>
piece = a:K
piece = h:R
piece = l:KNAD
piece = u:U
castling = false
doubleStep = false
extinctionValue = loss
extinctionPieceTypes = k
extinctionPseudoRoyal = false
nMoveRule = 0
nFoldRule = 3
promotionRegionMandatoryWhite<p> = *{n}
promotionRegionMandatoryBlack<p> = *1
promotionPolicy = optional:{{}} mandatory:{{oi}}
lionMovePieces = l(FFFFFFFFFFFFFFFF)
hookMovePieces = h:R-sR:1!
tenjikuTripleStepPieceTypes = {{a}}

[large-limits:large]
tradingRule = u:[any!,{{k}}]
''')
        cls.engine = subprocess.Popen([os.environ['STOCKFISH'], 'load', str(cls.config)],
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
        out = cls.command('setoption name UCI_Variant value large\nsetoption name Use NNUE value false\nisready\n')
        assert 'piece -' not in out and 'Invalid' not in out, out

    @classmethod
    def command(cls, text, search=False):
        cls.engine.stdin.write(text)
        cls.engine.stdin.flush()
        out = []
        ready = False
        perft_done = 'go perft' not in text
        while True:
            line = cls.lines.get(timeout=180)
            if line is None:
                raise AssertionError('Engine exited:\n' + ''.join(out))
            out.append(line)
            ready |= line.strip() == 'readyok'
            perft_done |= 'Nodes searched:' in line
            if (search and line.startswith('bestmove ')) or (not search and ready and perft_done):
                return ''.join(out)

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

    def output(self, board, side='w', commands='go perft 1\n'):
        return self.command('position fen ' + fen(board, self.size, side) + '\n' + commands + 'isready\n')

    def moves(self, board, side='w'):
        out = self.output(board, side)
        self.assertIn('Nodes searched:', out)
        moves = re.findall(r'^(\S+): \d+$', out, re.M)
        self.assertEqual(len(moves), len(set(moves)))
        return set(moves)

    def royals(self):
        n = self.size
        return {(0, 0): 'K', (n - 1, n - 1): 'k'}

    def test_ray_oracle_at_edges_and_word_boundaries(self):
        rng = random.Random(23625)
        n = self.size
        origins = [(1, 0), (n - 2, n - 1), (n // 2, n // 2),
                   (64 % n, 64 // n), (512 % n, 512 // n)]
        directions = [(f, r) for f in (-1, 0, 1) for r in (-1, 0, 1) if f or r]
        for origin in origins:
            for side in ('w', 'b'):
                for pc in ('r', 'b', 's'):
                    board = self.royals()
                    board[origin] = pc.upper() if side == 'w' else pc
                    empty = [(f, r) for f in range(n) for r in range(n) if (f, r) not in board]
                    for sq in rng.sample(empty, 60):
                        board[sq] = rng.choice(('x', 'X', '*'))
                    expected = set()
                    for df, dr in directions:
                        if pc == 'r' and df and dr:
                            continue
                        if pc == 'b' and (not df or not dr):
                            continue
                        for distance in range(1, n):
                            target = origin[0] + df * distance, origin[1] + dr * distance
                            if not (0 <= target[0] < n and 0 <= target[1] < n):
                                break
                            if pc == 's' and distance > 6:
                                break
                            occupant = board.get(target)
                            if occupant == '*':
                                break
                            if pc == 's' and distance <= 2:
                                continue
                            if not occupant or occupant.isupper() != (side == 'w'):
                                expected.add(square(*origin) + square(*target))
                            if occupant:
                                break
                    with self.subTest(origin=origin, side=side, piece=pc):
                        prefix = square(*origin)
                        actual = {m for m in self.moves(board, side)
                                  if m.startswith(prefix) and m[len(prefix)].isalpha()}
                        self.assertEqual(actual, expected)

    def test_far_corner_compound_routes_and_undo(self):
        n = self.size
        origin = square(n - 1, n - 1)
        steps = [square(n - i, n - i) for i in (2, 3, 4)]
        board = {(0, 0): 'K', (2, 2): 'k', (n - 1, n - 1): 'A'}
        moves = self.moves(board)
        for count in (1, 2, 3):
            self.assertIn(origin + ''.join(steps[:count]), moves)
        out = self.output(board, commands='d\ngo perft 2\nd\n')
        self.assertEqual(len(re.findall(r'^Fen:', out, re.M)), 2)
        self.assertEqual(*re.findall(r'^Fen: (.*)', out, re.M))
        self.assertEqual(*re.findall(r'^Key: (.*)', out, re.M))
        for pc in ('L', 'H'):
            board[n - 1, n - 1] = pc
            out = self.output(board, commands='d\ngo perft 2\nd\n')
            self.assertEqual(*re.findall(r'^Fen: (.*)', out, re.M))
            self.assertEqual(*re.findall(r'^Key: (.*)', out, re.M))

    def test_last_rank_promotion_both_colours(self):
        n = self.size
        for side, rank, target in [('w', n - 2, n - 1), ('b', 1, 0)]:
            board = self.royals()
            origin = n - 2, rank
            board[origin] = 'P' if side == 'w' else 'p'
            move = square(*origin) + square(n - 2, target)
            moves = self.moves(board, side)
            self.assertIn(move + '+', moves)
            self.assertNotIn(move, moves)
            out = self.command('position fen ' + fen(board, n, side) + ' moves ' + move + '+\nd\nisready\n')
            self.assertIn('+' + board[origin], re.search(r'^Fen: (.*)', out, re.M).group(1))

    def test_shallow_search(self):
        n = self.size
        board = self.royals()
        board[2, 3] = 'R'
        board[n - 3, n - 4] = 'r'
        legal = self.moves(board)
        if n * n > 640:
            self.command('setoption name Use NNUE value true\nisready\n')
        self.command('position fen ' + fen(board, n) + '\nisready\n')
        out = self.command('go depth 4\n', search=True)
        if n * n > 640:
            self.assertIn('classical evaluation enabled', out)
        self.assertRegex(out, r'info depth 4 ')
        best = re.search(r'^bestmove (\S+)', out, re.M).group(1)
        self.assertIn(best, legal)

    def test_universal_leaper_evaluation(self):
        n = self.size
        board = {**self.royals(), (1, 0): 'U'}
        out = self.output(board, commands='eval\n')
        self.assertRegex(out, r'Final evaluation\s+[+-]?\d')
        # A mobility bonus must survive multiplication before division even
        # with hundreds of destinations, for both sides of the evaluation.
        board[1, 0] = 'u'
        out = self.output(board, commands='eval\n')
        self.assertRegex(out, r'Final evaluation\s+[+-]?\d')

    def test_limits_inside_large_capture_tree(self):
        n = self.size
        board = {**self.royals(), (0, 1): 'R', (n - 1, n - 2): 'r',
                 (n // 2, 1): 'U', (n // 2, n - 2): 'u'}
        for f in range(n):
            board[f, 5] = 'X'
            board[f, n - 6] = 'x'
        self.command('setoption name UCI_Variant value large-limits\nisready\n')
        watchdog = threading.Timer(30, self.engine.kill)
        try:
            # Protected royals keep the universal leapers from ending the game
            # immediately; quiescence has a large tree of non-royal captures.
            self.command('position fen ' + fen(board, n) + '\nisready\n')
            watchdog.start()
            out = self.command('go nodes 2048\n', search=True)
            self.assertRegex(out, r'(?m)^bestmove [a-z]', msg=out)
            self.assertIsNone(self.engine.poll(), out)
        finally:
            watchdog.cancel()
            if self.engine.poll() is None:
                self.command('setoption name UCI_Variant value large\nisready\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
