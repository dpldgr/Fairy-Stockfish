#!/usr/bin/env python3
"""UCI verbosity protocol integration, including a real 15-second heartbeat."""
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import unittest

STATS = r'nodes \d+ nps \d+ hashfull \d+ tbhits \d+ time \d+'


class Engine:
    def __init__(self, binary, args=()):
        self.proc = subprocess.Popen([binary, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.lines = queue.Queue()
        def read():
            for line in self.proc.stdout:
                self.lines.put((time.monotonic(), line.rstrip()))
            self.lines.put((time.monotonic(), None))
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, text):
        self.proc.stdin.write(text + '\n')
        self.proc.stdin.flush()

    def until(self, predicate, timeout=90):
        result = []
        deadline = time.monotonic() + timeout
        while True:
            timestamp, line = self.lines.get(timeout=max(0.001, deadline - time.monotonic()))
            if line is None:
                raise AssertionError('Engine exited: ' + '\n'.join(s for _, s in result))
            result.append((timestamp, line))
            if predicate(line):
                return result

    def ready(self, commands=''):
        self.send(commands + '\nisready')
        return self.until(lambda line: line == 'readyok')

    def search(self, command):
        self.send(command)
        return self.until(lambda line: line.startswith('bestmove '))

    def timed_search(self, seconds):
        self.send('go infinite')
        timer = threading.Timer(seconds, lambda: self.send('stop'))
        timer.start()
        try:
            return self.until(lambda line: line.startswith('bestmove '), timeout=seconds + 30)
        finally:
            timer.cancel()

    def close(self):
        if self.proc.poll() is None:
            self.send('stop\nquit')
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.reader.join(timeout=3)
        assert self.proc.returncode == 0, self.proc.returncode

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class Verbosity(unittest.TestCase):
    binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())

    @staticmethod
    def normalized(lines):
        return [re.sub(r' (?:nps|time|hashfull) \d+', '', line)
                for _, line in lines if (line.startswith('info depth') and ' score ' in line)
                or line.startswith('bestmove ')]

    def test_option_default_and_handshakes(self):
        dialects = [('uci', 'uciok', 'option name UCI_Verbosity type spin default 3 min 1 max 3')]
        if int(os.environ.get('BOARD_SIZE', '8')) >= 9:
            dialects += [('usi', 'usiok', 'option name USI_Verbosity type spin default 3 min 1 max 3'),
                         ('ucci', 'ucciok', 'option UCI_Verbosity type spin default 3 min 1 max 3')]
        for command, end, expected in dialects:
            with self.subTest(protocol=command), Engine(self.binary) as engine:
                engine.send(command)
                lines = engine.until(lambda line: line == end)
                self.assertIn(expected, [s for _, s in lines])
        with Engine(self.binary) as engine:
            engine.send('xboard\nprotover 2')
            lines = engine.until(lambda line: line.startswith('feature done=1'))
            self.assertTrue(any('UCI_Verbosity -spin 3 1 3' in s for _, s in lines))
            engine.send('ping 17')
            self.assertIn('pong 17', [s for _, s in engine.until(lambda s: s == 'pong 17')])

    def test_fixed_depth_search_equivalence(self):
        outputs = []
        for level in (1, 2, 3):
            with Engine(self.binary) as engine:
                engine.ready(f'setoption name Use NNUE value false\nsetoption name UCI_Verbosity value {level}\n'
                             'ucinewgame\nposition startpos')
                lines = engine.search('go depth 5')
                outputs.append(self.normalized(lines))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])

    def test_perft_unchanged(self):
        for level in (1, 2, 3):
            with self.subTest(level=level), Engine(self.binary) as engine:
                engine.ready(f'setoption name UCI_Verbosity value {level}\nposition startpos')
                engine.send('go perft 3')
                lines = engine.until(lambda s: s.startswith('Nodes searched:'))
                self.assertEqual(lines[-1][1], 'Nodes searched: 8902')
                self.assertFalse(any(s.startswith('info nodes') for _, s in lines))

    def test_detailed_and_legacy_currmove(self):
        for level in (2, 3):
            with self.subTest(level=level), Engine(self.binary) as engine:
                engine.ready(f'setoption name Use NNUE value false\nsetoption name UCI_Verbosity value {level}\n'
                             'ucinewgame\nposition startpos')
                lines = engine.timed_search(5)
                currents = [s for _, s in lines if ' currmove ' in s]
                self.assertTrue(currents, '\n'.join(s for _, s in lines))
                suffix = r' ' + STATS if level == 3 else ''
                for line in currents:
                    self.assertRegex(line, r'^info depth \d+ currmove \S+ currmovenumber \d+' + suffix + '$')

    def test_multithread_multipv_counters(self):
        with Engine(self.binary) as engine:
            engine.ready('setoption name Use NNUE value false\nsetoption name UCI_Verbosity value 3\n'
                         'setoption name Threads value 2\nsetoption name MultiPV value 2\n'
                         'ucinewgame\nposition startpos')
            lines = engine.timed_search(5)
            currents = [s for _, s in lines if ' currmove ' in s]
            self.assertTrue(currents)
            previous = 0
            for line in currents:
                self.assertRegex(line, r'^info depth \d+ currmove \S+ currmovenumber \d+ ' + STATS + '$')
                nodes = int(re.search(r' nodes (\d+)', line)[1])
                self.assertGreaterEqual(nodes, previous)
                previous = nodes
            self.assertTrue(any(' multipv 2 ' in s for _, s in lines))

    def test_real_heartbeat_and_next_search_reset(self):
        # A terminal infinite search waits for stop without emitting PV/currmove.
        with Engine(self.binary) as engine:
            engine.ready('setoption name Use NNUE value false\n'
                         'setoption name UCI_Verbosity value 3\n'
                         'position fen 7k/6Q1/5K2/8/8/8/8/8 b - - 0 1')
            lines = engine.timed_search(16.5)
            depth_zero = next(t for t, s in lines if s.startswith('info depth 0 '))
            beats = [(t, s) for t, s in lines if s.startswith('info nodes ')]
            self.assertEqual(len(beats), 1, lines)
            self.assertGreaterEqual(beats[0][0] - depth_zero, 14.9)
            self.assertRegex(beats[0][1], '^info ' + STATS + '$')
            # An idle gap must not shorten the next search's first heartbeat.
            time.sleep(2)
            engine.ready('position fen 7k/6Q1/5K2/8/8/8/8/8 b - - 0 1')
            second = engine.timed_search(16.5)
            depth_zero = next(t for t, s in second if s.startswith('info depth 0 '))
            beats = [(t, s) for t, s in second if s.startswith('info nodes ')]
            self.assertEqual(len(beats), 1, second)
            self.assertGreaterEqual(beats[0][0] - depth_zero, 14.9)


if __name__ == '__main__':
    unittest.main()
