/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#ifndef MATE_TABLE_EXPORT_H_INCLUDED
#define MATE_TABLE_EXPORT_H_INCLUDED

#include <array>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>

#include "mate_table_bin.h"
#include "types.h"

namespace Stockfish {
class Variant;

namespace MateTableExport {

// Optional append-only training output; independent of search and table storage.
class Writer {
public:
  ~Writer();
  bool open(const Variant*, const std::vector<PieceType>&, const std::vector<Color>&,
            const std::string& path, unsigned entrySize, std::string& error);
  bool write(const MateTableBin::Entry&, std::string& error);
  bool finish(std::string& error);
  MateTableBin::Entry prototype() const { return material; }
  uint64_t records() const { return confirmed + used / size; }
  unsigned entry_size() const { return size; }
  const std::string& filename() const { return path; }

private:
  bool flush(std::string& error);
  bool fail(const std::string& reason, std::string& error);
  void pack72(const MateTableBin::Entry&, uint8_t*) const;
  std::string path;
  unsigned size = 72, cells = 0, files = 0, typeCount = 0;
  std::FILE* file = nullptr;
  std::unique_ptr<uint8_t[]> buffer;
  size_t used = 0;
  uint64_t initialBytes = 0, confirmed = 0;
  MateTableBin::Entry material;
};

} // namespace MateTableExport
} // namespace Stockfish

#endif
