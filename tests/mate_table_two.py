#!/usr/bin/env python3
"""Bare-King tables: complete legal sets, native probes and both export codecs."""
import itertools
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest

from mate_table_export import records, PREFIX
from uci_verbosity import Engine


def legal_states(files, ranks):
    return {(wk, bk, turn) for wk, bk in itertools.permutations(range(files * ranks), 2)
            if max(abs(wk % files - bk % files), abs(wk // files - bk // files)) > 1
            for turn in (0, 1)}


def fen(wk, bk, turn, files=8, ranks=8, symbols=('K', 'k')):
    board = {wk: symbols[0], bk: symbols[1]}
    rows = [','.join(board.get(r * files + f, '1') for f in range(files))
            for r in range(ranks - 1, -1, -1)]
    return '/'.join(rows) + (' b' if turn else ' w') + ' - - 0 1'


class TwoKings(unittest.TestCase):
    binary = str(Path(os.environ.get('STOCKFISH', './stockfish')).resolve())

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.config = cls.folder / 'kings.ini'
        cls.config.write_text((Path(__file__).parent / 'fixtures/metal-chess.ini').read_text() + '''
[two-small:metal-chess]
maxFile = 3
maxRank = 3
[two-rect:metal-chess]
maxFile = 4
maxRank = 3
[two-alias:two-small]
king = ck
[two-pure:two-small]
pawn = -
queen = -
customPiece1 = -
customPiece2 = -
customPiece3 = -
startFen = 2k/3/K2 w - - 0 1
[two-extinction:two-small]
extinctionValue = loss
[two-baring:two-small]
baringRule = true
[two-no-check:two-small]
checking = false
[two-royal-promotion:two-small]
promotedPieceType = k:q
''')
        if int(os.environ.get('BOARD_SIZE', '8')) >= 16:
            with cls.config.open('a') as out:
                out.write('''
[two-large:metal-chess]
maxFile = 16
maxRank = 16
''')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def engine(self, variant='metal-chess'):
        engine = Engine(self.binary, ('load', str(self.config)))
        engine.ready('setoption name UCI_Variant value ' + variant)
        return engine

    def build(self, engine, material='{K,k}', options='', command='mate-table'):
        prefix = '' if 'format table' in options else PREFIX
        engine.send(command + ' pieces ' + material + ' ' + options)
        lines = [s for _, s in engine.until(lambda s: s.startswith(prefix + 'complete ')
                                           or s.startswith(prefix + 'error ') or s.startswith(PREFIX + 'error '))]
        self.assertTrue(lines[-1].startswith(prefix + 'complete '), '\n'.join(lines))
        return lines

    def test_complete_metal_draw_exports_and_append(self):
        expected = legal_states(8, 8)
        self.assertEqual(len(expected), 7224)
        paths = {}
        with self.engine() as engine:
            for size in (72, 8):
                path = self.folder / f'metal-kings-{size}.bin'
                paths[size] = path
                size_option = '' if size == 72 else ' entrysize 8'
                lines = self.build(engine, options=f'export "{path}"{size_option}')
                self.assertIn(f'export complete records 7224 entrysize {size} bytes {7224 * size}', '\n'.join(lines))
                seen = set()
                for kings, supports, turn, score, result in records(path, size):
                    self.assertEqual((supports, score, result), ((), 0, 0))
                    self.assertNotIn((*kings, turn), seen)
                    seen.add((*kings, turn))
                self.assertEqual(seen, expected)
                original = path.read_bytes()
                self.build(engine, material='{ k, K, }', options=f'entrysize {size} export "{path}"')
                self.assertEqual(path.read_bytes(), original + original)
                raw = '\n'.join(s for _, s in engine.ready('mate-table stats raw'))
                self.assertIn('legal_states 7224', raw)
                self.assertEqual(raw.count('legal 3612 wins 0 draws 3612 losses 0'), 2)
        self.assertEqual(list(records(paths[72], 72)), list(records(paths[8], 8)))

    def test_rectangles_aliases_and_zero_support_schema(self):
        for variant, files, names, symbols in [('two-small', 3, ('p','q','r','b','n'), ('K','k')),
                                              ('two-rect', 4, ('p','q','r','b','n'), ('K','k')),
                                              ('two-alias', 3, ('p','q','r','b','n'), ('CK','ck')),
                                              ('two-pure', 3, (), ('K','k'))]:
            expected = legal_states(files, 3)
            for size in (8, 72):
                # This alias fixture retains its parent's single-character
                # startFen; use compact output, which needs no NNUE anchor.
                if variant == 'two-alias' and size == 72:
                    continue
                with self.subTest(variant=variant, size=size), self.engine(variant) as engine:
                    path = self.folder / f'{variant}-{size}.bin'
                    self.build(engine, '{' + ','.join(symbols) + '}', f'export "{path}" entrysize {size}')
                    decoded = list(records(path, size, files, 3, names))
                    self.assertEqual({(*kings, turn) for kings, _, turn, _, _ in decoded}, expected)
                    self.assertTrue(all((supports, score, result) == ((),0,0) for _,supports,_,score,result in decoded))

    def test_native_probes_cache_switching_and_formats(self):
        with self.engine() as engine:
            for view, command, material in [('info','mate-table','{k,K}'),
                                            ('info-table','mate-table build','{K,k}'),
                                            ('table','api mate-table','{K,k,}')]:
                lines = self.build(engine, material, f'format {view} memory 1', command)
                if view == 'table':
                    self.assertFalse(any(s.startswith(PREFIX) for s in lines))
                cached = [s for _,s in engine.ready('mate-table stats')]
                self.assertIn(PREFIX + 'all legal positions draw', cached)
            for wk,bk,turn in random.Random(15).sample(sorted(legal_states(8,8)), 32):
                engine.send('position fen ' + fen(wk,bk,turn) + '\nmate-table probe')
                line=engine.until(lambda s:s.startswith(PREFIX+'probe '))[-1][1]
                self.assertIn('result draw bestmove ',line)
                self.assertNotIn('dtm_',line)
                best=line.rsplit(' ',1)[1]
                engine.send('go perft 1')
                divided=[s for _,s in engine.until(lambda s:s.startswith('Nodes searched:'))]
                legal={s.split(':')[0] for s in divided if s.endswith(': 1')}
                self.assertIn(best,legal)
            for position in ['7k/8/8/8/8/8/8/KR6 w - - 0 1',
                             '8/8/8/8/8/8/8/Kk6 w - - 0 1']:
                engine.send('position fen '+position+'\nmate-table probe')
                engine.until(lambda s:s.startswith(PREFIX+'error '))
            engine.ready('setoption name UCI_Variant value chess')
            engine.send('mate-table status')
            engine.until(lambda s:s==PREFIX+'status empty')
            engine.ready('setoption name UCI_Variant value metal-chess')
            engine.send('mate-table status')
            engine.until(lambda s:s==PREFIX+'status ready')
            self.build(engine,'{K,B,k}')
            engine.send('position fen 7k/8/8/8/8/8/8/K7 w - - 0 1\nmate-table probe')
            engine.until(lambda s:s.startswith(PREFIX+'error '))
            self.build(engine)
            engine.ready('mate-table clear')
            engine.send('mate-table status')
            engine.until(lambda s:s==PREFIX+'status empty')

    def test_append_kings_to_existing_three_piece_material(self):
        with self.engine('two-small') as engine:
            for size in (72,8):
                path=self.folder/f'mixed-{size}.bin'
                self.build(engine,'{K,B,k}',f'export "{path}" entrysize {size}')
                original=path.read_bytes()
                self.build(engine,options=f'export "{path}" entrysize {size}')
                self.assertTrue(path.read_bytes().startswith(original))
                decoded=list(records(path,size,3))
                self.assertTrue(all(len(row[1])==1 for row in decoded[:len(original)//size]))
                kings=decoded[len(original)//size:]
                self.assertEqual({(*row[0],row[2]) for row in kings},legal_states(3,3))

    def test_reject_unsupported_and_malformed_without_replacing_cache(self):
        for variant in ('two-extinction','two-baring','two-no-check','two-royal-promotion'):
            with self.subTest(variant=variant),self.engine(variant) as engine:
                engine.send('mate-table pieces {K,k}')
                engine.until(lambda s:s.startswith(PREFIX+'error unsupported:'))
        with self.engine() as engine:
            self.build(engine)
            for material in ('{K}','{k}','{K,K}','{k,k}','{K,k,k}','{K,k,missing}','{K,,k}'):
                engine.send('mate-table pieces '+material)
                engine.until(lambda s:s.startswith(PREFIX+'error '))
                self.assertIn(PREFIX+'status ready',[s for _,s in engine.ready('mate-table status')])
            for option in ('color white','partner b','opponent n'):
                engine.send('mate-table pieces {K,k} '+option)
                engine.until(lambda s:s.startswith(PREFIX+'error '))

    def test_command_line_waits_for_export(self):
        for prefix in ([],['api']):
            path=self.folder/f'cli-{len(prefix)}.bin'
            run=subprocess.run([self.binary,*prefix,'mate-table','pieces','{k,K}','export',str(path),'entrysize','8'],
                               capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn(PREFIX+'complete ',run.stdout)
            self.assertEqual(path.stat().st_size,7224*8)

    @unittest.skipUnless(int(os.environ.get('BOARD_SIZE','8'))>=16,'large build')
    def test_large_table_and_export_limits(self):
        with self.engine('two-large') as engine:
            self.build(engine,options='memory 1')
            raw='\n'.join(s for _,s in engine.ready('mate-table stats raw'))
            self.assertIn('legal_states '+str(len(legal_states(16,16))),raw)
            for size in (72,):
                path=self.folder/f'large-{size}.bin'
                engine.send(f'mate-table pieces {{K,k}} export "{path}" entrysize {size}')
                engine.until(lambda s:s.startswith(PREFIX+'error export board exceeds'))
                self.assertFalse(path.exists())

    @unittest.skipUnless(int(os.environ.get('BOARD_SIZE','8'))>=16,'large build')
    def test_compact_large_board_export(self):
        expected = legal_states(16,16)
        with self.engine('two-large') as engine:
            for size in (7,8,144):
                path=self.folder/f'wide-compact-{size}.bin'
                self.build(engine,options=f'export "{path}" entrysize {size}')
                decoded=list(records(path,size,16))
                self.assertEqual(len(decoded),len(expected))
                self.assertEqual({(*row[0],row[2]) for row in decoded},expected)
                self.assertTrue(all(row[1]==() and row[3:]==(0,0) for row in decoded))


if __name__=='__main__':
    unittest.main()
