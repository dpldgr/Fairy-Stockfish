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

#include "types.h"

namespace Stockfish {

class Position;
class movelist_buf;

movelist_buf* get_thread_mlb( const Position& pos );

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

template<typename T>
T* alloc(size_t count)
{
   return static_cast<T*>( malloc(sizeof(T)*count) );
}

template<typename T>
T* alloc(size_t count1, size_t count2)
{
   return static_cast<T*>( malloc(sizeof(T)*count1*count2) );
}

template<GenType>
ExtMove* generate(const Position& pos, ExtMove* moveList);

    class movelist_buf
    {
    public:
        movelist_buf() : movelist_buf(64) {}
        movelist_buf(const int list_cnt) { list_count = list_cnt;  }

        static void mlb_init( const size_t thread_cnt );
        static void mlb_shutdown();

        void init()
        {
            ptr_stack = alloc<ExtMove*>(list_count);
            data = alloc<ExtMove>(move_count, list_count);

            for (int i = 0; i < (list_count - 1); i++)
            {
                ptr_stack[i] = (ExtMove*)(data + i * move_count);
            }

            ptr_stack[list_count - 1] = nullptr; // The last element is used as a guard value.
        }

        void shutdown()
        {
            if (ptr_stack) { free(ptr_stack); ptr_stack = nullptr; }
            if (data) { free(data); data = nullptr; }
        }

        ~movelist_buf()
        {
            if (ptr_stack) free(ptr_stack);
            if (data) free(data);
        }

        void reinit()
        {
            if (ptr_stack) free(ptr_stack);
            if (data) free(data);

            ptr_stack = alloc<ExtMove*>(list_count);
            data = alloc<ExtMove>(move_count, list_count);

            for (int i = 0; i < (list_count - 1); i++)
            {
                ptr_stack[i] = (ExtMove*)(data + i * move_count);
            }

            ptr_stack[list_count - 1] = nullptr; // The last element is used as a guard value.
        }

        ExtMove* acquire()
        {
            return ptr_stack[top++];
        }

        void release(ExtMove* ptr)
        {
            ptr_stack[--top] = ptr;
        }

        static int thread_count;
        static int move_count;
        static int list_count;

        ExtMove** ptr_stack = nullptr;
        ExtMove* data = nullptr;
        int top = 0;
    };

	extern movelist_buf mlb_pool[MAX_THREADS];

/// The MoveList struct is a simple wrapper around generate(). It sometimes comes
/// in handy to use this class instead of the low level generate() function.
template<GenType T>
struct MoveList {

  explicit MoveList(const Position& pos)
  {
    //this->mlb = get_thread_mlb(pos);
    this->mlb = pos.get_mlb();
    this->moveList = this->mlb->acquire();
    this->last = generate<T>(pos, this->moveList);
  }

  ~MoveList()
  {
    this->mlb->release(this->moveList);
  }

  const ExtMove* begin() const { return moveList; }
  const ExtMove* end() const { return last; }
  size_t size() const { return last - moveList; }
  bool contains(Move move) const {
    return std::find(begin(), end(), move) != end();
  }

private:
    movelist_buf* mlb;
    ExtMove* last;
    ExtMove* moveList = nullptr;
};

} // namespace Stockfish


#endif // #ifndef MOVEGEN_H_INCLUDED
