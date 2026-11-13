#!/usr/bin/env python3
"""DTX export: independent decoding, mixed-material appends and bin parity."""
import itertools
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import unittest
from mate_table_export import records as bin_records
from uci_verbosity import Engine

PREFIX='info string mate-table '
ROOT=Path(__file__).parent

def read_header(path):
    with open(path,'rb') as stream:
        fixed=stream.read(64)
        assert fixed[:8]==b'DTXTRN\r\n'
        version,prefix,length,stride,files,ranks,types,maximum,sb,tb,db,metric,vn,cn,count=struct.unpack_from('<HHIIHHHHBBBBIIQ',fixed,8)
        assert version==1 and prefix==64 and metric==1
        assert fixed[48:64]==bytes((0,0,0,0,1,0,1,1))+bytes(8)
        stream.seek(0);raw=stream.read(length)
        name=raw[64:64+vn].decode();at=64+vn;symbols=[]
        for _ in range(types+1):
            n=struct.unpack_from('<H',raw,at)[0];at+=2
            symbols.append(raw[at:at+n].decode());at+=n
        assert at==64+vn+cn and not any(raw[at:])
        assert Path(path).stat().st_size==length+count*stride
        return dict(header_bytes=length,stride=stride,files=files,ranks=ranks,types=types,maximum=maximum,sb=sb,tb=tb,db=db,count=count,name=name,symbols=symbols)

def records(path):
    h=read_header(path)
    with open(path,'rb') as stream:
        stream.seek(h['header_bytes'])
        for _ in range(h['count']):
            raw=stream.read(h['stride']);word=int.from_bytes(raw,'little');at=0
            def take(n):
                nonlocal at
                v=(word>>at)&((1<<n)-1);at+=n;return v
            kings=(take(h['sb']),take(h['sb']));pieces=[];empty=False
            for i in range(h['maximum']-2):
                square,kind,color=take(h['sb']),take(h['tb']),take(1)
                if kind:
                    assert not empty
                    pieces.append((square,h['symbols'][kind].lower(),color))
                else:assert square==color==0;empty=True
            turn=take(1);distance=take(h['db'])
            if distance>>(h['db']-1):distance-=1<<h['db']
            assert not word>>at
            if distance==-(1<<(h['db']-1)):score=result=0
            else:
                result=1 if distance>0 else -1
                score=result*(32000-abs(distance))
            yield kings,tuple(pieces),turn,score,result

class DtxExports(unittest.TestCase):
    binary=str(Path(os.environ.get('STOCKFISH','./stockfish')).resolve())
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.config=cls.root/'dtx.ini'
        cls.config.write_text((ROOT/'fixtures/metal-chess.ini').read_text()+'''\n[dtx-tiny:metal-chess]\nmaxFile = 3\nmaxRank = 3\n[dtx-rectangle:metal-chess]\nmaxFile = 4\nmaxRank = 3\n[dtx-stale-win:metal-chess]\nstalemateValue = win\n[dtx-eight:dtx-tiny]\ncustomPiece4 = x:W\ncustomPiece5 = y:F\ncustomPiece6 = z:N\n[dtx-alias:dtx-tiny]\npiece = sb:<b>\n''')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def engine(self,variant='metal-chess'):
        e=Engine(self.binary,('load',str(self.config)))
        e.ready('setoption name Use NNUE value false\nsetoption name UCI_Variant value '+variant);return e
    def build(self,e,material,path,extra=''):
        e.send(f'mate-table pieces {material} format info export "{path}" {extra}')
        lines=[s for _,s in e.until(lambda s:s.startswith(PREFIX+'complete ') or s.startswith(PREFIX+'error '),timeout=180)]
        self.assertTrue(lines[-1].startswith(PREFIX+'complete '),'\n'.join(lines))
        report=next(s for s in lines if s.startswith(PREFIX+'export complete '))
        return int(re.search(r'records (\d+)',report)[1])
    def test_complete_metal_two_three_and_mixed_append(self):
        target=self.root/'metal.dtx';expected=self.root/'metal.bin'
        total=0
        with self.engine() as e:
            for material in ('{K,k}','{K,k,Q}','{K,k,q}','{K,k,R}','{K,k,r}','{K,k,B}','{K,k,b}','{K,k,N}','{K,k,n}'):
                n=self.build(e,material,target);m=self.build(e,material,expected,'entrysize 8');self.assertEqual(n,m);total+=n
                h=read_header(target);self.assertEqual(h['count'],total)
                self.assertEqual((h['maximum'],h['sb'],h['tb'],h['db'],h['stride']),(4,6,3,11,6))
                self.assertEqual(h['symbols'],['K','P','Q','R','B','N'])
        self.assertEqual(total,3201224)
        for n,(a,b) in enumerate(itertools.zip_longest(records(target),bin_records(expected,8)),1):self.assertEqual(a,b)
        self.assertEqual(n,total)
        # Keep generated real data for optional integration tests only when requested.
        destination=os.environ.get('DTX_TEST_DATA')
        if destination:
            import shutil
            Path(destination).mkdir(parents=True,exist_ok=True)
            shutil.copyfile(target,Path(destination)/'metal-2-3.dtx');shutil.copyfile(expected,Path(destination)/'metal-2-3.bin')
    def test_four_piece_and_rectangle_parity(self):
        for variant,width,height in [('dtx-tiny',3,3),('dtx-rectangle',4,3)]:
            target=self.root/(variant+'.dtx');expected=self.root/(variant+'.bin')
            with self.engine(variant) as e:
                for material in ('{K,k}','{K,k,B}','{K,k,Q,Q}','{K,k,Q,q}','{K,k,Q,R}','{K,k,Q,r}'):
                    self.assertEqual(self.build(e,material,target),self.build(e,material,expected,'entrysize 7'))
            for a,b in itertools.zip_longest(records(target),bin_records(expected,7,width,height)):self.assertEqual(a,b)
    def test_catalogue_empty_code_boundary_and_multicharacter(self):
        for variant,material in [('dtx-eight','{K,k,Z}'),('dtx-alias','{K,k,SB}')]:
            target=self.root/(variant+'.dtx');expected=self.root/(variant+'.bin')
            with self.engine(variant) as e:
                self.assertEqual(self.build(e,material,target),self.build(e,material,expected,'entrysize 8'))
            h=read_header(target)
            if variant=='dtx-eight':self.assertEqual((h['types'],h['tb']),(8,4))
            names=tuple(s.lower() for s in h['symbols'][1:])
            for a,b in itertools.zip_longest(records(target),bin_records(expected,8,3,3,names)):self.assertEqual(a,b)
    def test_reject_invalid_append_without_changes(self):
        original=self.root/'append.dtx'
        with self.engine() as e:self.build(e,'{K,k}',original)
        saved=original.read_bytes()
        bad=[]
        h=read_header(original)
        for offset,value in [(0,0),(8,2),(20,7),(24,4),(30,7),(40,0),(56,1)]:
            raw=bytearray(saved);raw[offset]=value;bad.append(bytes(raw))
        bad.extend((saved[:-1],saved+b'x'))
        with self.engine() as e:
            for i,raw in enumerate(bad):
                p=self.root/f'bad-{i}.dtx';p.write_bytes(raw)
                e.send(f'mate-table pieces {{K,k}} export "{p}"')
                lines=[s for _,s in e.until(lambda s:s.startswith(PREFIX+'error '))]
                self.assertIn('error',lines[-1]);self.assertEqual(p.read_bytes(),raw)
        with self.engine('dtx-tiny') as e:
            e.send(f'mate-table pieces {{K,k}} export "{original}"')
            e.until(lambda s:s.startswith(PREFIX+'error '))
        self.assertEqual(original.read_bytes(),saved)
    def test_explicit_bin_width_and_five_piece_rejected_early(self):
        for variant,material,extra,reason in [('metal-chess','{K,k}','entrysize 7','entrysize applies only'),('metal-chess','{K,k,B,N,N}','','at most four'),('dtx-stale-win','{K,k,B}','','terminal wins')]:
            with self.engine(variant) as e:
                p=self.root/'not-created.dtx'
                e.send(f'mate-table pieces {material} export "{p}" {extra}')
                lines=[s for _,s in e.until(lambda s:s.startswith(PREFIX+'error '))]
                self.assertIn(reason,lines[-1]);self.assertFalse(p.exists())

if __name__=='__main__':unittest.main()
