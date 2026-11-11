// Standalone codec checks; no engine or trainer dependency.
#include "../src/mate_table_bin.h"
#include <cassert>
#include <iostream>
#include <random>

using namespace Stockfish::MateTableBin;

int main() {
  std::array<uint8_t, 8> bytes{};
  Entry e;
  e.kings = {0, 63};
  e.count = 3; e.turn = 1; e.score = -32000; e.result = -1;
  e.pieces = {{{1, 0, 0}, {62, 7, 1}, {31, 4, 0}}};
  assert(encode8(e, bytes.data(), 64, 8));
  // Independent fixed little-endian encoding of all 63 used bits.
  const std::array<uint8_t, 8> expected = {0xc0, 0x1f, 0x80, 0xff, 0x1f, 0x1d, 0x60, 0x10};
  assert(bytes == expected);
  Entry decoded;
  assert(decode8(bytes.data(), decoded, 64, 8));
  assert(decoded.score == -32000 && decoded.result == -1 && decoded.count == 3);
  assert(decoded.pieces[1].square == 62 && decoded.pieces[1].type == 7 && decoded.pieces[1].color == 1);
  bytes[7] |= 0x80;
  assert(!decode8(bytes.data(), decoded, 64, 8)); // Reserved bit.
  bytes[7] = 0x70;
  assert(!decode8(bytes.data(), decoded, 64, 8)); // Reserved result code.
  assert(!encode8(e, bytes.data(), 64, 7));
  assert(!encode8(e, bytes.data(), 63, 8));
  e.pieces[1].square = 1;
  assert(!encode8(e, bytes.data(), 64, 8));
  e.count = 4;
  assert(!encode8(e, bytes.data(), 64, 8));

  std::mt19937 rng(28481);
  for (unsigned sample = 0; sample < 10000; ++sample)
  {
      e = Entry{};
      e.count = uint8_t(sample % 4);
      e.turn = uint8_t(sample % 2);
      e.score = int16_t(int(rng() % 65536) - 32768);
      e.result = int8_t(int(sample % 3) - 1);
      std::array<unsigned, 5> places{};
      uint64_t used = 0;
      for (unsigned i = 0; i < e.count + 2u; ++i)
      {
          unsigned sq;
          do { sq = rng() % 64; } while (used & (uint64_t(1) << sq));
          used |= uint64_t(1) << sq;
          places[i] = sq;
      }
      e.kings = {uint8_t(places[0]), uint8_t(places[1])};
      for (unsigned i = 0; i < e.count; ++i)
          e.pieces[i] = {uint8_t(places[i + 2]), uint8_t(rng() % 8), uint8_t(rng() % 2)};
      assert(encode8(e, bytes.data(), 64, 8));
      assert(decode8(bytes.data(), decoded, 64, 8));
      assert(e.kings == decoded.kings && e.count == decoded.count && e.turn == decoded.turn);
      assert(e.score == decoded.score && e.result == decoded.result);
      for (unsigned i = 0; i < e.count; ++i)
          assert(e.pieces[i].square == decoded.pieces[i].square && e.pieces[i].type == decoded.pieces[i].type
                 && e.pieces[i].color == decoded.pieces[i].color);
  }
  e = Entry{}; e.kings = {0, 63};
  assert(encode8(e, bytes.data(), 64, 8));
  bytes[2] |= 1;
  assert(!decode8(bytes.data(), decoded, 64, 8)); // Nonzero unused support word.
  std::cout << "compact codec: golden record, malformed records and 10000 round trips PASS\n";
}
