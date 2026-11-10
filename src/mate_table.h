/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#ifndef MATE_TABLE_H_INCLUDED
#define MATE_TABLE_H_INCLUDED

#include <istream>
#include <memory>

namespace Stockfish {

class Position;

// An optional analysis job. No tables or work are added to ordinary search.
class MateTable {
public:
  MateTable();
  ~MateTable();
  void command(std::istream&, const Position&);
  void stop();
  void wait();

private:
  struct Impl;
  std::unique_ptr<Impl> impl;
};

} // namespace Stockfish

#endif
