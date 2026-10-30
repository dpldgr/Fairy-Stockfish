#!/usr/bin/env python3
"""Universal Betza moves, prohibited captures and Emperor trading rules."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest

SIZE = int(os.environ.get('BOARD_SIZE', '8'))
LAST = chr(ord('a') + SIZE - 1)


def fen(pieces, side='w'):
    board = {LAST + '1': 'K', LAST + str(SIZE): 'k', **pieces}
    rows = []
    for rank in range(SIZE, 0, -1):
        row, empty = [], 0
        for file in range(SIZE):
            piece = board.get(chr(ord('a') + file) + str(rank))
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


class UniversalLeaper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())
        cls.temp = tempfile.TemporaryDirectory()
        cls.config = Path(cls.temp.name) / 'universal.ini'
        cls.config.write_text(f'''[universal]
maxFile = {SIZE}
maxRank = {SIZE}
commoner = k
rook = r
piece = em:U
piece = pr:K
piece = v:W
castling = false
extinctionValue = loss
extinctionPieceTypes = k
startFen = {fen({'d4': 'EM'})}
[quiet:universal]
piece = em:mU
[capture:universal]
piece = em:cU
[mixed:universal]
piece = em:mUcK
[split:universal]
piece = em:mUcU
[legacy:universal]
customPiece1 = em:U
[prohibited:universal]
prohibitedCaptures = em:pr
[trading:universal]
tradingRule = em:[any!,{{k,pr,em}}]
[ban-royals:universal]
tradingRule = em:[any,{{k,pr,em}}]
[mobility:universal]
mobilityRegionWhiteCustomPiece1 = d4 a1 b7
[royal:universal]
commoner = -
king = k
extinctionPieceTypes = k
[royal-quiet:royal]
piece = em:mU
[royal-capture:royal]
piece = em:cU
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def output(self, name, board, side='w', commands='go perft 1\n'):
        result = subprocess.run([self.engine, 'load', str(self.config)],
                                input=f'setoption name UCI_Variant value {name}\n'
                                      f'position fen {fen(board, side)}\n' + commands + 'quit\n',
                                text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def moves(self, name, board, side='w'):
        output = self.output(name, board, side)
        self.assertIn('Nodes searched:', output)
        return set(re.findall(r'^(\S+): \d+$', output, re.M))

    def test_exact_destinations_and_modalities_for_both_colours(self):
        squares = {chr(ord('a') + f) + str(r) for f in range(SIZE) for r in range(1, SIZE + 1)}
        for side in ('w', 'b'):
            board = {'d4': 'EM' if side == 'w' else 'em', 'd5': 'V' if side == 'w' else 'v',
                     'b7': 'v' if side == 'w' else 'V'}
            friends = {'d4', 'd5', LAST + ('1' if side == 'w' else str(SIZE))}
            enemies = {'b7', LAST + (str(SIZE) if side == 'w' else '1')}
            for name in ('universal', 'quiet', 'capture', 'split', 'legacy'):
                with self.subTest(side=side, name=name):
                    targets = enemies if name == 'capture' else squares - friends
                    if name == 'quiet':
                        targets -= enemies
                    actual = {m[2:] for m in self.moves(name, board, side) if m.startswith('d4')}
                    self.assertEqual(actual, targets)

    def test_modality_resets_for_following_atom(self):
        moves = self.moves('mixed', {'d4': 'EM', 'e5': 'v', 'b7': 'v'})
        self.assertIn('d4a1', moves)
        self.assertIn('d4e5', moves)
        self.assertNotIn('d4b7', moves)

    def test_occupied_neighbours_do_not_block_universal_leap(self):
        board = {'d4': 'EM', **{s: 'V' for s in ('c3','d3','e3','c4','e4','c5','d5','e5')}, 'b7': 'v'}
        moves = self.moves('universal', board)
        self.assertIn('d4a1', moves)
        self.assertIn('d4b7', moves)
        self.assertNotIn('d4d5', moves)

    def test_walls_and_mobility_restrict_landings(self):
        moves = self.moves('universal', {'d4': 'EM', 'd5': '*', 'a1': '*'})
        self.assertNotIn('d4a1', moves)
        self.assertNotIn('d4d5', moves)
        self.assertIn('d4d6', moves)
        moves = self.moves('mobility', {'d4': 'EM', 'b7': 'v'})
        self.assertEqual({m for m in moves if m.startswith('d4')}, {'d4a1', 'd4b7'})

    def test_prohibited_captures_for_both_colours(self):
        for side in ('w', 'b'):
            board = {'d4': 'EM' if side == 'w' else 'em', 'b7': 'pr' if side == 'w' else 'PR',
                     'f3': 'v' if side == 'w' else 'V'}
            self.assertIn('d4b7', self.moves('universal', board, side))
            moves = self.moves('prohibited', board, side)
            self.assertNotIn('d4b7', moves)
            self.assertIn('d4f3', moves)
            self.assertIn('d4a1', moves)

    def test_emperor_protected_royal_captures(self):
        for side in ('w', 'b'):
            for victim in ('k', 'pr', 'em'):
                with self.subTest(side=side, victim=victim):
                    board = {'d4': 'EM' if side == 'w' else 'em',
                             'f6': victim if side == 'w' else victim.upper(),
                             'f8': 'r' if side == 'w' else 'R'}
                    self.assertIn('d4f6', self.moves('universal', board, side))
                    self.assertNotIn('d4f6', self.moves('trading', board, side))
                    del board['f8']
                    self.assertIn('d4f6', self.moves('trading', board, side))
                    self.assertNotIn('d4f6', self.moves('ban-royals', board, side))

    def test_adjacent_royal_and_protected_nonroyal(self):
        board = {'d4': 'EM', 'e5': 'pr', 'e8': 'r'}
        self.assertNotIn('d4e5', self.moves('trading', board))
        board['e5'] = 'v'
        self.assertIn('d4e5', self.moves('trading', board))

    def test_universal_capture_can_protect_a_royal(self):
        board = {'d4': 'EM', 'f6': 'pr', 'a2': 'em', 'b3': 'V'}
        self.assertIn('d4f6', self.moves('universal', board))
        self.assertNotIn('d4f6', self.moves('trading', board))

    def test_recapture_uses_resulting_occupancy(self):
        # The Emperor currently blocks this rook's protection of the prince.
        board = {'d4': 'EM', 'd2': 'r', 'd6': 'pr'}
        self.assertNotIn('d4d6', self.moves('trading', board))
        board['d5'] = 'V'
        self.assertIn('d4d6', self.moves('trading', board))

    def test_universal_capture_attack_detection_and_evasion(self):
        for name in ('royal', 'royal-capture', 'royal-quiet'):
            output = self.output(name, {'d4': 'EM'}, 'b', 'd\n')
            checkers = re.search(r'^Checkers:(.*)', output, re.M).group(1)
            self.assertEqual('d4' in checkers, name != 'royal-quiet')
        moves = self.moves('royal', {'b7': 'em', 'b1': 'R'})
        self.assertIn('b1b7', moves)
        self.assertNotIn(LAST + '1' + chr(ord(LAST) - 1) + '1', moves)

    def test_perft_undo_restores_position_and_key(self):
        output = self.output('trading', {'d4': 'EM', 'b7': 'em', 'f6': 'pr'}, commands='d\ngo perft 2\nd\n')
        self.assertGreater(int(re.search(r'Nodes searched: (\d+)', output).group(1)), 0)
        for pattern in (r'^Fen: (.+)', r'^Key: (\S+)'):
            values = re.findall(pattern, output, re.M)
            self.assertEqual(len(values), 2)
            self.assertEqual(values[0], values[1])

    def test_search_can_play_an_allowed_universal_capture(self):
        with subprocess.Popen([self.engine, 'load', str(self.config)], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as engine:
            timer = threading.Timer(60, engine.kill)
            timer.start()
            try:
                engine.stdin.write('setoption name UCI_Variant value trading\n'
                                   f'position fen {fen({"d4": "EM", "b7": "pr"})}\n'
                                   'go depth 2 searchmoves d4b7\n')
                engine.stdin.flush()
                lines = []
                for line in engine.stdout:
                    lines.append(line)
                    if line.startswith('bestmove '):
                        break
                engine.stdin.write('quit\n')
                engine.stdin.flush()
                _, errors = engine.communicate(timeout=10)
                self.assertEqual(engine.returncode, 0, errors)
                self.assertIn('info depth 2 ', ''.join(lines))
                self.assertRegex(''.join(lines), r'(?m)^bestmove d4b7(?: |$)')
            finally:
                timer.cancel()


if __name__ == '__main__':
    unittest.main()
