#!/usr/bin/env python3
"""Validate shared Make/Python capacity normalization without building objects."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class BuildFeatures(unittest.TestCase):
    def make(self, *options, js=False):
        cmd = ['make', '-s', '--no-print-directory', '-C', str(ROOT / 'src')]
        cmd += ['-f', 'Makefile_js', '-n', 'build'] if js else ['ARCH=x86-64', 'config-sanity']
        return subprocess.run(cmd + list(options), capture_output=True, text=True)

    def test_make_normalizes_capacities(self):
        for requested in (64, 65, 128, 129, 192, 193, 256, 257, 320, 321, 384, 385, 448, 449, 511, 512):
            for js in (False, True):
                with self.subTest(requested=requested, js=js):
                    result = self.make(f'piece_slots={requested}', js=js)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(f'-DPIECE_TYPE_CAPACITY={(requested + 63) // 64 * 64}', result.stdout)
                    self.assertIn('-DENABLE_GATING=1', result.stdout)

    def test_make_rejects_invalid_inputs(self):
        for value in ('', '0', '63', '513', '-64', '64.0', 'abc', '64 128'):
            for js in (False, True):
                with self.subTest(value=value, js=js):
                    result = self.make(f'piece_slots={value}', js=js)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('piece_slots', result.stderr)
        for value in ('', 'true', '0', 'YES', 'yes no'):
            self.assertNotEqual(self.make(f'gating={value}').returncode, 0)

    def test_gating_disabled(self):
        for js in (False, True):
            result = self.make('gating=no', js=js)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('-DENABLE_GATING=0', result.stdout)

    def setup_args(self, slots, gating):
        with patch.dict(os.environ, PIECE_SLOTS=slots, GATING=gating), \
             patch('setuptools.setup'), contextlib.redirect_stdout(io.StringIO()):
            # setup.py resolves package files relative to the checkout root.
            previous = Path.cwd()
            try:
                os.chdir(ROOT)
                return runpy.run_path(str(ROOT / 'setup.py'))['args']
            finally:
                os.chdir(previous)

    def test_python_normalizes_and_validates(self):
        self.assertIn('-DPIECE_TYPE_CAPACITY=192', self.setup_args('129', 'no'))
        self.assertIn('-DENABLE_GATING=0', self.setup_args('512', 'no'))
        for slots, gating in (('63', 'yes'), ('513', 'yes'), ('abc', 'yes'), ('64', 'true')):
            with self.assertRaises(ValueError):
                self.setup_args(slots, gating)


if __name__ == '__main__':
    unittest.main()
