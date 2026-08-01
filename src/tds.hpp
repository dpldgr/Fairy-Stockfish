/*
  Fairy-Stockfish, a UCI chess playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  Fairy-Stockfish is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#ifndef TDS_H_INCLUDED
#define TDS_H_INCLUDED

namespace Stockfish {

class Position;

namespace TDS {

// Start an exact, fixed-depth minimax whose ready nodes are scheduled through
// a shared transposition table. The call is asynchronous, like ordinary "go".
void start(const Position&, int depth);

// Wait for an outstanding TDS search. Setting Threads.stop asks it to finish.
void wait();

} // namespace TDS
} // namespace Stockfish

#endif // #ifndef TDS_H_INCLUDED
