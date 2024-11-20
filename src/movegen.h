/*
  Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  Copyright (C) 2004-2022 The Stockfish developers (see AUTHORS file)

  Stockfish is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  Stockfish is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#ifndef MOVEGEN_H_INCLUDED
#define MOVEGEN_H_INCLUDED

#include <algorithm>
#include <iostream>

#include "types.h"

namespace Stockfish {

class Position;

enum GenType {
  CAPTURES,
  QUIETS,
  QUIET_CHECKS,
  EVASIONS,
  NON_EVASIONS,
  LEGAL
};

struct ExtMove {
  Move move;
  int value;

  operator Move() const { return move; }
  void operator=(Move m) { move = m; }

  // Inhibit unwanted implicit conversions to Move
  // with an ambiguity that yields to a compile error.
  operator float() const = delete;
};

inline bool operator<(const ExtMove& f, const ExtMove& s) {
  return f.value < s.value;
}

template<GenType>
ExtMove* generate(const Position& pos, ExtMove* moveList);

    class movelist_buf
    {
    public:
        movelist_buf(int move_count_, int list_count_)
        {
            this->move_count = move_count_;
            this->list_count = list_count_;

            constexpr std::size_t move_size = sizeof(ExtMove);
            const std::size_t list_size = move_size * move_count;
            const std::size_t malloc_size = list_size * list_count;

            header = (ExtMove**)malloc(sizeof(ExtMove*) * (list_count + 1) ); // One extra slot for a nullptr guard.
            data = (ExtMove*)malloc(malloc_size);

            for (int i = 0; i < list_count; i++)
            {
                header[i] = (ExtMove*)(data + i * move_count);
            }

            header[list_count] = nullptr; // Guard value, this is how we tell that we've run out of stack memory.
        }

        ~movelist_buf()
        {
            if (header) free(header);
            if (data) free(data);
        }

        void resize(const int move_count_, int list_count_)
        {
            this->move_count = move_count_;
            this->list_count = list_count_;

            constexpr std::size_t move_size = sizeof(ExtMove);
            const std::size_t list_size = move_size * move_count;
            const std::size_t malloc_size = list_size * list_count;

            if (header) free(header);
            if (data) free(data);

            header = (ExtMove**)malloc(sizeof(ExtMove*) * (list_count + 1) ); // One extra slot for a nullptr guard.
            data = (ExtMove*)malloc(malloc_size);

            for (int i = 0; i < list_count; i++)
            {
                header[i] = (ExtMove*)(data + i * move_count);
            }

            header[list_count] = nullptr; // Guard value, this is how we tell that we've run out of stack memory.
        }

        ExtMove* acquire()
        {
            return header[top++];
        }

        void release(ExtMove* ptr)
        {
            header[--top] = ptr;
        }

        ExtMove** header = nullptr;
        ExtMove* data = nullptr;
        int top = 0;
        int list_count = 0;
        int move_count = 0;
    };

	extern movelist_buf mlb;
	extern movelist_buf mpb;

constexpr size_t moveListSize = sizeof(ExtMove) * MAX_MOVES;

/// The MoveList struct is a simple wrapper around generate(). It sometimes comes
/// in handy to use this class instead of the low level generate() function.
template<GenType T>
struct MoveList {


#ifdef USE_HEAP_INSTEAD_OF_STACK_FOR_MOVE_LIST
    explicit MoveList(const Position& pos)
    {
        this->moveList = mlb.acquire();
        this->last = generate<T>(pos, this->moveList);
    }

    ~MoveList()
    {
		mlb.release(this->moveList);
    }
#else
    explicit MoveList(const Position& pos) : last(generate<T>(pos, moveList))
    {
        ;
    }
#endif

  const ExtMove* begin() const { return moveList; }
  const ExtMove* end() const { return last; }
  size_t size() const { return last - moveList; }
  bool contains(Move move) const {
    return std::find(begin(), end(), move) != end();
  }

private:
    ExtMove* last;
#ifdef USE_HEAP_INSTEAD_OF_STACK_FOR_MOVE_LIST
    ExtMove* moveList = 0;
#else
    ExtMove moveList[MAX_MOVES];
#endif
};

} // namespace Stockfish

#endif // #ifndef MOVEGEN_H_INCLUDED
