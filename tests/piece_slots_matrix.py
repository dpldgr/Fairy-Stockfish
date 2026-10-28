#!/usr/bin/env python3
"""Compile/run encoding checks for all capacities and representative boards."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    binary = str(Path(directory) / 'encoding')
    for files, ranks in ((8, 8), (12, 10), (16, 16), (19, 19), (32, 12)):
        for slots in range(64, 513, 64):
            subprocess.run(shlex.split(os.environ.get('CXX', 'g++'))
                           + ['-std=c++17', '-O2']
                           + shlex.split(os.environ.get('CXXFLAGS', ''))
                           + [f'-DBOARD_FILES={files}', f'-DBOARD_RANKS={ranks}',
                              f'-DPIECE_TYPE_CAPACITY={slots}', '-DIS_64BIT',
                              str(root / 'tests/piece_slots.cpp'), '-o', binary], check=True)
            subprocess.run([binary], check=True)
