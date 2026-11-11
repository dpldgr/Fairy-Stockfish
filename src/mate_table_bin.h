/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#ifndef MATE_TABLE_BIN_H_INCLUDED
#define MATE_TABLE_BIN_H_INCLUDED

// Standalone compact-record codec, also usable by a variant's training DLL.
// No engine headers, native bitfields, alignment or host byte order required.
#include <array>
#include <cstdint>

namespace Stockfish::MateTableBin {

struct Support {
  uint8_t square = 0, type = 0, color = 0;
};

struct Entry {
  std::array<uint8_t, 2> kings{}; // White, Black; dense rank-major squares
  std::array<Support, 3> pieces{};
  uint8_t count = 0, turn = 0;   // White=0, Black=1
  int16_t score = 0;
  int8_t result = 0;            // Side-to-move WDL: -1, 0, +1
};

// Dense type indices enumerate every configured non-king type in slot order.
// The separately stored King is implicit and is not in this index range.
inline bool valid(const Entry& e, unsigned squares, unsigned types) {
  if (!squares || squares > 64 || types > 8 || e.count > 3 || e.turn > 1
      || e.result < -1 || e.result > 1 || e.kings[0] >= squares || e.kings[1] >= squares
      || e.kings[0] == e.kings[1]) return false;
  uint64_t occupied = (uint64_t(1) << e.kings[0]) | (uint64_t(1) << e.kings[1]);
  for (unsigned i = 0; i < e.count; ++i)
  {
      const Support& p = e.pieces[i];
      if (p.square >= squares || p.type >= types || p.color > 1
          || (occupied & (uint64_t(1) << p.square))) return false;
      occupied |= uint64_t(1) << p.square;
  }
  return true;
}

// Little-endian 64-bit word:
// [0:6] WK, [6:6] BK, [12:10]*3 supports (square:6,type:3,color:1),
// [42:1] turn, [43:2] support count, [45:16] signed score,
// [61:2] result+1, [63:1] reserved zero. Unused support words are zero.
inline bool encode8(const Entry& e, uint8_t* bytes, unsigned squares, unsigned types) {
  if (!valid(e, squares, types)) return false;
  uint64_t word = e.kings[0] | (uint64_t(e.kings[1]) << 6);
  for (unsigned i = 0; i < e.count; ++i)
  {
      const Support& p = e.pieces[i];
      word |= uint64_t(p.square | (unsigned(p.type) << 6) | (unsigned(p.color) << 9)) << (12 + 10 * i);
  }
  word |= uint64_t(e.turn) << 42;
  word |= uint64_t(e.count) << 43;
  word |= uint64_t(uint16_t(e.score)) << 45;
  word |= uint64_t(e.result + 1) << 61;
  for (unsigned i = 0; i < 8; ++i) bytes[i] = uint8_t(word >> (8 * i));
  return true;
}

inline bool decode8(const uint8_t* bytes, Entry& entry, unsigned squares, unsigned types) {
  uint64_t word = 0;
  for (unsigned i = 0; i < 8; ++i) word |= uint64_t(bytes[i]) << (8 * i);
  unsigned result = unsigned((word >> 61) & 3);
  if ((word >> 63) || result == 3) return false;
  Entry e;
  e.kings = {uint8_t(word & 63), uint8_t((word >> 6) & 63)};
  e.turn = uint8_t((word >> 42) & 1);
  e.count = uint8_t((word >> 43) & 3);
  unsigned score = unsigned((word >> 45) & 65535);
  e.score = int16_t(score < 32768 ? int(score) : int(score) - 65536);
  e.result = int8_t(int(result) - 1);
  for (unsigned i = 0; i < 3; ++i)
  {
      unsigned p = unsigned((word >> (12 + 10 * i)) & 1023);
      if (i >= e.count) { if (p) return false; }
      else e.pieces[i] = {uint8_t(p & 63), uint8_t((p >> 6) & 7), uint8_t(p >> 9)};
  }
  if (!valid(e, squares, types)) return false;
  entry = e;
  return true;
}

} // namespace Stockfish::MateTableBin

#endif
