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
size_t get_thread_id( const Position& pos );

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
        movelist_buf();
        movelist_buf(int move_count_, int list_count_);
        ~movelist_buf();
        void alloc();
        void dealloc();
        ExtMove* acquire();
        void release(ExtMove* ptr);
    protected:
        ExtMove** ptr_stack = nullptr;
        ExtMove* data = nullptr;
        int top = 0;
        int list_count = 0;
        int move_count = 0;
    };

	inline movelist_buf::movelist_buf() : movelist_buf(MAX_MOVES,64)
	{}

	inline movelist_buf::movelist_buf(int move_count_, int list_count_)
	{
		this->move_count = move_count_;
		this->list_count = list_count_;
	}

	inline movelist_buf::~movelist_buf()
	{
		dealloc();
	}

	inline void movelist_buf::alloc()
	{
		constexpr std::size_t move_size = sizeof(ExtMove);
		constexpr std::size_t move_ptr_size = sizeof(ExtMove*);

		ptr_stack = static_cast<ExtMove**>( malloc(move_ptr_size * list_count) );
		data = static_cast<ExtMove*>( malloc(move_size * move_count * list_count) );

		for (int i = 0; i < (list_count - 1); i++)
		{
			ptr_stack[i] = (ExtMove*)(data + i * move_count);
		}

		ptr_stack[list_count - 1] = nullptr; // The last element is used as a guard value.
	}

	inline void movelist_buf::dealloc()
	{
		if (ptr_stack) { free(ptr_stack); ptr_stack = nullptr; }
		if (data) { free(data); data = nullptr; }
	}

	inline ExtMove* movelist_buf::acquire()
	{
		return ptr_stack[top++];
	}

	inline void movelist_buf::release(ExtMove* ptr)
	{
		ptr_stack[--top] = ptr;
	}

    extern movelist_buf mlb[512];
    extern int mlb_thread_count;

movelist_buf& get_thread_mlb( const Position& pos );

inline void mlb_create( int thread_count )
{
	mlb_thread_count = thread_count;

	for ( int i = 0 ; i < mlb_thread_count ; i++ )
	{
		mlb[i].alloc();
	}
}

inline void mlb_destroy()
{
	for ( int i = 0 ; i < mlb_thread_count ; i++ )
	{
		mlb[i].dealloc();
	}
}

/// The MoveList struct is a simple wrapper around generate(). It sometimes comes
/// in handy to use this class instead of the low level generate() function.
template<GenType T>
struct MoveList {

    explicit MoveList(const Position& pos)
    :mlb_(get_thread_mlb(pos))
    {
        this->moveList = mlb_.acquire();
        this->last = generate<T>(pos, this->moveList);
    }

    ~MoveList()
    {
        mlb_.release(this->moveList);
    }

  const ExtMove* begin() const { return moveList; }
  const ExtMove* end() const { return last; }
  size_t size() const { return last - moveList; }
  bool contains(Move move) const {
    return std::find(begin(), end(), move) != end();
  }

private:
    movelist_buf& mlb_;
    ExtMove* last;
    ExtMove* moveList = nullptr;
};

} // namespace Stockfish

#endif // #ifndef MOVEGEN_H_INCLUDED
