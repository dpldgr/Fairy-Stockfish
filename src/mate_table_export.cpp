/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#include "mate_table_export.h"

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <new>
#include <system_error>

#include "bitboard.h"
#include "variant.h"

namespace Stockfish::MateTableExport {

namespace {
constexpr size_t BufferRecords = 8192;

void bits(uint8_t* out, unsigned at, unsigned value, unsigned width) {
  for (unsigned i = 0; i < width; ++i)
      if ((value >> i) & 1) out[(at + i) / 8] |= uint8_t(1 << ((at + i) % 8));
}
}

Writer::~Writer() { if (file) std::fclose(file); }

bool Writer::open(const Variant* v, const std::vector<PieceType>& types,
                  const std::vector<Color>& owners, const std::string& filename,
                  unsigned entrySize, std::string& error) {
  if (file || !path.empty()) { error = "export writer already opened"; return false; }
  if (entrySize < 7 || entrySize > 144) { error = "entrysize must be 7..144"; return false; }
  size = entrySize;
  files = unsigned(v->maxFile) + 1;
  cells = files * (unsigned(v->maxRank) + 1);
  if (size == 72 && cells > 128)
  { error = "export board exceeds 128 cells for entrysize 72"; return false; }
  if (size == 72 && v->nnueKing != KING)
  { error = "72-byte export requires the variant's unique NNUE King"; return false; }
  if (types.size() > 3 || types.size() != owners.size())
  { error = "export requires zero to three supporting pieces"; return false; }
  std::array<unsigned, PIECE_TYPE_NB> index{};
  for (PieceSet ps = v->pieceTypes & ~piece_set(KING); ps;)
      index[pop_lsb(ps)] = typeCount++;
  if (size == 72 && typeCount > 16)
  { error = "export variant exceeds 16 non-king piece types"; return false; }
  material.count = uint8_t(types.size());
  for (size_t i = 0; i < types.size(); ++i)
      material.pieces[i] = {0, uint16_t(index[types[i]]), uint8_t(owners[i])};
  // The upstream payload includes zero hand counts for ALL configured types.
  unsigned payloadBits = cells + 41 + 5 * material.count + 10 * (typeCount + 1);
  if (size == 72 && payloadBits > 512)
  { error = "72-byte export packed position exceeds 512 bits"; return false; }
  if (size != 72)
  {
      if (!compact.reset(cells, typeCount, size, error)) return false;
      if (!compact.can_fit(unsigned(types.size())))
      { error = "requested material does not fit entrysize " + std::to_string(size); return false; }
      compactEntry.pieces.resize(types.size());
  }

  std::error_code ec;
  bool exists = std::filesystem::exists(filename, ec);
  if (ec) { error = "cannot inspect export file: " + ec.message(); return false; }
  if (exists)
  {
      if (!std::filesystem::is_regular_file(filename, ec) || ec)
      { error = "export destination must be a regular file"; return false; }
      initialBytes = std::filesystem::file_size(filename, ec);
      if (ec) { error = "cannot read export file size: " + ec.message(); return false; }
      if (initialBytes % size)
      { error = "export file size is not a multiple of entrysize " + std::to_string(size); return false; }
  }
  buffer.reset(new (std::nothrow) uint8_t[BufferRecords * size]);
  if (!buffer) { error = "export buffer allocation failed"; return false; }
  file = std::fopen(filename.c_str(), "ab");
  if (!file) { error = "cannot open export file: " + filename; return false; }
  // Buffer complete records ourselves, so partial writes have an exact boundary.
  if (std::setvbuf(file, nullptr, _IONBF, 0))
  { std::fclose(file); file = nullptr; error = "cannot configure export stream"; return false; }
  path = filename;
  return true;
}

void Writer::pack72(const MateTableBin::Entry& e, uint8_t* out) const {
  std::memset(out, 0, 72);
  bits(out, 0, e.turn, 1);
  bits(out, 1, e.kings[0], 7);
  bits(out, 8, e.kings[1], 7);
  auto scan = [&](unsigned sq) { return (cells / files - 1 - sq / files) * files + sq % files; };
  unsigned king0 = scan(e.kings[0]), king1 = scan(e.kings[1]);
  for (unsigned i = 0; i < e.count; ++i)
  {
      const auto& p = e.pieces[i];
      unsigned square = scan(p.square), preceding = 0;
      for (unsigned j = 0; j < e.count; ++j) preceding += scan(e.pieces[j].square) < square;
      unsigned at = 15 + square - (king0 < square) - (king1 < square) + 5 * preceding;
      bits(out, at, 2 * p.type + 1, 5);
      bits(out, at + 5, p.color, 1);
  }
  unsigned fullmove = 15 + cells - 2 + 5 * e.count + 10 * (typeCount + 1) + 4 + 1 + 6;
  bits(out, fullmove, 1, 16); // Fullmove 1, rule50 0, no rights or EP square.
  out[64] = uint8_t(uint16_t(e.score));
  out[65] = uint8_t(uint16_t(e.score) >> 8);
  // MOVE_NONE=0. This field is unused by the value-training loader.
  out[68] = 1; // Placeholder gamePly, following variant-nnue-tools.
  out[70] = uint8_t(e.result);
}

bool Writer::write(const MateTableBin::Entry& entry, std::string& error) {
  if (!file) { error = "export stream is closed"; return false; }
  if (entry.count != material.count || entry.count > 3)
  { error = "invalid export support count"; return false; }
  // Canonical support order makes the bytes independent of input material order.
  auto e = entry;
  auto less = [](const auto& a, const auto& b) {
      return a.color != b.color ? a.color < b.color : a.type != b.type ? a.type < b.type : a.square < b.square;
  };
  for (unsigned i = 1; i < e.count; ++i)
      for (unsigned j = i; j && less(e.pieces[j], e.pieces[j - 1]); --j)
          std::swap(e.pieces[j], e.pieces[j - 1]);
  if (size == 8 && cells <= 64 && typeCount <= 8)
  {
      if (!MateTableBin::encode8(e, buffer.get() + used, cells, typeCount))
      { error = "invalid compact export record"; return false; }
  }
  else if (size == 72) pack72(e, buffer.get() + used);
  else
  {
      compactEntry.kings = {e.kings[0], e.kings[1]};
      compactEntry.turn = e.turn; compactEntry.score = e.score; compactEntry.result = e.result;
      for (unsigned i = 0; i < e.count; ++i)
          compactEntry.pieces[i] = {e.pieces[i].square, e.pieces[i].type, e.pieces[i].color};
      if (!compact.encode(compactEntry, buffer.get() + used, error)) return false;
  }
  used += size;
  return used < BufferRecords * size || flush(error);
}

bool Writer::fail(const std::string& reason, std::string& error) {
  if (file) { std::fclose(file); file = nullptr; }
  std::error_code ec;
  std::filesystem::resize_file(path, initialBytes + confirmed * size, ec);
  used = 0;
  error = reason;
  if (ec) error += "; could not restore complete-record boundary: " + ec.message();
  return false;
}

bool Writer::flush(std::string& error) {
  if (!used) return true;
  size_t written = std::fwrite(buffer.get(), 1, used, file);
  confirmed += written / size;
  if (written != used) return fail("export write failed", error);
  used = 0;
  return true;
}

bool Writer::finish(std::string& error) {
  if (!file) { error = "export stream is closed"; return false; }
  if (!flush(error)) return false;
  int result = std::fclose(file);
  file = nullptr;
  return result == 0 || fail("export close failed", error);
}

} // namespace Stockfish::MateTableExport
