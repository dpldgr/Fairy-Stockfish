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

#ifndef TYPES_H_INCLUDED
#define TYPES_H_INCLUDED

/// When compiling with provided Makefile (e.g. for Linux and OSX), configuration
/// is done automatically. To get started type 'make help'.
///
/// When Makefile is not used (e.g. with Microsoft Visual Studio) some switches
/// need to be set manually:
///
/// -DNDEBUG      | Disable debugging mode. Always use this for release.
///
/// -DNO_PREFETCH | Disable use of prefetch asm-instruction. You may need this to
///               | run on some very old machines.
///
/// -DUSE_POPCNT  | Add runtime support for use of popcnt asm-instruction. Works
///               | only in 64-bit mode and requires hardware with popcnt support.
///
/// -DUSE_PEXT    | Add runtime support for use of pext asm-instruction. Works
///               | only in 64-bit mode and requires hardware with pext support.

#include <cassert>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <string_view>
#include <type_traits>
#include <algorithm>

#ifndef BOARD_FILES
#define BOARD_FILES 8
#endif
#ifndef BOARD_RANKS
#define BOARD_RANKS 8
#endif
#ifndef BOARD_SQUARES
#define BOARD_SQUARES (BOARD_FILES * BOARD_RANKS)
#endif

#if BOARD_FILES < 8 || BOARD_FILES > 32
#error "BOARD_FILES must be between 8 and 32"
#endif
#if BOARD_RANKS < 8 || BOARD_RANKS > 48
#error "BOARD_RANKS must be between 8 and 48"
#endif
#if BOARD_SQUARES < 64 || BOARD_SQUARES > 384
#error "BOARD_SQUARES must be between 64 and 384"
#endif
#if BOARD_SQUARES > 128
#define BITBOARD_MULTIWORD
#define BITBOARD_WORDS ((BOARD_SQUARES + 63) / 64)
#endif
#if (defined(LARGEBOARDS) && (BOARD_FILES != 12 || BOARD_RANKS != 10))
#error "LARGEBOARDS is a compatibility alias for BOARD_FILES=12 and BOARD_RANKS=10; define BOARD_FILES/BOARD_RANKS instead"
#endif
#if BOARD_SQUARES > 64 && !defined(LARGEBOARDS)
#define LARGEBOARDS
#endif


#if defined(_MSC_VER)
// Disable some silly and noisy warning from MSVC compiler
#pragma warning(disable: 4127) // Conditional expression is constant
#pragma warning(disable: 4146) // Unary minus operator applied to unsigned type
#pragma warning(disable: 4800) // Forcing value to bool 'true' or 'false'
#pragma comment(linker, "/STACK:8000000") // Use 8 MB stack size for MSVC
#pragma comment(lib, "advapi32.lib") // Fix linker error
#endif

/// Predefined macros hell:
///
/// __GNUC__           Compiler is gcc, Clang or Intel on Linux
/// __INTEL_COMPILER   Compiler is Intel
/// _MSC_VER           Compiler is MSVC or Intel on Windows
/// _WIN32             Building on Windows (any)
/// _WIN64             Building on Windows 64 bit

#if defined(__GNUC__ ) && (__GNUC__ < 9 || (__GNUC__ == 9 && __GNUC_MINOR__ <= 2)) && defined(_WIN32) && !defined(__clang__)
#define ALIGNAS_ON_STACK_VARIABLES_BROKEN
#endif

#define ASSERT_ALIGNED(ptr, alignment) assert(reinterpret_cast<uintptr_t>(ptr) % alignment == 0)

#if defined(_WIN64) && defined(_MSC_VER) // No Makefile used
#  include <intrin.h> // Microsoft header for _BitScanForward64()
#  define IS_64BIT
#endif

#if defined(USE_POPCNT) && (defined(__INTEL_COMPILER) || defined(_MSC_VER))
#  include <nmmintrin.h> // Intel and Microsoft header for _mm_popcnt_u64()
#endif

#if !defined(NO_PREFETCH) && (defined(__INTEL_COMPILER) || defined(_MSC_VER))
#  include <xmmintrin.h> // Intel and Microsoft header for _mm_prefetch()
#endif

#if defined(USE_PEXT)
#  include <immintrin.h> // Header for _pext_u64() intrinsic
#  if defined(LARGEBOARDS) && !defined(BITBOARD_MULTIWORD)
#    define pext(b, m) (_pext_u64(b, m) ^ (_pext_u64(b >> 64, m >> 64) << popcount((m << 64) >> 64)))
#  elif !defined(BITBOARD_MULTIWORD)
#    define pext(b, m) _pext_u64(b, m)
#  endif
#endif

namespace Stockfish {

#ifdef USE_POPCNT
constexpr bool HasPopCnt = true;
#else
constexpr bool HasPopCnt = false;
#endif

#ifdef USE_PEXT
constexpr bool HasPext = true;
#else
constexpr bool HasPext = false;
#endif

#ifdef IS_64BIT
constexpr bool Is64Bit = true;
#else
constexpr bool Is64Bit = false;
#endif

typedef uint64_t Key;
#ifdef BITBOARD_MULTIWORD
struct Bitboard {
    uint64_t b64[BITBOARD_WORDS];

    constexpr Bitboard() : b64 {} {}
    constexpr Bitboard(uint64_t i) : b64 {} { b64[BITBOARD_WORDS - 1] = i; }

    template<typename... T>
    constexpr Bitboard(uint64_t first, T... rest) : b64 {} {
        static_assert(1 + sizeof...(rest) <= BITBOARD_WORDS, "Too many words for Bitboard");
        const uint64_t words[] = { first, uint64_t(rest)... };
        constexpr int count = 1 + sizeof...(rest);
        for (int i = 0; i < count; ++i)
            b64[BITBOARD_WORDS - count + i] = words[i];
    }

    constexpr operator bool() const {
        for (int i = 0; i < BITBOARD_WORDS; ++i)
            if (b64[i])
                return true;
        return false;
    }
    constexpr operator long long unsigned () const { return b64[BITBOARD_WORDS - 1]; }
    constexpr operator unsigned() const { return unsigned(b64[BITBOARD_WORDS - 1]); }

    constexpr Bitboard operator << (const unsigned int bits) const {
        Bitboard out;
        if (bits >= BITBOARD_WORDS * 64)
            return out;
        const unsigned word = bits / 64;
        const unsigned rem = bits % 64;
        for (int i = 0; i < BITBOARD_WORDS; ++i)
        {
            const int src = i + word;
            if (src < BITBOARD_WORDS)
                out.b64[i] |= b64[src] << rem;
            if (rem && src + 1 < BITBOARD_WORDS)
                out.b64[i] |= b64[src + 1] >> (64 - rem);
        }
        return out;
    }

    constexpr Bitboard operator >> (const unsigned int bits) const {
        Bitboard out;
        if (bits >= BITBOARD_WORDS * 64)
            return out;
        const unsigned word = bits / 64;
        const unsigned rem = bits % 64;
        for (int i = BITBOARD_WORDS - 1; i >= 0; --i)
        {
            const int src = i - word;
            if (src >= 0)
                out.b64[i] |= b64[src] >> rem;
            if (rem && src - 1 >= 0)
                out.b64[i] |= b64[src - 1] << (64 - rem);
        }
        return out;
    }

    constexpr Bitboard operator << (const int bits) const { return *this << unsigned(bits); }
    constexpr Bitboard operator >> (const int bits) const { return *this >> unsigned(bits); }
    constexpr bool operator == (const Bitboard y) const {
        for (int i = 0; i < BITBOARD_WORDS; ++i)
            if (b64[i] != y.b64[i])
                return false;
        return true;
    }
    constexpr bool operator != (const Bitboard y) const { return !(*this == y); }
    inline Bitboard& operator |=(const Bitboard x) { for (int i = 0; i < BITBOARD_WORDS; ++i) b64[i] |= x.b64[i]; return *this; }
    inline Bitboard& operator &=(const Bitboard x) { for (int i = 0; i < BITBOARD_WORDS; ++i) b64[i] &= x.b64[i]; return *this; }
    inline Bitboard& operator ^=(const Bitboard x) { for (int i = 0; i < BITBOARD_WORDS; ++i) b64[i] ^= x.b64[i]; return *this; }
    constexpr Bitboard operator ~ () const {
        Bitboard out;
        for (int i = 0; i < BITBOARD_WORDS; ++i)
            out.b64[i] = ~b64[i];
        return out;
    }
    constexpr Bitboard operator - () const { return Bitboard(0) - *this; }
    constexpr Bitboard operator | (const Bitboard x) const {
        Bitboard out;
        for (int i = 0; i < BITBOARD_WORDS; ++i)
            out.b64[i] = b64[i] | x.b64[i];
        return out;
    }
    constexpr Bitboard operator & (const Bitboard x) const {
        Bitboard out;
        for (int i = 0; i < BITBOARD_WORDS; ++i)
            out.b64[i] = b64[i] & x.b64[i];
        return out;
    }
    constexpr Bitboard operator ^ (const Bitboard x) const {
        Bitboard out;
        for (int i = 0; i < BITBOARD_WORDS; ++i)
            out.b64[i] = b64[i] ^ x.b64[i];
        return out;
    }
    constexpr Bitboard operator + (const Bitboard x) const {
        Bitboard out;
        uint64_t carry = 0;
        for (int i = BITBOARD_WORDS - 1; i >= 0; --i)
        {
            const uint64_t sum = b64[i] + x.b64[i];
            out.b64[i] = sum + carry;
            carry = (sum < b64[i]) || (carry && out.b64[i] == 0);
        }
        return out;
    }
    constexpr Bitboard operator - (const Bitboard x) const {
        Bitboard out;
        uint64_t borrow = 0;
        for (int i = BITBOARD_WORDS - 1; i >= 0; --i)
        {
            const uint64_t sub = x.b64[i] + borrow;
            out.b64[i] = b64[i] - sub;
            borrow = (b64[i] < x.b64[i]) || (borrow && b64[i] == x.b64[i]);
        }
        return out;
    }
    constexpr Bitboard operator - (const int x) const { return *this - Bitboard(x); }
    constexpr Bitboard operator * (const Bitboard) const { return Bitboard(0); }
};
constexpr int SQUARE_BITS = BOARD_SQUARES <= 256 ? 8 : 9;
#elif defined(LARGEBOARDS)
#if defined(__GNUC__) && defined(IS_64BIT)
typedef unsigned __int128 Bitboard;
#else
struct Bitboard {
    uint64_t b64[2];

    constexpr Bitboard() : b64 {0, 0} {}
    constexpr Bitboard(uint64_t i) : b64 {0, i} {}
    constexpr Bitboard(uint64_t hi, uint64_t lo) : b64 {hi, lo} {};

    constexpr operator bool() const {
        return b64[0] || b64[1];
    }

    constexpr operator long long unsigned () const {
        return b64[1];
    }

    constexpr operator unsigned() const {
        return b64[1];
    }

    constexpr Bitboard operator << (const unsigned int bits) const {
        return Bitboard(  bits >= 64 ? b64[1] << (bits - 64)
                        : bits == 0  ? b64[0]
                        : ((b64[0] << bits) | (b64[1] >> (64 - bits))),
                        bits >= 64 ? 0 : b64[1] << bits);
    }

    constexpr Bitboard operator >> (const unsigned int bits) const {
        return Bitboard(bits >= 64 ? 0 : b64[0] >> bits,
                          bits >= 64 ? b64[0] >> (bits - 64)
                        : bits == 0  ? b64[1]
                        : ((b64[1] >> bits) | (b64[0] << (64 - bits))));
    }

    constexpr Bitboard operator << (const int bits) const {
        return *this << unsigned(bits);
    }

    constexpr Bitboard operator >> (const int bits) const {
        return *this >> unsigned(bits);
    }

    constexpr bool operator == (const Bitboard y) const {
        return (b64[0] == y.b64[0]) && (b64[1] == y.b64[1]);
    }

    constexpr bool operator != (const Bitboard y) const {
        return !(*this == y);
    }

    inline Bitboard& operator |=(const Bitboard x) {
        b64[0] |= x.b64[0];
        b64[1] |= x.b64[1];
        return *this;
    }
    inline Bitboard& operator &=(const Bitboard x) {
        b64[0] &= x.b64[0];
        b64[1] &= x.b64[1];
        return *this;
    }
    inline Bitboard& operator ^=(const Bitboard x) {
        b64[0] ^= x.b64[0];
        b64[1] ^= x.b64[1];
        return *this;
    }

    constexpr Bitboard operator ~ () const {
        return Bitboard(~b64[0], ~b64[1]);
    }

    constexpr Bitboard operator - () const {
        return Bitboard(-b64[0] - (b64[1] > 0), -b64[1]);
    }

    constexpr Bitboard operator | (const Bitboard x) const {
        return Bitboard(b64[0] | x.b64[0], b64[1] | x.b64[1]);
    }

    constexpr Bitboard operator & (const Bitboard x) const {
        return Bitboard(b64[0] & x.b64[0], b64[1] & x.b64[1]);
    }

    constexpr Bitboard operator ^ (const Bitboard x) const {
        return Bitboard(b64[0] ^ x.b64[0], b64[1] ^ x.b64[1]);
    }

    constexpr Bitboard operator - (const Bitboard x) const {
        return Bitboard(b64[0] - x.b64[0] - (b64[1] < x.b64[1]), b64[1] - x.b64[1]);
    }

    constexpr Bitboard operator - (const int x) const {
        return *this - Bitboard(x);
    }

    inline Bitboard operator * (const Bitboard x) const {
        uint64_t a_lo = (uint32_t)b64[1];
        uint64_t a_hi = b64[1] >> 32;
        uint64_t b_lo = (uint32_t)x.b64[1];
        uint64_t b_hi = x.b64[1] >> 32;

        uint64_t t1 = (a_hi * b_lo) + ((a_lo * b_lo) >> 32);
        uint64_t t2 = (a_lo * b_hi) + (t1 & 0xFFFFFFFF);

        return Bitboard(b64[0] * x.b64[1] + b64[1] * x.b64[0] + (a_hi * b_hi) + (t1 >> 32) + (t2 >> 32),
                        (t2 << 32) + (a_lo * b_lo & 0xFFFFFFFF));
   }
};
#endif
constexpr int SQUARE_BITS = 7;
#else
typedef uint64_t Bitboard;
constexpr int SQUARE_BITS = 6;
#endif

inline uint64_t software_pext64(uint64_t b, uint64_t m) {

    uint64_t result = 0;
    unsigned bit = 0;

    while (m)
    {
        const uint64_t lsb = m & -m;
        if (b & lsb)
            result |= uint64_t(1) << bit;
        m ^= lsb;
        ++bit;
    }

    return result;
}

inline unsigned software_popcount64(uint64_t b) {

#if defined(__GNUC__)
    return unsigned(__builtin_popcountll(b));
#else
    unsigned cnt = 0;
    while (b)
    {
        b &= b - 1;
        ++cnt;
    }
    return cnt;
#endif
}

#if defined(BITBOARD_MULTIWORD)
inline unsigned pext(Bitboard b, Bitboard m) {

    unsigned result = 0;
    unsigned shift = 0;

    for (int i = BITBOARD_WORDS - 1; i >= 0; --i)
    {
#if defined(USE_PEXT)
        result ^= unsigned(_pext_u64(b.b64[i], m.b64[i]) << shift);
#else
        result ^= unsigned(software_pext64(b.b64[i], m.b64[i]) << shift);
#endif
        shift += software_popcount64(m.b64[i]);
    }

    return result;
}
#elif !defined(USE_PEXT)
inline unsigned pext(Bitboard b, Bitboard m) {

#ifdef LARGEBOARDS
#if defined(__GNUC__) && defined(IS_64BIT)
    return unsigned(  software_pext64(uint64_t(b), uint64_t(m))
                    ^ (software_pext64(uint64_t(b >> 64), uint64_t(m >> 64)) << software_popcount64(uint64_t(m))));
#else
    return unsigned(  software_pext64(b.b64[1], m.b64[1])
                    ^ (software_pext64(b.b64[0], m.b64[0]) << software_popcount64(m.b64[1])));
#endif
#else
    return unsigned(software_pext64(b, m));
#endif
}
#endif

//When defined, move list will be stored in heap. Delete this if you want to use stack to store move list. Using stack can cause overflow (Segmentation Fault) when the search is too deep.
#define USE_HEAP_INSTEAD_OF_STACK_FOR_MOVE_LIST

#ifdef ALLVARS
constexpr int MAX_MOVES = 8192;
#ifdef USE_HEAP_INSTEAD_OF_STACK_FOR_MOVE_LIST
constexpr int MAX_PLY = 246;
#else
constexpr int MAX_PLY = 60;
#endif
/// endif USE_HEAP_INSTEAD_OF_STACK_FOR_MOVE_LIST
#else
constexpr int MAX_MOVES = 1024;
constexpr int MAX_PLY = 246;
#endif
/// endif ALLVARS

/// A move needs 16 bits to be stored
///
/// bit  0- 5: destination square (from 0 to 63)
/// bit  6-11: origin square (from 0 to 63)
/// bit 12-13: promotion piece type - 2 (from KNIGHT-2 to QUEEN-2)
/// bit 14-15: special move flag: promotion (1), en passant (2), castling (3)
/// NOTE: en passant bit is set only when a pawn can be captured
///
/// Special cases are MOVE_NONE and MOVE_NULL. We can sneak these in because in
/// any normal move destination square is always different from origin square
/// while MOVE_NONE and MOVE_NULL have the same origin and destination square.

using MoveStorage = std::conditional_t<BOARD_SQUARES <= 256, uint32_t, uint64_t>;

enum Move : MoveStorage {
  MOVE_NONE,
  MOVE_NULL = MoveStorage(1) + (MoveStorage(1) << SQUARE_BITS)
};

enum MoveType : MoveStorage {
  NORMAL,
  EN_PASSANT          = MoveStorage(1) << (2 * SQUARE_BITS),
  CASTLING           = MoveStorage(2) << (2 * SQUARE_BITS),
  PROMOTION          = MoveStorage(3) << (2 * SQUARE_BITS),
  DROP               = MoveStorage(4) << (2 * SQUARE_BITS),
  PIECE_PROMOTION    = MoveStorage(5) << (2 * SQUARE_BITS),
  PIECE_DEMOTION     = MoveStorage(6) << (2 * SQUARE_BITS),
  SPECIAL            = MoveStorage(7) << (2 * SQUARE_BITS),
  LION               = MoveStorage(8) << (2 * SQUARE_BITS),
  HOOK               = MoveStorage(9) << (2 * SQUARE_BITS),
  DOUBLE_MOVE        = MoveStorage(10) << (2 * SQUARE_BITS),
};

constexpr int MOVE_TYPE_BITS = 4;

enum Color {
  WHITE, BLACK, COLOR_NB = 2
};

enum CastlingRights {
  NO_CASTLING,
  WHITE_OO,
  WHITE_OOO = WHITE_OO << 1,
  BLACK_OO  = WHITE_OO << 2,
  BLACK_OOO = WHITE_OO << 3,

  KING_SIDE      = WHITE_OO  | BLACK_OO,
  QUEEN_SIDE     = WHITE_OOO | BLACK_OOO,
  WHITE_CASTLING = WHITE_OO  | WHITE_OOO,
  BLACK_CASTLING = BLACK_OO  | BLACK_OOO,
  ANY_CASTLING   = WHITE_CASTLING | BLACK_CASTLING,

  CASTLING_RIGHT_NB = 16
};

enum CheckCount : int {
  CHECKS_0 = 0, CHECKS_NB = 11
};

enum MaterialCounting {
  NO_MATERIAL_COUNTING, JANGGI_MATERIAL, UNWEIGHTED_MATERIAL, WHITE_DRAW_ODDS, BLACK_DRAW_ODDS
};

enum CountingRule {
  NO_COUNTING, MAKRUK_COUNTING, CAMBODIAN_COUNTING, ASEAN_COUNTING
};

enum ChasingRule {
  NO_CHASING, AXF_CHASING
};

enum EnclosingRule {
  NO_ENCLOSING, REVERSI, ATAXX, QUADWRANGLE, SNORT, ANYSIDE, TOP
};

enum WallingRule {
  NO_WALLING, ARROW, DUCK, EDGE, PAST, STATIC
};

enum EndgameEval {
  NO_EG_EVAL, EG_EVAL_CHESS, EG_EVAL_ANTI, EG_EVAL_ATOMIC, EG_EVAL_DUCK, EG_EVAL_MISERE, EG_EVAL_RK, EG_EVAL_NB
};

enum OptBool {
  NO_VALUE, VALUE_FALSE, VALUE_TRUE
};

enum Phase {
  PHASE_ENDGAME,
  PHASE_MIDGAME = 128,
  MG = 0, EG = 1, PHASE_NB = 2
};

enum ScaleFactor {
  SCALE_FACTOR_DRAW    = 0,
  SCALE_FACTOR_NORMAL  = 64,
  SCALE_FACTOR_MAX     = 128,
  SCALE_FACTOR_NONE    = 255
};

enum Bound {
  BOUND_NONE,
  BOUND_UPPER,
  BOUND_LOWER,
  BOUND_EXACT = BOUND_UPPER | BOUND_LOWER
};

enum Value : int {
  VALUE_ZERO      = 0,
  VALUE_DRAW      = 0,
  VALUE_KNOWN_WIN = 10000,
  VALUE_MATE      = 32000,
  XBOARD_VALUE_MATE = 200000,
  VALUE_VIRTUAL_MATE = 3000,
  VALUE_VIRTUAL_MATE_IN_MAX_PLY = VALUE_VIRTUAL_MATE - MAX_PLY,
  VALUE_INFINITE  = 32001,
  VALUE_NONE      = 32002,

  VALUE_TB_WIN_IN_MAX_PLY  =  VALUE_MATE - 2 * MAX_PLY,
  VALUE_TB_LOSS_IN_MAX_PLY = -VALUE_TB_WIN_IN_MAX_PLY,
  VALUE_MATE_IN_MAX_PLY  =  VALUE_MATE - MAX_PLY,
  VALUE_MATED_IN_MAX_PLY = -VALUE_MATE_IN_MAX_PLY,

  PawnValueMg   = 126,   PawnValueEg   = 208,
  KnightValueMg = 781,   KnightValueEg = 854,
  BishopValueMg = 825,   BishopValueEg = 915,
  RookValueMg   = 1276,  RookValueEg   = 1380,
  QueenValueMg  = 2538,  QueenValueEg  = 2682,
  FersValueMg              = 420,   FersValueEg              = 450,
  AlfilValueMg             = 350,   AlfilValueEg             = 330,
  FersAlfilValueMg         = 700,   FersAlfilValueEg         = 650,
  SilverValueMg            = 660,   SilverValueEg            = 640,
  AiwokValueMg             = 2300,  AiwokValueEg             = 2700,
  BersValueMg              = 1800,  BersValueEg              = 1900,
  ArchbishopValueMg        = 2200,  ArchbishopValueEg        = 2200,
  ChancellorValueMg        = 2300,  ChancellorValueEg        = 2600,
  AmazonValueMg            = 2700,  AmazonValueEg            = 2850,
  KnibisValueMg            = 1100,  KnibisValueEg            = 1200,
  BiskniValueMg            = 750,   BiskniValueEg            = 700,
  KnirooValueMg            = 1050,  KnirooValueEg            = 1250,
  RookniValueMg            = 800,   RookniValueEg            = 950,
  ShogiPawnValueMg         =  90,   ShogiPawnValueEg         = 100,
  LanceValueMg             = 400,   LanceValueEg             = 240,
  ShogiKnightValueMg       = 420,   ShogiKnightValueEg       = 290,
  GoldValueMg              = 720,   GoldValueEg              = 700,
  DragonHorseValueMg       = 1550,  DragonHorseValueEg       = 1550,
  ClobberPieceValueMg      = 300,   ClobberPieceValueEg      = 300,
  BreakthroughPieceValueMg = 300,   BreakthroughPieceValueEg = 300,
  ImmobilePieceValueMg     = 50,    ImmobilePieceValueEg     = 50,
  CannonPieceValueMg       = 800,   CannonPieceValueEg       = 700,
  JanggiCannonPieceValueMg = 800,   JanggiCannonPieceValueEg = 600,
  SoldierValueMg           = 200,   SoldierValueEg           = 270,
  HorseValueMg             = 520,   HorseValueEg             = 800,
  ElephantValueMg          = 300,   ElephantValueEg          = 300,
  JanggiElephantValueMg    = 340,   JanggiElephantValueEg    = 350,
  BannerValueMg            = 3400,  BannerValueEg            = 3500,
  WazirValueMg             = 400,   WazirValueEg             = 350,
  CommonerValueMg          = 700,   CommonerValueEg          = 900,
  CentaurValueMg           = 1800,  CentaurValueEg           = 1900,

  MidgameLimit  = 15258, EndgameLimit  = 3915
};

constexpr int PIECE_TYPE_BITS = 6; // PIECE_TYPE_NB = pow(2, PIECE_TYPE_BITS)

enum PieceType {
  NO_PIECE_TYPE, PAWN, KNIGHT, BISHOP, ROOK, QUEEN,
  FERS, MET = FERS, ALFIL, FERS_ALFIL, SILVER, KHON = SILVER, AIWOK, BERS, DRAGON = BERS,
  ARCHBISHOP, CHANCELLOR, AMAZON, KNIBIS, BISKNI, KNIROO, ROOKNI,
  SHOGI_PAWN, LANCE, SHOGI_KNIGHT, GOLD, DRAGON_HORSE,
  CLOBBER_PIECE, BREAKTHROUGH_PIECE, IMMOBILE_PIECE, CANNON, JANGGI_CANNON,
  SOLDIER, HORSE, ELEPHANT, JANGGI_ELEPHANT, BANNER,
  WAZIR, COMMONER, CENTAUR,

  CUSTOM_PIECE_1, CUSTOM_PIECE_2, CUSTOM_PIECE_3, CUSTOM_PIECE_4,
  CUSTOM_PIECE_5, CUSTOM_PIECE_6, CUSTOM_PIECE_7, CUSTOM_PIECE_8,

  PIECE_TYPE_NB = 1 << PIECE_TYPE_BITS,
  KING = PIECE_TYPE_NB - 1,

  // Aliases
  CUSTOM_PIECES = CUSTOM_PIECE_1,
  CUSTOM_PIECES_END = KING - 1,
  CUSTOM_PIECES_ROYAL = CUSTOM_PIECES_END,
  CUSTOM_PIECES_NB = CUSTOM_PIECES_END - CUSTOM_PIECES + 1,
  FAIRY_PIECES = QUEEN + 1,
  FAIRY_PIECES_END = CUSTOM_PIECES - 1,
  ALL_PIECES = 0,
};
static_assert(KING < PIECE_TYPE_NB, "KING exceeds PIECE_TYPE_NB.");
static_assert(PIECE_TYPE_BITS <= 6, "PIECE_TYPE uses more than 6 bit");
static_assert(!(PIECE_TYPE_NB & (PIECE_TYPE_NB - 1)), "PIECE_TYPE_NB is not a power of 2");

static_assert(2 * SQUARE_BITS + MOVE_TYPE_BITS + 2 * PIECE_TYPE_BITS <= 8 * sizeof(MoveStorage), "Move encoding uses more bits than MoveStorage");

enum Piece {
  NO_PIECE,
  W_PAWN = PAWN,                 W_KNIGHT, W_BISHOP, W_ROOK, W_QUEEN, W_KING = KING,
  B_PAWN = PAWN + PIECE_TYPE_NB, B_KNIGHT, B_BISHOP, B_ROOK, B_QUEEN, B_KING = KING + PIECE_TYPE_NB,
  PIECE_NB = 2 * PIECE_TYPE_NB
};

enum PieceSet : uint64_t {
  NO_PIECE_SET = 0,
  CHESS_PIECES = (1ULL << PAWN) | (1ULL << KNIGHT) | (1ULL << BISHOP) | (1ULL << ROOK) | (1ULL << QUEEN) | (1ULL << KING),
  COMMON_FAIRY_PIECES = (1ULL << IMMOBILE_PIECE) | (1ULL << COMMONER) | (1ULL << ARCHBISHOP) | (1ULL << CHANCELLOR),
  SHOGI_PIECES = (1ULL << SHOGI_PAWN) | (1ULL << GOLD) | (1ULL << SILVER) | (1ULL << SHOGI_KNIGHT) | (1ULL << LANCE)
                | (1ULL << DRAGON)| (1ULL << DRAGON_HORSE) | (1ULL << KING),
  COMMON_STEP_PIECES = (1ULL << COMMONER) | (1ULL << FERS) | (1ULL << WAZIR) | (1ULL << BREAKTHROUGH_PIECE),
};

enum RiderType : int {
  NO_RIDER = 0,
  RIDER_BISHOP = 1 << 0,
  RIDER_ROOK_H = 1 << 1,
  RIDER_ROOK_V = 1 << 2,
  RIDER_CANNON_H = 1 << 3,
  RIDER_CANNON_V = 1 << 4,
  RIDER_LAME_DABBABA = 1 << 5,
  RIDER_HORSE = 1 << 6,
  RIDER_ELEPHANT = 1 << 7,
  RIDER_JANGGI_ELEPHANT = 1 << 8,
  RIDER_CANNON_DIAG = 1 << 9,
  RIDER_NIGHTRIDER = 1 << 10,
  RIDER_GRASSHOPPER_H = 1 << 11,
  RIDER_GRASSHOPPER_V = 1 << 12,
  RIDER_GRASSHOPPER_D = 1 << 13,
  HOPPING_RIDERS =  RIDER_CANNON_H | RIDER_CANNON_V | RIDER_CANNON_DIAG
                  | RIDER_GRASSHOPPER_H | RIDER_GRASSHOPPER_V | RIDER_GRASSHOPPER_D,
  LAME_LEAPERS = RIDER_LAME_DABBABA | RIDER_HORSE | RIDER_ELEPHANT | RIDER_JANGGI_ELEPHANT,
  ASYMMETRICAL_RIDERS =  RIDER_HORSE | RIDER_JANGGI_ELEPHANT
                       | RIDER_GRASSHOPPER_H | RIDER_GRASSHOPPER_V | RIDER_GRASSHOPPER_D,
  NON_SLIDING_RIDERS = HOPPING_RIDERS | LAME_LEAPERS | RIDER_NIGHTRIDER,
};

extern Value PieceValue[PHASE_NB][PIECE_NB];
extern Value EvalPieceValue[PHASE_NB][PIECE_NB]; // variant piece values for evaluation
extern Value CapturePieceValue[PHASE_NB][PIECE_NB]; // variant piece values for captures/search

typedef int Depth;

enum : int {
  DEPTH_QS_CHECKS     =  0,
  DEPTH_QS_NO_CHECKS  = -1,
  DEPTH_QS_RECAPTURES = -5,
  DEPTH_QS_MAX        = -32,

  DEPTH_NONE   = -6,

  DEPTH_OFFSET = -7 // value used only for TT entry occupancy check
};

enum Square : int {
  SQ_NONE = BOARD_SQUARES,
  SQUARE_ZERO = 0,
  SQ_MIN = 0,
  SQUARE_NB = BOARD_SQUARES,
  SQUARE_BIT_MASK = (1 << SQUARE_BITS) - 1,
  SQ_MAX = SQUARE_NB - 1,
  SQUARE_NB_CHESS = 64,
  SQUARE_NB_SHOGI = 81
};
enum Direction : int {
  NORTH = BOARD_FILES,
  EAST  =  1,
  SOUTH = -NORTH,
  WEST  = -EAST,

  NORTH_EAST = NORTH + EAST,
  SOUTH_EAST = SOUTH + EAST,
  SOUTH_WEST = SOUTH + WEST,
  NORTH_WEST = NORTH + WEST
};

enum File : int {
  FILE_A = 0, FILE_B = 1, FILE_C = 2, FILE_D = 3, FILE_E = 4, FILE_F = 5, FILE_G = 6, FILE_H = 7, FILE_I = 8, FILE_J = 9, FILE_K = 10, FILE_L = 11, FILE_M = 12, FILE_N = 13, FILE_O = 14, FILE_P = 15, FILE_Q = 16, FILE_R = 17, FILE_S = 18, FILE_T = 19, FILE_U = 20, FILE_V = 21, FILE_W = 22, FILE_X = 23, FILE_Y = 24, FILE_Z = 25, FILE_AA = 26, FILE_AB = 27, FILE_AC = 28, FILE_AD = 29, FILE_AE = 30, FILE_AF = 31,
  FILE_NB = BOARD_FILES,
  FILE_MAX = FILE_NB - 1
};
enum Rank : int {
  RANK_1 = 0, RANK_2 = 1, RANK_3 = 2, RANK_4 = 3, RANK_5 = 4, RANK_6 = 5, RANK_7 = 6, RANK_8 = 7, RANK_9 = 8, RANK_10 = 9, RANK_11 = 10, RANK_12 = 11, RANK_13 = 12, RANK_14 = 13, RANK_15 = 14, RANK_16 = 15, RANK_17 = 16, RANK_18 = 17, RANK_19 = 18, RANK_20 = 19, RANK_21 = 20, RANK_22 = 21, RANK_23 = 22, RANK_24 = 23, RANK_25 = 24, RANK_26 = 25, RANK_27 = 26, RANK_28 = 27, RANK_29 = 28, RANK_30 = 29, RANK_31 = 30, RANK_32 = 31, RANK_33 = 32, RANK_34 = 33, RANK_35 = 34, RANK_36 = 35, RANK_37 = 36, RANK_38 = 37, RANK_39 = 38, RANK_40 = 39, RANK_41 = 40, RANK_42 = 41, RANK_43 = 42, RANK_44 = 43, RANK_45 = 44, RANK_46 = 45, RANK_47 = 46, RANK_48 = 47,
  RANK_NB = BOARD_RANKS,
  RANK_MAX = RANK_NB - 1
};
// Keep track of what a move changes on the board (used by NNUE)
struct DirtyPiece {

  // Number of changed pieces
  int dirty_num;

  // Max 3 pieces can change in one move. A promotion with capture moves
  // both the pawn and the captured piece to SQ_NONE and the piece promoted
  // to from SQ_NONE to the capture square.
  Piece piece[12];
  Piece handPiece[12];
  int handCount[12];

  // From and to squares, which may be SQ_NONE
  Square from[12];
  Square to[12];
};

/// Score enum stores a middlegame and an endgame value in a single integer (enum).
/// The least significant 16 bits are used to store the middlegame value and the
/// upper 16 bits are used to store the endgame value. We have to take care to
/// avoid left-shifting a signed int to avoid undefined behavior.
enum Score : int { SCORE_ZERO };

constexpr Score make_score(int mg, int eg) {
  return Score((int)((unsigned int)eg << 16) + mg);
}

/// Extracting the signed lower and upper 16 bits is not so trivial because
/// according to the standard a simple cast to short is implementation defined
/// and so is a right shift of a signed integer.
inline Value eg_value(Score s) {
  union { uint16_t u; int16_t s; } eg = { uint16_t(unsigned(s + 0x8000) >> 16) };
  return Value(eg.s);
}

inline Value mg_value(Score s) {
  union { uint16_t u; int16_t s; } mg = { uint16_t(unsigned(s)) };
  return Value(mg.s);
}

#define ENABLE_BIT_OPERATORS_ON(T)                                        \
constexpr T operator~ (T d) { return (T)~(int)d; }                        \
constexpr T operator| (T d1, T d2) { return (T)((int)d1 | (int)d2); }     \
constexpr T operator& (T d1, T d2) { return (T)((int)d1 & (int)d2); }     \
constexpr T operator^ (T d1, T d2) { return (T)((int)d1 ^ (int)d2); }     \
inline T& operator|= (T& d1, T d2) { return (T&)((int&)d1 |= (int)d2); }  \
inline T& operator&= (T& d1, T d2) { return (T&)((int&)d1 &= (int)d2); }  \
inline T& operator^= (T& d1, T d2) { return (T&)((int&)d1 ^= (int)d2); }

#define ENABLE_BASE_OPERATORS_ON(T)                                \
constexpr T operator+(T d1, int d2) { return T(int(d1) + d2); }    \
constexpr T operator-(T d1, int d2) { return T(int(d1) - d2); }    \
constexpr T operator-(T d) { return T(-int(d)); }                  \
inline T& operator+=(T& d1, int d2) { return d1 = d1 + d2; }       \
inline T& operator-=(T& d1, int d2) { return d1 = d1 - d2; }

#define ENABLE_INCR_OPERATORS_ON(T)                                \
inline T& operator++(T& d) { return d = T(int(d) + 1); }           \
inline T& operator--(T& d) { return d = T(int(d) - 1); }

#define ENABLE_FULL_OPERATORS_ON(T)                                \
ENABLE_BASE_OPERATORS_ON(T)                                        \
constexpr T operator*(int i, T d) { return T(i * int(d)); }        \
constexpr T operator*(T d, int i) { return T(int(d) * i); }        \
constexpr T operator/(T d, int i) { return T(int(d) / i); }        \
constexpr int operator/(T d1, T d2) { return int(d1) / int(d2); }  \
inline T& operator*=(T& d, int i) { return d = T(int(d) * i); }    \
inline T& operator/=(T& d, int i) { return d = T(int(d) / i); }

ENABLE_FULL_OPERATORS_ON(Value)
ENABLE_FULL_OPERATORS_ON(Direction)

ENABLE_INCR_OPERATORS_ON(Piece)
ENABLE_INCR_OPERATORS_ON(PieceType)
ENABLE_INCR_OPERATORS_ON(Square)
ENABLE_INCR_OPERATORS_ON(File)
ENABLE_INCR_OPERATORS_ON(Rank)
ENABLE_INCR_OPERATORS_ON(CheckCount)

ENABLE_BASE_OPERATORS_ON(Score)

ENABLE_BASE_OPERATORS_ON(PieceType)
ENABLE_BIT_OPERATORS_ON(RiderType)
ENABLE_BASE_OPERATORS_ON(RiderType)

#undef ENABLE_FULL_OPERATORS_ON
#undef ENABLE_INCR_OPERATORS_ON
#undef ENABLE_BASE_OPERATORS_ON
#undef ENABLE_BIT_OPERATORS_ON

constexpr PieceSet piece_set(PieceType pt) {
  return PieceSet(1ULL << pt);
}

constexpr PieceSet operator~ (PieceSet ps) { return (PieceSet)~(uint64_t)ps; }
constexpr PieceSet operator| (PieceSet ps1, PieceSet ps2) { return (PieceSet)((uint64_t)ps1 | (uint64_t)ps2); }
constexpr PieceSet operator| (PieceSet ps, PieceType pt) { return ps | piece_set(pt); }
constexpr PieceSet operator& (PieceSet ps1, PieceSet ps2) { return (PieceSet)((uint64_t)ps1 & (uint64_t)ps2); }
constexpr PieceSet operator& (PieceSet ps, PieceType pt) { return ps & piece_set(pt); }
constexpr PieceSet operator^ (PieceSet ps1, PieceSet ps2) { return (PieceSet)((uint64_t)ps1 ^ (uint64_t)ps2); }
constexpr PieceSet operator^ (PieceSet ps, PieceType pt) { return ps ^ piece_set(pt); }
inline PieceSet& operator|= (PieceSet& ps1, PieceSet ps2) { return (PieceSet&)((uint64_t&)ps1 |= (uint64_t)ps2); }
inline PieceSet& operator|= (PieceSet& ps, PieceType pt) { return ps |= piece_set(pt); }
inline PieceSet& operator&= (PieceSet& ps1, PieceSet ps2) { return (PieceSet&)((uint64_t&)ps1 &= (uint64_t)ps2); }
//inline PieceSet& operator&= (PieceSet& ps, PieceType pt) does not make sense
inline PieceSet& operator^= (PieceSet& ps1, PieceSet ps2) { return (PieceSet&)((uint64_t&)ps1 ^= (uint64_t)ps2); }
inline PieceSet& operator^= (PieceSet& ps, PieceType pt) { return ps ^= piece_set(pt); }

static_assert(piece_set(PAWN) & PAWN);
static_assert(piece_set(KING) & KING);

/// Additional operators to add a Direction to a Square
constexpr Square operator+(Square s, Direction d) { return Square(int(s) + int(d)); }
constexpr Square operator-(Square s, Direction d) { return Square(int(s) - int(d)); }
inline Square& operator+=(Square& s, Direction d) { return s = s + d; }
inline Square& operator-=(Square& s, Direction d) { return s = s - d; }

/// Only declared but not defined. We don't want to multiply two scores due to
/// a very high risk of overflow. So user should explicitly convert to integer.
Score operator*(Score, Score) = delete;

/// Division of a Score must be handled separately for each term
inline Score operator/(Score s, int i) {
  return make_score(mg_value(s) / i, eg_value(s) / i);
}

/// Multiplication of a Score by an integer. We check for overflow in debug mode.
inline Score operator*(Score s, int i) {

  Score result = Score(int(s) * i);

  assert(eg_value(result) == (i * eg_value(s)));
  assert(mg_value(result) == (i * mg_value(s)));
  assert((i == 0) || (result / i) == s);

  return result;
}

/// Multiplication of a Score by a boolean
inline Score operator*(Score s, bool b) {
  return b ? s : SCORE_ZERO;
}

constexpr Color operator~(Color c) {
  return Color(c ^ BLACK); // Toggle color
}

constexpr Square flip_rank(Square s, Rank maxRank = RANK_8) { // Swap A1 <-> A8
  return Square(s + NORTH * (maxRank - 2 * (s / NORTH)));
}

constexpr Square flip_file(Square s, File maxFile = FILE_H) { // Swap A1 <-> H1
  return Square(s + maxFile - 2 * (s % NORTH));
}

constexpr Piece operator~(Piece pc) {
  return Piece(pc ^ PIECE_TYPE_NB);  // Swap color of piece B_KNIGHT <-> W_KNIGHT
}

constexpr CastlingRights operator&(Color c, CastlingRights cr) {
  return CastlingRights((c == WHITE ? WHITE_CASTLING : BLACK_CASTLING) & cr);
}

constexpr Value mate_in(int ply) {
  return VALUE_MATE - ply;
}

constexpr Value mated_in(int ply) {
  return -VALUE_MATE + ply;
}

constexpr Value convert_mate_value(Value v, int ply) {
  return  v ==  VALUE_MATE ? mate_in(ply)
        : v == -VALUE_MATE ? mated_in(ply)
        : v;
}

constexpr Square make_square(File f, Rank r) {
  return Square(r * FILE_NB + f);
}

constexpr bool is_supported_file(File f) {
  return f >= FILE_A && f <= FILE_AF;
}

constexpr bool is_supported_rank(Rank r) {
  return r >= RANK_1 && r <= RANK_48;
}

constexpr bool is_square_literal_file_char(char c) {
  return c >= 'a' && c <= 'z';
}

constexpr bool is_square_literal_rank_char(char c) {
  return c >= '0' && c <= '9';
}

constexpr int file_index_from_string(std::string_view s) {
  int file = -1;

  for (char c : s)
  {
      if (!is_square_literal_file_char(c))
          return -1;

      file = (file + 1) * 26 + (c - 'a');
  }

  return file;
}

constexpr int rank_index_from_string(std::string_view s) {
  if (s.empty())
      return -1;

  int rank = 0;

  for (char c : s)
  {
      if (!is_square_literal_rank_char(c))
          return -1;

      rank = rank * 10 + (c - '0');
  }

  return rank > 0 ? rank - 1 : -1;
}

constexpr Square SQ(File f, Rank r) {
  return is_supported_file(f) && is_supported_rank(r) ? make_square(f, r) : *static_cast<volatile Square*>(nullptr);
}

constexpr Square SQ(std::string_view s) {
  size_t split = 0;

  while (split < s.size() && is_square_literal_file_char(s[split]))
      ++split;

  int f = file_index_from_string(s.substr(0, split));
  int r = rank_index_from_string(s.substr(split));

  return is_supported_file(File(f)) && is_supported_rank(Rank(r)) ? SQ(File(f), Rank(r)) : *static_cast<volatile Square*>(nullptr);
}

constexpr File operator"" _file(const char* s, size_t n) {
  int f = file_index_from_string(std::string_view(s, n));

  return is_supported_file(File(f)) ? File(f) : *static_cast<volatile File*>(nullptr);
}

constexpr File operator"" _file(unsigned long long n) {
  return n >= 1 && n <= unsigned(FILE_AF + 1) ? File(n - 1) : *static_cast<volatile File*>(nullptr);
}

constexpr Rank operator"" _rank(const char* s, size_t n) {
  int r = rank_index_from_string(std::string_view(s, n));

  return is_supported_rank(Rank(r)) ? Rank(r) : *static_cast<volatile Rank*>(nullptr);
}

constexpr Rank operator"" _rank(unsigned long long n) {
  return n >= 1 && n <= unsigned(RANK_48 + 1) ? Rank(n - 1) : *static_cast<volatile Rank*>(nullptr);
}

constexpr Square operator"" _sq(const char* s, size_t n) {
  return SQ(std::string_view(s, n));
}

constexpr bool square_file_rank_range_test() {
  for (int f = FILE_A; f <= FILE_AF; ++f)
      for (int r = RANK_1; r <= RANK_48; ++r)
          if (SQ(File(f), Rank(r)) != make_square(File(f), Rank(r)))
              return false;

  return true;
}

static_assert(square_file_rank_range_test(), "SQ(File, Rank) must cover every supported file/rank pair");
static_assert(SQ("a1") == SQ(FILE_A, RANK_1), "SQ string parser failed for a1");
static_assert(SQ("h8") == SQ(FILE_H, RANK_8), "SQ string parser failed for h8");
static_assert(SQ("j10") == SQ(FILE_J, RANK_10), "SQ string parser failed for j10");
static_assert(SQ("ad12") == SQ(FILE_AD, RANK_12), "SQ string parser failed for ad12");
static_assert(SQ("af48") == SQ(FILE_AF, RANK_48), "SQ string parser failed for af48");
static_assert("a"_file == FILE_A, "file literal failed for a");
static_assert("ad"_file == FILE_AD, "file literal failed for ad");
static_assert(1_file == FILE_A, "numeric file literal failed for 1_file");
static_assert(30_file == FILE_AD, "numeric file literal failed for 30_file");
static_assert("1"_rank == RANK_1, "rank literal failed for 1");
static_assert("12"_rank == RANK_12, "rank literal failed for 12");
static_assert(1_rank == RANK_1, "numeric rank literal failed for 1_rank");
static_assert(12_rank == RANK_12, "numeric rank literal failed for 12_rank");
static_assert("a1"_sq == SQ(FILE_A, RANK_1), "square literal failed for a1");
static_assert("ad12"_sq == SQ(FILE_AD, RANK_12), "square literal failed for ad12");

constexpr Piece make_piece(Color c, PieceType pt) {
  return Piece((c << PIECE_TYPE_BITS) + pt);
}

constexpr PieceType type_of(Piece pc) {
  return PieceType(pc & (PIECE_TYPE_NB - 1));
}

inline Color color_of(Piece pc) {
  assert(pc != NO_PIECE);
  return Color(pc >> PIECE_TYPE_BITS);
}

constexpr bool is_ok(Square s) {
  return s >= SQ_MIN && s <= SQ_MAX;
}

constexpr File file_of(Square s) {
  return File(s % FILE_NB);
}

constexpr Rank rank_of(Square s) {
  return Rank(s / FILE_NB);
}

constexpr Rank relative_rank(Color c, Rank r, Rank maxRank = RANK_8) {
  return Rank(c == WHITE ? r : maxRank - r);
}

constexpr Rank relative_rank(Color c, Square s, Rank maxRank = RANK_8) {
  return relative_rank(c, rank_of(s), maxRank);
}

constexpr Square relative_square(Color c, Square s, Rank maxRank = RANK_8) {
  return make_square(file_of(s), relative_rank(c, s, maxRank));
}

constexpr Direction pawn_push(Color c) {
  return c == WHITE ? NORTH : SOUTH;
}

constexpr MoveType type_of(Move m) {
  return MoveType(m & (15 << (2 * SQUARE_BITS)));
}

constexpr Square to_sq(Move m) {
  return Square(m & SQUARE_BIT_MASK);
}

constexpr Square from_sq(Move m) {
  return type_of(m) == DROP ? SQ_NONE : Square((m >> SQUARE_BITS) & SQUARE_BIT_MASK);
}

inline int from_to(Move m) {
 return to_sq(m) + (from_sq(m) << SQUARE_BITS);
}

inline PieceType promotion_type(Move m) {
  return type_of(m) == PROMOTION ? PieceType((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS)) & (PIECE_TYPE_NB - 1)) : NO_PIECE_TYPE;
}

inline PieceType gating_type(Move m) {
  return PieceType((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS)) & (PIECE_TYPE_NB - 1));
}

inline Square gating_square(Move m) {
  return Square((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS + PIECE_TYPE_BITS)) & SQUARE_BIT_MASK);
}

inline int lion_path_index(Move m) {
  return (m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS)) & 63;
}

inline Square hook_sq(Move m) {
  return Square((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS)) & SQUARE_BIT_MASK);
}

inline Square double_move_sq(Move m) {
  return Square((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS)) & SQUARE_BIT_MASK);
}

inline bool is_gating(Move m) {
  return gating_type(m) && (type_of(m) == NORMAL || type_of(m) == CASTLING);
}

inline bool is_pass(Move m) {
  return type_of(m) == SPECIAL && from_sq(m) == to_sq(m);
}

constexpr Move make_move(Square from, Square to) {
  return Move((MoveStorage(from) << SQUARE_BITS) + MoveStorage(to));
}

template<MoveType T>
inline Move make(Square from, Square to, PieceType pt = NO_PIECE_TYPE) {
  return Move((MoveStorage(pt) << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + MoveStorage(T) + (MoveStorage(from) << SQUARE_BITS) + MoveStorage(to));
}

constexpr Move make_drop(Square to, PieceType pt_in_hand, PieceType pt_dropped) {
  return Move((MoveStorage(pt_in_hand) << (2 * SQUARE_BITS + MOVE_TYPE_BITS + PIECE_TYPE_BITS)) + (MoveStorage(pt_dropped) << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + MoveStorage(DROP) + MoveStorage(to));
}

constexpr Move reverse_move(Move m) {
  return make_move(to_sq(m), from_sq(m));
}

template<MoveType T>
constexpr Move make_gating(Square from, Square to, PieceType pt, Square gate) {
  return Move((MoveStorage(gate) << (2 * SQUARE_BITS + MOVE_TYPE_BITS + PIECE_TYPE_BITS)) + (MoveStorage(pt) << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + MoveStorage(T) + (MoveStorage(from) << SQUARE_BITS) + MoveStorage(to));
}

constexpr Move make_lion(Square from, int path, Square to) {
  return Move((MoveStorage(path) << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + MoveStorage(LION) + (MoveStorage(from) << SQUARE_BITS) + MoveStorage(to));
}

constexpr Move make_hook(Square from, Square hook, Square to) {
  return Move((MoveStorage(hook) << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + MoveStorage(HOOK) + (MoveStorage(from) << SQUARE_BITS) + MoveStorage(to));
}

constexpr Move make_double_move(Square from, Square intermediate, Square to) {
  return Move((MoveStorage(intermediate) << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + MoveStorage(DOUBLE_MOVE) + (MoveStorage(from) << SQUARE_BITS) + MoveStorage(to));
}

constexpr PieceType dropped_piece_type(Move m) {
  return PieceType((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS)) & (PIECE_TYPE_NB - 1));
}

constexpr PieceType in_hand_piece_type(Move m) {
  return PieceType((m >> (2 * SQUARE_BITS + MOVE_TYPE_BITS + PIECE_TYPE_BITS)) & (PIECE_TYPE_NB - 1));
}

inline bool is_custom(PieceType pt) {
  return pt >= CUSTOM_PIECES && pt <= CUSTOM_PIECES_END;
}

inline bool is_ok(Move m) {
  return from_sq(m) != to_sq(m) || type_of(m) == PROMOTION || type_of(m) == SPECIAL; // Catch MOVE_NULL and MOVE_NONE
}

inline int dist(Direction d) {
  return std::abs(d % NORTH) < NORTH / 2 ? std::max(std::abs(d / NORTH), int(std::abs(d % NORTH)))
      : std::max(std::abs(d / NORTH) + 1, int(NORTH - std::abs(d % NORTH)));
}

/// Based on a congruential pseudo random number generator
constexpr Key make_key(uint64_t seed) {
  return seed * 6364136223846793005ULL + 1442695040888963407ULL;
}

} // namespace Stockfish

#endif // #ifndef TYPES_H_INCLUDED

#include "tune.h" // Global visibility to tuning setup
