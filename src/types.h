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
constexpr int SQUARE_BITS = 9;
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

enum Move : uint64_t {
  MOVE_NONE,
  MOVE_NULL = 1 + (1 << SQUARE_BITS)
};

enum MoveType : uint64_t {
  NORMAL,
  EN_PASSANT          = 1 << (2 * SQUARE_BITS),
  CASTLING           = 2 << (2 * SQUARE_BITS),
  PROMOTION          = 3 << (2 * SQUARE_BITS),
  DROP               = 4 << (2 * SQUARE_BITS),
  PIECE_PROMOTION    = 5 << (2 * SQUARE_BITS),
  PIECE_DEMOTION     = 6 << (2 * SQUARE_BITS),
  SPECIAL            = 7 << (2 * SQUARE_BITS),
  LION               = 8 << (2 * SQUARE_BITS),
  HOOK               = 9 << (2 * SQUARE_BITS),
  DOUBLE_MOVE        = 10 << (2 * SQUARE_BITS),
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

static_assert(2 * SQUARE_BITS + MOVE_TYPE_BITS + 2 * PIECE_TYPE_BITS <= 64, "Move encoding uses more than 64 bits");

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
  SQ_A1 = 0 * BOARD_FILES + 0,     SQ_B1 = 0 * BOARD_FILES + 1,     SQ_C1 = 0 * BOARD_FILES + 2,     SQ_D1 = 0 * BOARD_FILES + 3,
  SQ_E1 = 0 * BOARD_FILES + 4,     SQ_F1 = 0 * BOARD_FILES + 5,     SQ_G1 = 0 * BOARD_FILES + 6,     SQ_H1 = 0 * BOARD_FILES + 7,
  SQ_I1 = 0 * BOARD_FILES + 8,     SQ_J1 = 0 * BOARD_FILES + 9,     SQ_K1 = 0 * BOARD_FILES + 10,     SQ_L1 = 0 * BOARD_FILES + 11,
  SQ_M1 = 0 * BOARD_FILES + 12,     SQ_N1 = 0 * BOARD_FILES + 13,     SQ_O1 = 0 * BOARD_FILES + 14,     SQ_P1 = 0 * BOARD_FILES + 15,
  SQ_Q1 = 0 * BOARD_FILES + 16,     SQ_R1 = 0 * BOARD_FILES + 17,     SQ_S1 = 0 * BOARD_FILES + 18,     SQ_T1 = 0 * BOARD_FILES + 19,
  SQ_U1 = 0 * BOARD_FILES + 20,     SQ_V1 = 0 * BOARD_FILES + 21,     SQ_W1 = 0 * BOARD_FILES + 22,     SQ_X1 = 0 * BOARD_FILES + 23,
  SQ_Y1 = 0 * BOARD_FILES + 24,     SQ_Z1 = 0 * BOARD_FILES + 25,     SQ_AA1 = 0 * BOARD_FILES + 26,     SQ_AB1 = 0 * BOARD_FILES + 27,
  SQ_AC1 = 0 * BOARD_FILES + 28,     SQ_AD1 = 0 * BOARD_FILES + 29,     SQ_AE1 = 0 * BOARD_FILES + 30,     SQ_AF1 = 0 * BOARD_FILES + 31,
  SQ_A2 = 1 * BOARD_FILES + 0,     SQ_B2 = 1 * BOARD_FILES + 1,     SQ_C2 = 1 * BOARD_FILES + 2,     SQ_D2 = 1 * BOARD_FILES + 3,
  SQ_E2 = 1 * BOARD_FILES + 4,     SQ_F2 = 1 * BOARD_FILES + 5,     SQ_G2 = 1 * BOARD_FILES + 6,     SQ_H2 = 1 * BOARD_FILES + 7,
  SQ_I2 = 1 * BOARD_FILES + 8,     SQ_J2 = 1 * BOARD_FILES + 9,     SQ_K2 = 1 * BOARD_FILES + 10,     SQ_L2 = 1 * BOARD_FILES + 11,
  SQ_M2 = 1 * BOARD_FILES + 12,     SQ_N2 = 1 * BOARD_FILES + 13,     SQ_O2 = 1 * BOARD_FILES + 14,     SQ_P2 = 1 * BOARD_FILES + 15,
  SQ_Q2 = 1 * BOARD_FILES + 16,     SQ_R2 = 1 * BOARD_FILES + 17,     SQ_S2 = 1 * BOARD_FILES + 18,     SQ_T2 = 1 * BOARD_FILES + 19,
  SQ_U2 = 1 * BOARD_FILES + 20,     SQ_V2 = 1 * BOARD_FILES + 21,     SQ_W2 = 1 * BOARD_FILES + 22,     SQ_X2 = 1 * BOARD_FILES + 23,
  SQ_Y2 = 1 * BOARD_FILES + 24,     SQ_Z2 = 1 * BOARD_FILES + 25,     SQ_AA2 = 1 * BOARD_FILES + 26,     SQ_AB2 = 1 * BOARD_FILES + 27,
  SQ_AC2 = 1 * BOARD_FILES + 28,     SQ_AD2 = 1 * BOARD_FILES + 29,     SQ_AE2 = 1 * BOARD_FILES + 30,     SQ_AF2 = 1 * BOARD_FILES + 31,
  SQ_A3 = 2 * BOARD_FILES + 0,     SQ_B3 = 2 * BOARD_FILES + 1,     SQ_C3 = 2 * BOARD_FILES + 2,     SQ_D3 = 2 * BOARD_FILES + 3,
  SQ_E3 = 2 * BOARD_FILES + 4,     SQ_F3 = 2 * BOARD_FILES + 5,     SQ_G3 = 2 * BOARD_FILES + 6,     SQ_H3 = 2 * BOARD_FILES + 7,
  SQ_I3 = 2 * BOARD_FILES + 8,     SQ_J3 = 2 * BOARD_FILES + 9,     SQ_K3 = 2 * BOARD_FILES + 10,     SQ_L3 = 2 * BOARD_FILES + 11,
  SQ_M3 = 2 * BOARD_FILES + 12,     SQ_N3 = 2 * BOARD_FILES + 13,     SQ_O3 = 2 * BOARD_FILES + 14,     SQ_P3 = 2 * BOARD_FILES + 15,
  SQ_Q3 = 2 * BOARD_FILES + 16,     SQ_R3 = 2 * BOARD_FILES + 17,     SQ_S3 = 2 * BOARD_FILES + 18,     SQ_T3 = 2 * BOARD_FILES + 19,
  SQ_U3 = 2 * BOARD_FILES + 20,     SQ_V3 = 2 * BOARD_FILES + 21,     SQ_W3 = 2 * BOARD_FILES + 22,     SQ_X3 = 2 * BOARD_FILES + 23,
  SQ_Y3 = 2 * BOARD_FILES + 24,     SQ_Z3 = 2 * BOARD_FILES + 25,     SQ_AA3 = 2 * BOARD_FILES + 26,     SQ_AB3 = 2 * BOARD_FILES + 27,
  SQ_AC3 = 2 * BOARD_FILES + 28,     SQ_AD3 = 2 * BOARD_FILES + 29,     SQ_AE3 = 2 * BOARD_FILES + 30,     SQ_AF3 = 2 * BOARD_FILES + 31,
  SQ_A4 = 3 * BOARD_FILES + 0,     SQ_B4 = 3 * BOARD_FILES + 1,     SQ_C4 = 3 * BOARD_FILES + 2,     SQ_D4 = 3 * BOARD_FILES + 3,
  SQ_E4 = 3 * BOARD_FILES + 4,     SQ_F4 = 3 * BOARD_FILES + 5,     SQ_G4 = 3 * BOARD_FILES + 6,     SQ_H4 = 3 * BOARD_FILES + 7,
  SQ_I4 = 3 * BOARD_FILES + 8,     SQ_J4 = 3 * BOARD_FILES + 9,     SQ_K4 = 3 * BOARD_FILES + 10,     SQ_L4 = 3 * BOARD_FILES + 11,
  SQ_M4 = 3 * BOARD_FILES + 12,     SQ_N4 = 3 * BOARD_FILES + 13,     SQ_O4 = 3 * BOARD_FILES + 14,     SQ_P4 = 3 * BOARD_FILES + 15,
  SQ_Q4 = 3 * BOARD_FILES + 16,     SQ_R4 = 3 * BOARD_FILES + 17,     SQ_S4 = 3 * BOARD_FILES + 18,     SQ_T4 = 3 * BOARD_FILES + 19,
  SQ_U4 = 3 * BOARD_FILES + 20,     SQ_V4 = 3 * BOARD_FILES + 21,     SQ_W4 = 3 * BOARD_FILES + 22,     SQ_X4 = 3 * BOARD_FILES + 23,
  SQ_Y4 = 3 * BOARD_FILES + 24,     SQ_Z4 = 3 * BOARD_FILES + 25,     SQ_AA4 = 3 * BOARD_FILES + 26,     SQ_AB4 = 3 * BOARD_FILES + 27,
  SQ_AC4 = 3 * BOARD_FILES + 28,     SQ_AD4 = 3 * BOARD_FILES + 29,     SQ_AE4 = 3 * BOARD_FILES + 30,     SQ_AF4 = 3 * BOARD_FILES + 31,
  SQ_A5 = 4 * BOARD_FILES + 0,     SQ_B5 = 4 * BOARD_FILES + 1,     SQ_C5 = 4 * BOARD_FILES + 2,     SQ_D5 = 4 * BOARD_FILES + 3,
  SQ_E5 = 4 * BOARD_FILES + 4,     SQ_F5 = 4 * BOARD_FILES + 5,     SQ_G5 = 4 * BOARD_FILES + 6,     SQ_H5 = 4 * BOARD_FILES + 7,
  SQ_I5 = 4 * BOARD_FILES + 8,     SQ_J5 = 4 * BOARD_FILES + 9,     SQ_K5 = 4 * BOARD_FILES + 10,     SQ_L5 = 4 * BOARD_FILES + 11,
  SQ_M5 = 4 * BOARD_FILES + 12,     SQ_N5 = 4 * BOARD_FILES + 13,     SQ_O5 = 4 * BOARD_FILES + 14,     SQ_P5 = 4 * BOARD_FILES + 15,
  SQ_Q5 = 4 * BOARD_FILES + 16,     SQ_R5 = 4 * BOARD_FILES + 17,     SQ_S5 = 4 * BOARD_FILES + 18,     SQ_T5 = 4 * BOARD_FILES + 19,
  SQ_U5 = 4 * BOARD_FILES + 20,     SQ_V5 = 4 * BOARD_FILES + 21,     SQ_W5 = 4 * BOARD_FILES + 22,     SQ_X5 = 4 * BOARD_FILES + 23,
  SQ_Y5 = 4 * BOARD_FILES + 24,     SQ_Z5 = 4 * BOARD_FILES + 25,     SQ_AA5 = 4 * BOARD_FILES + 26,     SQ_AB5 = 4 * BOARD_FILES + 27,
  SQ_AC5 = 4 * BOARD_FILES + 28,     SQ_AD5 = 4 * BOARD_FILES + 29,     SQ_AE5 = 4 * BOARD_FILES + 30,     SQ_AF5 = 4 * BOARD_FILES + 31,
  SQ_A6 = 5 * BOARD_FILES + 0,     SQ_B6 = 5 * BOARD_FILES + 1,     SQ_C6 = 5 * BOARD_FILES + 2,     SQ_D6 = 5 * BOARD_FILES + 3,
  SQ_E6 = 5 * BOARD_FILES + 4,     SQ_F6 = 5 * BOARD_FILES + 5,     SQ_G6 = 5 * BOARD_FILES + 6,     SQ_H6 = 5 * BOARD_FILES + 7,
  SQ_I6 = 5 * BOARD_FILES + 8,     SQ_J6 = 5 * BOARD_FILES + 9,     SQ_K6 = 5 * BOARD_FILES + 10,     SQ_L6 = 5 * BOARD_FILES + 11,
  SQ_M6 = 5 * BOARD_FILES + 12,     SQ_N6 = 5 * BOARD_FILES + 13,     SQ_O6 = 5 * BOARD_FILES + 14,     SQ_P6 = 5 * BOARD_FILES + 15,
  SQ_Q6 = 5 * BOARD_FILES + 16,     SQ_R6 = 5 * BOARD_FILES + 17,     SQ_S6 = 5 * BOARD_FILES + 18,     SQ_T6 = 5 * BOARD_FILES + 19,
  SQ_U6 = 5 * BOARD_FILES + 20,     SQ_V6 = 5 * BOARD_FILES + 21,     SQ_W6 = 5 * BOARD_FILES + 22,     SQ_X6 = 5 * BOARD_FILES + 23,
  SQ_Y6 = 5 * BOARD_FILES + 24,     SQ_Z6 = 5 * BOARD_FILES + 25,     SQ_AA6 = 5 * BOARD_FILES + 26,     SQ_AB6 = 5 * BOARD_FILES + 27,
  SQ_AC6 = 5 * BOARD_FILES + 28,     SQ_AD6 = 5 * BOARD_FILES + 29,     SQ_AE6 = 5 * BOARD_FILES + 30,     SQ_AF6 = 5 * BOARD_FILES + 31,
  SQ_A7 = 6 * BOARD_FILES + 0,     SQ_B7 = 6 * BOARD_FILES + 1,     SQ_C7 = 6 * BOARD_FILES + 2,     SQ_D7 = 6 * BOARD_FILES + 3,
  SQ_E7 = 6 * BOARD_FILES + 4,     SQ_F7 = 6 * BOARD_FILES + 5,     SQ_G7 = 6 * BOARD_FILES + 6,     SQ_H7 = 6 * BOARD_FILES + 7,
  SQ_I7 = 6 * BOARD_FILES + 8,     SQ_J7 = 6 * BOARD_FILES + 9,     SQ_K7 = 6 * BOARD_FILES + 10,     SQ_L7 = 6 * BOARD_FILES + 11,
  SQ_M7 = 6 * BOARD_FILES + 12,     SQ_N7 = 6 * BOARD_FILES + 13,     SQ_O7 = 6 * BOARD_FILES + 14,     SQ_P7 = 6 * BOARD_FILES + 15,
  SQ_Q7 = 6 * BOARD_FILES + 16,     SQ_R7 = 6 * BOARD_FILES + 17,     SQ_S7 = 6 * BOARD_FILES + 18,     SQ_T7 = 6 * BOARD_FILES + 19,
  SQ_U7 = 6 * BOARD_FILES + 20,     SQ_V7 = 6 * BOARD_FILES + 21,     SQ_W7 = 6 * BOARD_FILES + 22,     SQ_X7 = 6 * BOARD_FILES + 23,
  SQ_Y7 = 6 * BOARD_FILES + 24,     SQ_Z7 = 6 * BOARD_FILES + 25,     SQ_AA7 = 6 * BOARD_FILES + 26,     SQ_AB7 = 6 * BOARD_FILES + 27,
  SQ_AC7 = 6 * BOARD_FILES + 28,     SQ_AD7 = 6 * BOARD_FILES + 29,     SQ_AE7 = 6 * BOARD_FILES + 30,     SQ_AF7 = 6 * BOARD_FILES + 31,
  SQ_A8 = 7 * BOARD_FILES + 0,     SQ_B8 = 7 * BOARD_FILES + 1,     SQ_C8 = 7 * BOARD_FILES + 2,     SQ_D8 = 7 * BOARD_FILES + 3,
  SQ_E8 = 7 * BOARD_FILES + 4,     SQ_F8 = 7 * BOARD_FILES + 5,     SQ_G8 = 7 * BOARD_FILES + 6,     SQ_H8 = 7 * BOARD_FILES + 7,
  SQ_I8 = 7 * BOARD_FILES + 8,     SQ_J8 = 7 * BOARD_FILES + 9,     SQ_K8 = 7 * BOARD_FILES + 10,     SQ_L8 = 7 * BOARD_FILES + 11,
  SQ_M8 = 7 * BOARD_FILES + 12,     SQ_N8 = 7 * BOARD_FILES + 13,     SQ_O8 = 7 * BOARD_FILES + 14,     SQ_P8 = 7 * BOARD_FILES + 15,
  SQ_Q8 = 7 * BOARD_FILES + 16,     SQ_R8 = 7 * BOARD_FILES + 17,     SQ_S8 = 7 * BOARD_FILES + 18,     SQ_T8 = 7 * BOARD_FILES + 19,
  SQ_U8 = 7 * BOARD_FILES + 20,     SQ_V8 = 7 * BOARD_FILES + 21,     SQ_W8 = 7 * BOARD_FILES + 22,     SQ_X8 = 7 * BOARD_FILES + 23,
  SQ_Y8 = 7 * BOARD_FILES + 24,     SQ_Z8 = 7 * BOARD_FILES + 25,     SQ_AA8 = 7 * BOARD_FILES + 26,     SQ_AB8 = 7 * BOARD_FILES + 27,
  SQ_AC8 = 7 * BOARD_FILES + 28,     SQ_AD8 = 7 * BOARD_FILES + 29,     SQ_AE8 = 7 * BOARD_FILES + 30,     SQ_AF8 = 7 * BOARD_FILES + 31,
  SQ_A9 = 8 * BOARD_FILES + 0,     SQ_B9 = 8 * BOARD_FILES + 1,     SQ_C9 = 8 * BOARD_FILES + 2,     SQ_D9 = 8 * BOARD_FILES + 3,
  SQ_E9 = 8 * BOARD_FILES + 4,     SQ_F9 = 8 * BOARD_FILES + 5,     SQ_G9 = 8 * BOARD_FILES + 6,     SQ_H9 = 8 * BOARD_FILES + 7,
  SQ_I9 = 8 * BOARD_FILES + 8,     SQ_J9 = 8 * BOARD_FILES + 9,     SQ_K9 = 8 * BOARD_FILES + 10,     SQ_L9 = 8 * BOARD_FILES + 11,
  SQ_M9 = 8 * BOARD_FILES + 12,     SQ_N9 = 8 * BOARD_FILES + 13,     SQ_O9 = 8 * BOARD_FILES + 14,     SQ_P9 = 8 * BOARD_FILES + 15,
  SQ_Q9 = 8 * BOARD_FILES + 16,     SQ_R9 = 8 * BOARD_FILES + 17,     SQ_S9 = 8 * BOARD_FILES + 18,     SQ_T9 = 8 * BOARD_FILES + 19,
  SQ_U9 = 8 * BOARD_FILES + 20,     SQ_V9 = 8 * BOARD_FILES + 21,     SQ_W9 = 8 * BOARD_FILES + 22,     SQ_X9 = 8 * BOARD_FILES + 23,
  SQ_Y9 = 8 * BOARD_FILES + 24,     SQ_Z9 = 8 * BOARD_FILES + 25,     SQ_AA9 = 8 * BOARD_FILES + 26,     SQ_AB9 = 8 * BOARD_FILES + 27,
  SQ_AC9 = 8 * BOARD_FILES + 28,     SQ_AD9 = 8 * BOARD_FILES + 29,     SQ_AE9 = 8 * BOARD_FILES + 30,     SQ_AF9 = 8 * BOARD_FILES + 31,
  SQ_A10 = 9 * BOARD_FILES + 0,     SQ_B10 = 9 * BOARD_FILES + 1,     SQ_C10 = 9 * BOARD_FILES + 2,     SQ_D10 = 9 * BOARD_FILES + 3,
  SQ_E10 = 9 * BOARD_FILES + 4,     SQ_F10 = 9 * BOARD_FILES + 5,     SQ_G10 = 9 * BOARD_FILES + 6,     SQ_H10 = 9 * BOARD_FILES + 7,
  SQ_I10 = 9 * BOARD_FILES + 8,     SQ_J10 = 9 * BOARD_FILES + 9,     SQ_K10 = 9 * BOARD_FILES + 10,     SQ_L10 = 9 * BOARD_FILES + 11,
  SQ_M10 = 9 * BOARD_FILES + 12,     SQ_N10 = 9 * BOARD_FILES + 13,     SQ_O10 = 9 * BOARD_FILES + 14,     SQ_P10 = 9 * BOARD_FILES + 15,
  SQ_Q10 = 9 * BOARD_FILES + 16,     SQ_R10 = 9 * BOARD_FILES + 17,     SQ_S10 = 9 * BOARD_FILES + 18,     SQ_T10 = 9 * BOARD_FILES + 19,
  SQ_U10 = 9 * BOARD_FILES + 20,     SQ_V10 = 9 * BOARD_FILES + 21,     SQ_W10 = 9 * BOARD_FILES + 22,     SQ_X10 = 9 * BOARD_FILES + 23,
  SQ_Y10 = 9 * BOARD_FILES + 24,     SQ_Z10 = 9 * BOARD_FILES + 25,     SQ_AA10 = 9 * BOARD_FILES + 26,     SQ_AB10 = 9 * BOARD_FILES + 27,
  SQ_AC10 = 9 * BOARD_FILES + 28,     SQ_AD10 = 9 * BOARD_FILES + 29,     SQ_AE10 = 9 * BOARD_FILES + 30,     SQ_AF10 = 9 * BOARD_FILES + 31,
  SQ_A11 = 10 * BOARD_FILES + 0,     SQ_B11 = 10 * BOARD_FILES + 1,     SQ_C11 = 10 * BOARD_FILES + 2,     SQ_D11 = 10 * BOARD_FILES + 3,
  SQ_E11 = 10 * BOARD_FILES + 4,     SQ_F11 = 10 * BOARD_FILES + 5,     SQ_G11 = 10 * BOARD_FILES + 6,     SQ_H11 = 10 * BOARD_FILES + 7,
  SQ_I11 = 10 * BOARD_FILES + 8,     SQ_J11 = 10 * BOARD_FILES + 9,     SQ_K11 = 10 * BOARD_FILES + 10,     SQ_L11 = 10 * BOARD_FILES + 11,
  SQ_M11 = 10 * BOARD_FILES + 12,     SQ_N11 = 10 * BOARD_FILES + 13,     SQ_O11 = 10 * BOARD_FILES + 14,     SQ_P11 = 10 * BOARD_FILES + 15,
  SQ_Q11 = 10 * BOARD_FILES + 16,     SQ_R11 = 10 * BOARD_FILES + 17,     SQ_S11 = 10 * BOARD_FILES + 18,     SQ_T11 = 10 * BOARD_FILES + 19,
  SQ_U11 = 10 * BOARD_FILES + 20,     SQ_V11 = 10 * BOARD_FILES + 21,     SQ_W11 = 10 * BOARD_FILES + 22,     SQ_X11 = 10 * BOARD_FILES + 23,
  SQ_Y11 = 10 * BOARD_FILES + 24,     SQ_Z11 = 10 * BOARD_FILES + 25,     SQ_AA11 = 10 * BOARD_FILES + 26,     SQ_AB11 = 10 * BOARD_FILES + 27,
  SQ_AC11 = 10 * BOARD_FILES + 28,     SQ_AD11 = 10 * BOARD_FILES + 29,     SQ_AE11 = 10 * BOARD_FILES + 30,     SQ_AF11 = 10 * BOARD_FILES + 31,
  SQ_A12 = 11 * BOARD_FILES + 0,     SQ_B12 = 11 * BOARD_FILES + 1,     SQ_C12 = 11 * BOARD_FILES + 2,     SQ_D12 = 11 * BOARD_FILES + 3,
  SQ_E12 = 11 * BOARD_FILES + 4,     SQ_F12 = 11 * BOARD_FILES + 5,     SQ_G12 = 11 * BOARD_FILES + 6,     SQ_H12 = 11 * BOARD_FILES + 7,
  SQ_I12 = 11 * BOARD_FILES + 8,     SQ_J12 = 11 * BOARD_FILES + 9,     SQ_K12 = 11 * BOARD_FILES + 10,     SQ_L12 = 11 * BOARD_FILES + 11,
  SQ_M12 = 11 * BOARD_FILES + 12,     SQ_N12 = 11 * BOARD_FILES + 13,     SQ_O12 = 11 * BOARD_FILES + 14,     SQ_P12 = 11 * BOARD_FILES + 15,
  SQ_Q12 = 11 * BOARD_FILES + 16,     SQ_R12 = 11 * BOARD_FILES + 17,     SQ_S12 = 11 * BOARD_FILES + 18,     SQ_T12 = 11 * BOARD_FILES + 19,
  SQ_U12 = 11 * BOARD_FILES + 20,     SQ_V12 = 11 * BOARD_FILES + 21,     SQ_W12 = 11 * BOARD_FILES + 22,     SQ_X12 = 11 * BOARD_FILES + 23,
  SQ_Y12 = 11 * BOARD_FILES + 24,     SQ_Z12 = 11 * BOARD_FILES + 25,     SQ_AA12 = 11 * BOARD_FILES + 26,     SQ_AB12 = 11 * BOARD_FILES + 27,
  SQ_AC12 = 11 * BOARD_FILES + 28,     SQ_AD12 = 11 * BOARD_FILES + 29,     SQ_AE12 = 11 * BOARD_FILES + 30,     SQ_AF12 = 11 * BOARD_FILES + 31,
  SQ_A13 = 12 * BOARD_FILES + 0,     SQ_B13 = 12 * BOARD_FILES + 1,     SQ_C13 = 12 * BOARD_FILES + 2,     SQ_D13 = 12 * BOARD_FILES + 3,
  SQ_E13 = 12 * BOARD_FILES + 4,     SQ_F13 = 12 * BOARD_FILES + 5,     SQ_G13 = 12 * BOARD_FILES + 6,     SQ_H13 = 12 * BOARD_FILES + 7,
  SQ_I13 = 12 * BOARD_FILES + 8,     SQ_J13 = 12 * BOARD_FILES + 9,     SQ_K13 = 12 * BOARD_FILES + 10,     SQ_L13 = 12 * BOARD_FILES + 11,
  SQ_M13 = 12 * BOARD_FILES + 12,     SQ_N13 = 12 * BOARD_FILES + 13,     SQ_O13 = 12 * BOARD_FILES + 14,     SQ_P13 = 12 * BOARD_FILES + 15,
  SQ_Q13 = 12 * BOARD_FILES + 16,     SQ_R13 = 12 * BOARD_FILES + 17,     SQ_S13 = 12 * BOARD_FILES + 18,     SQ_T13 = 12 * BOARD_FILES + 19,
  SQ_U13 = 12 * BOARD_FILES + 20,     SQ_V13 = 12 * BOARD_FILES + 21,     SQ_W13 = 12 * BOARD_FILES + 22,     SQ_X13 = 12 * BOARD_FILES + 23,
  SQ_Y13 = 12 * BOARD_FILES + 24,     SQ_Z13 = 12 * BOARD_FILES + 25,     SQ_AA13 = 12 * BOARD_FILES + 26,     SQ_AB13 = 12 * BOARD_FILES + 27,
  SQ_AC13 = 12 * BOARD_FILES + 28,     SQ_AD13 = 12 * BOARD_FILES + 29,     SQ_AE13 = 12 * BOARD_FILES + 30,     SQ_AF13 = 12 * BOARD_FILES + 31,
  SQ_A14 = 13 * BOARD_FILES + 0,     SQ_B14 = 13 * BOARD_FILES + 1,     SQ_C14 = 13 * BOARD_FILES + 2,     SQ_D14 = 13 * BOARD_FILES + 3,
  SQ_E14 = 13 * BOARD_FILES + 4,     SQ_F14 = 13 * BOARD_FILES + 5,     SQ_G14 = 13 * BOARD_FILES + 6,     SQ_H14 = 13 * BOARD_FILES + 7,
  SQ_I14 = 13 * BOARD_FILES + 8,     SQ_J14 = 13 * BOARD_FILES + 9,     SQ_K14 = 13 * BOARD_FILES + 10,     SQ_L14 = 13 * BOARD_FILES + 11,
  SQ_M14 = 13 * BOARD_FILES + 12,     SQ_N14 = 13 * BOARD_FILES + 13,     SQ_O14 = 13 * BOARD_FILES + 14,     SQ_P14 = 13 * BOARD_FILES + 15,
  SQ_Q14 = 13 * BOARD_FILES + 16,     SQ_R14 = 13 * BOARD_FILES + 17,     SQ_S14 = 13 * BOARD_FILES + 18,     SQ_T14 = 13 * BOARD_FILES + 19,
  SQ_U14 = 13 * BOARD_FILES + 20,     SQ_V14 = 13 * BOARD_FILES + 21,     SQ_W14 = 13 * BOARD_FILES + 22,     SQ_X14 = 13 * BOARD_FILES + 23,
  SQ_Y14 = 13 * BOARD_FILES + 24,     SQ_Z14 = 13 * BOARD_FILES + 25,     SQ_AA14 = 13 * BOARD_FILES + 26,     SQ_AB14 = 13 * BOARD_FILES + 27,
  SQ_AC14 = 13 * BOARD_FILES + 28,     SQ_AD14 = 13 * BOARD_FILES + 29,     SQ_AE14 = 13 * BOARD_FILES + 30,     SQ_AF14 = 13 * BOARD_FILES + 31,
  SQ_A15 = 14 * BOARD_FILES + 0,     SQ_B15 = 14 * BOARD_FILES + 1,     SQ_C15 = 14 * BOARD_FILES + 2,     SQ_D15 = 14 * BOARD_FILES + 3,
  SQ_E15 = 14 * BOARD_FILES + 4,     SQ_F15 = 14 * BOARD_FILES + 5,     SQ_G15 = 14 * BOARD_FILES + 6,     SQ_H15 = 14 * BOARD_FILES + 7,
  SQ_I15 = 14 * BOARD_FILES + 8,     SQ_J15 = 14 * BOARD_FILES + 9,     SQ_K15 = 14 * BOARD_FILES + 10,     SQ_L15 = 14 * BOARD_FILES + 11,
  SQ_M15 = 14 * BOARD_FILES + 12,     SQ_N15 = 14 * BOARD_FILES + 13,     SQ_O15 = 14 * BOARD_FILES + 14,     SQ_P15 = 14 * BOARD_FILES + 15,
  SQ_Q15 = 14 * BOARD_FILES + 16,     SQ_R15 = 14 * BOARD_FILES + 17,     SQ_S15 = 14 * BOARD_FILES + 18,     SQ_T15 = 14 * BOARD_FILES + 19,
  SQ_U15 = 14 * BOARD_FILES + 20,     SQ_V15 = 14 * BOARD_FILES + 21,     SQ_W15 = 14 * BOARD_FILES + 22,     SQ_X15 = 14 * BOARD_FILES + 23,
  SQ_Y15 = 14 * BOARD_FILES + 24,     SQ_Z15 = 14 * BOARD_FILES + 25,     SQ_AA15 = 14 * BOARD_FILES + 26,     SQ_AB15 = 14 * BOARD_FILES + 27,
  SQ_AC15 = 14 * BOARD_FILES + 28,     SQ_AD15 = 14 * BOARD_FILES + 29,     SQ_AE15 = 14 * BOARD_FILES + 30,     SQ_AF15 = 14 * BOARD_FILES + 31,
  SQ_A16 = 15 * BOARD_FILES + 0,     SQ_B16 = 15 * BOARD_FILES + 1,     SQ_C16 = 15 * BOARD_FILES + 2,     SQ_D16 = 15 * BOARD_FILES + 3,
  SQ_E16 = 15 * BOARD_FILES + 4,     SQ_F16 = 15 * BOARD_FILES + 5,     SQ_G16 = 15 * BOARD_FILES + 6,     SQ_H16 = 15 * BOARD_FILES + 7,
  SQ_I16 = 15 * BOARD_FILES + 8,     SQ_J16 = 15 * BOARD_FILES + 9,     SQ_K16 = 15 * BOARD_FILES + 10,     SQ_L16 = 15 * BOARD_FILES + 11,
  SQ_M16 = 15 * BOARD_FILES + 12,     SQ_N16 = 15 * BOARD_FILES + 13,     SQ_O16 = 15 * BOARD_FILES + 14,     SQ_P16 = 15 * BOARD_FILES + 15,
  SQ_Q16 = 15 * BOARD_FILES + 16,     SQ_R16 = 15 * BOARD_FILES + 17,     SQ_S16 = 15 * BOARD_FILES + 18,     SQ_T16 = 15 * BOARD_FILES + 19,
  SQ_U16 = 15 * BOARD_FILES + 20,     SQ_V16 = 15 * BOARD_FILES + 21,     SQ_W16 = 15 * BOARD_FILES + 22,     SQ_X16 = 15 * BOARD_FILES + 23,
  SQ_Y16 = 15 * BOARD_FILES + 24,     SQ_Z16 = 15 * BOARD_FILES + 25,     SQ_AA16 = 15 * BOARD_FILES + 26,     SQ_AB16 = 15 * BOARD_FILES + 27,
  SQ_AC16 = 15 * BOARD_FILES + 28,     SQ_AD16 = 15 * BOARD_FILES + 29,     SQ_AE16 = 15 * BOARD_FILES + 30,     SQ_AF16 = 15 * BOARD_FILES + 31,
  SQ_A17 = 16 * BOARD_FILES + 0,     SQ_B17 = 16 * BOARD_FILES + 1,     SQ_C17 = 16 * BOARD_FILES + 2,     SQ_D17 = 16 * BOARD_FILES + 3,
  SQ_E17 = 16 * BOARD_FILES + 4,     SQ_F17 = 16 * BOARD_FILES + 5,     SQ_G17 = 16 * BOARD_FILES + 6,     SQ_H17 = 16 * BOARD_FILES + 7,
  SQ_I17 = 16 * BOARD_FILES + 8,     SQ_J17 = 16 * BOARD_FILES + 9,     SQ_K17 = 16 * BOARD_FILES + 10,     SQ_L17 = 16 * BOARD_FILES + 11,
  SQ_M17 = 16 * BOARD_FILES + 12,     SQ_N17 = 16 * BOARD_FILES + 13,     SQ_O17 = 16 * BOARD_FILES + 14,     SQ_P17 = 16 * BOARD_FILES + 15,
  SQ_Q17 = 16 * BOARD_FILES + 16,     SQ_R17 = 16 * BOARD_FILES + 17,     SQ_S17 = 16 * BOARD_FILES + 18,     SQ_T17 = 16 * BOARD_FILES + 19,
  SQ_U17 = 16 * BOARD_FILES + 20,     SQ_V17 = 16 * BOARD_FILES + 21,     SQ_W17 = 16 * BOARD_FILES + 22,     SQ_X17 = 16 * BOARD_FILES + 23,
  SQ_Y17 = 16 * BOARD_FILES + 24,     SQ_Z17 = 16 * BOARD_FILES + 25,     SQ_AA17 = 16 * BOARD_FILES + 26,     SQ_AB17 = 16 * BOARD_FILES + 27,
  SQ_AC17 = 16 * BOARD_FILES + 28,     SQ_AD17 = 16 * BOARD_FILES + 29,     SQ_AE17 = 16 * BOARD_FILES + 30,     SQ_AF17 = 16 * BOARD_FILES + 31,
  SQ_A18 = 17 * BOARD_FILES + 0,     SQ_B18 = 17 * BOARD_FILES + 1,     SQ_C18 = 17 * BOARD_FILES + 2,     SQ_D18 = 17 * BOARD_FILES + 3,
  SQ_E18 = 17 * BOARD_FILES + 4,     SQ_F18 = 17 * BOARD_FILES + 5,     SQ_G18 = 17 * BOARD_FILES + 6,     SQ_H18 = 17 * BOARD_FILES + 7,
  SQ_I18 = 17 * BOARD_FILES + 8,     SQ_J18 = 17 * BOARD_FILES + 9,     SQ_K18 = 17 * BOARD_FILES + 10,     SQ_L18 = 17 * BOARD_FILES + 11,
  SQ_M18 = 17 * BOARD_FILES + 12,     SQ_N18 = 17 * BOARD_FILES + 13,     SQ_O18 = 17 * BOARD_FILES + 14,     SQ_P18 = 17 * BOARD_FILES + 15,
  SQ_Q18 = 17 * BOARD_FILES + 16,     SQ_R18 = 17 * BOARD_FILES + 17,     SQ_S18 = 17 * BOARD_FILES + 18,     SQ_T18 = 17 * BOARD_FILES + 19,
  SQ_U18 = 17 * BOARD_FILES + 20,     SQ_V18 = 17 * BOARD_FILES + 21,     SQ_W18 = 17 * BOARD_FILES + 22,     SQ_X18 = 17 * BOARD_FILES + 23,
  SQ_Y18 = 17 * BOARD_FILES + 24,     SQ_Z18 = 17 * BOARD_FILES + 25,     SQ_AA18 = 17 * BOARD_FILES + 26,     SQ_AB18 = 17 * BOARD_FILES + 27,
  SQ_AC18 = 17 * BOARD_FILES + 28,     SQ_AD18 = 17 * BOARD_FILES + 29,     SQ_AE18 = 17 * BOARD_FILES + 30,     SQ_AF18 = 17 * BOARD_FILES + 31,
  SQ_A19 = 18 * BOARD_FILES + 0,     SQ_B19 = 18 * BOARD_FILES + 1,     SQ_C19 = 18 * BOARD_FILES + 2,     SQ_D19 = 18 * BOARD_FILES + 3,
  SQ_E19 = 18 * BOARD_FILES + 4,     SQ_F19 = 18 * BOARD_FILES + 5,     SQ_G19 = 18 * BOARD_FILES + 6,     SQ_H19 = 18 * BOARD_FILES + 7,
  SQ_I19 = 18 * BOARD_FILES + 8,     SQ_J19 = 18 * BOARD_FILES + 9,     SQ_K19 = 18 * BOARD_FILES + 10,     SQ_L19 = 18 * BOARD_FILES + 11,
  SQ_M19 = 18 * BOARD_FILES + 12,     SQ_N19 = 18 * BOARD_FILES + 13,     SQ_O19 = 18 * BOARD_FILES + 14,     SQ_P19 = 18 * BOARD_FILES + 15,
  SQ_Q19 = 18 * BOARD_FILES + 16,     SQ_R19 = 18 * BOARD_FILES + 17,     SQ_S19 = 18 * BOARD_FILES + 18,     SQ_T19 = 18 * BOARD_FILES + 19,
  SQ_U19 = 18 * BOARD_FILES + 20,     SQ_V19 = 18 * BOARD_FILES + 21,     SQ_W19 = 18 * BOARD_FILES + 22,     SQ_X19 = 18 * BOARD_FILES + 23,
  SQ_Y19 = 18 * BOARD_FILES + 24,     SQ_Z19 = 18 * BOARD_FILES + 25,     SQ_AA19 = 18 * BOARD_FILES + 26,     SQ_AB19 = 18 * BOARD_FILES + 27,
  SQ_AC19 = 18 * BOARD_FILES + 28,     SQ_AD19 = 18 * BOARD_FILES + 29,     SQ_AE19 = 18 * BOARD_FILES + 30,     SQ_AF19 = 18 * BOARD_FILES + 31,
  SQ_A20 = 19 * BOARD_FILES + 0,     SQ_B20 = 19 * BOARD_FILES + 1,     SQ_C20 = 19 * BOARD_FILES + 2,     SQ_D20 = 19 * BOARD_FILES + 3,
  SQ_E20 = 19 * BOARD_FILES + 4,     SQ_F20 = 19 * BOARD_FILES + 5,     SQ_G20 = 19 * BOARD_FILES + 6,     SQ_H20 = 19 * BOARD_FILES + 7,
  SQ_I20 = 19 * BOARD_FILES + 8,     SQ_J20 = 19 * BOARD_FILES + 9,     SQ_K20 = 19 * BOARD_FILES + 10,     SQ_L20 = 19 * BOARD_FILES + 11,
  SQ_M20 = 19 * BOARD_FILES + 12,     SQ_N20 = 19 * BOARD_FILES + 13,     SQ_O20 = 19 * BOARD_FILES + 14,     SQ_P20 = 19 * BOARD_FILES + 15,
  SQ_Q20 = 19 * BOARD_FILES + 16,     SQ_R20 = 19 * BOARD_FILES + 17,     SQ_S20 = 19 * BOARD_FILES + 18,     SQ_T20 = 19 * BOARD_FILES + 19,
  SQ_U20 = 19 * BOARD_FILES + 20,     SQ_V20 = 19 * BOARD_FILES + 21,     SQ_W20 = 19 * BOARD_FILES + 22,     SQ_X20 = 19 * BOARD_FILES + 23,
  SQ_Y20 = 19 * BOARD_FILES + 24,     SQ_Z20 = 19 * BOARD_FILES + 25,     SQ_AA20 = 19 * BOARD_FILES + 26,     SQ_AB20 = 19 * BOARD_FILES + 27,
  SQ_AC20 = 19 * BOARD_FILES + 28,     SQ_AD20 = 19 * BOARD_FILES + 29,     SQ_AE20 = 19 * BOARD_FILES + 30,     SQ_AF20 = 19 * BOARD_FILES + 31,
  SQ_A21 = 20 * BOARD_FILES + 0,     SQ_B21 = 20 * BOARD_FILES + 1,     SQ_C21 = 20 * BOARD_FILES + 2,     SQ_D21 = 20 * BOARD_FILES + 3,
  SQ_E21 = 20 * BOARD_FILES + 4,     SQ_F21 = 20 * BOARD_FILES + 5,     SQ_G21 = 20 * BOARD_FILES + 6,     SQ_H21 = 20 * BOARD_FILES + 7,
  SQ_I21 = 20 * BOARD_FILES + 8,     SQ_J21 = 20 * BOARD_FILES + 9,     SQ_K21 = 20 * BOARD_FILES + 10,     SQ_L21 = 20 * BOARD_FILES + 11,
  SQ_M21 = 20 * BOARD_FILES + 12,     SQ_N21 = 20 * BOARD_FILES + 13,     SQ_O21 = 20 * BOARD_FILES + 14,     SQ_P21 = 20 * BOARD_FILES + 15,
  SQ_Q21 = 20 * BOARD_FILES + 16,     SQ_R21 = 20 * BOARD_FILES + 17,     SQ_S21 = 20 * BOARD_FILES + 18,     SQ_T21 = 20 * BOARD_FILES + 19,
  SQ_U21 = 20 * BOARD_FILES + 20,     SQ_V21 = 20 * BOARD_FILES + 21,     SQ_W21 = 20 * BOARD_FILES + 22,     SQ_X21 = 20 * BOARD_FILES + 23,
  SQ_Y21 = 20 * BOARD_FILES + 24,     SQ_Z21 = 20 * BOARD_FILES + 25,     SQ_AA21 = 20 * BOARD_FILES + 26,     SQ_AB21 = 20 * BOARD_FILES + 27,
  SQ_AC21 = 20 * BOARD_FILES + 28,     SQ_AD21 = 20 * BOARD_FILES + 29,     SQ_AE21 = 20 * BOARD_FILES + 30,     SQ_AF21 = 20 * BOARD_FILES + 31,
  SQ_A22 = 21 * BOARD_FILES + 0,     SQ_B22 = 21 * BOARD_FILES + 1,     SQ_C22 = 21 * BOARD_FILES + 2,     SQ_D22 = 21 * BOARD_FILES + 3,
  SQ_E22 = 21 * BOARD_FILES + 4,     SQ_F22 = 21 * BOARD_FILES + 5,     SQ_G22 = 21 * BOARD_FILES + 6,     SQ_H22 = 21 * BOARD_FILES + 7,
  SQ_I22 = 21 * BOARD_FILES + 8,     SQ_J22 = 21 * BOARD_FILES + 9,     SQ_K22 = 21 * BOARD_FILES + 10,     SQ_L22 = 21 * BOARD_FILES + 11,
  SQ_M22 = 21 * BOARD_FILES + 12,     SQ_N22 = 21 * BOARD_FILES + 13,     SQ_O22 = 21 * BOARD_FILES + 14,     SQ_P22 = 21 * BOARD_FILES + 15,
  SQ_Q22 = 21 * BOARD_FILES + 16,     SQ_R22 = 21 * BOARD_FILES + 17,     SQ_S22 = 21 * BOARD_FILES + 18,     SQ_T22 = 21 * BOARD_FILES + 19,
  SQ_U22 = 21 * BOARD_FILES + 20,     SQ_V22 = 21 * BOARD_FILES + 21,     SQ_W22 = 21 * BOARD_FILES + 22,     SQ_X22 = 21 * BOARD_FILES + 23,
  SQ_Y22 = 21 * BOARD_FILES + 24,     SQ_Z22 = 21 * BOARD_FILES + 25,     SQ_AA22 = 21 * BOARD_FILES + 26,     SQ_AB22 = 21 * BOARD_FILES + 27,
  SQ_AC22 = 21 * BOARD_FILES + 28,     SQ_AD22 = 21 * BOARD_FILES + 29,     SQ_AE22 = 21 * BOARD_FILES + 30,     SQ_AF22 = 21 * BOARD_FILES + 31,
  SQ_A23 = 22 * BOARD_FILES + 0,     SQ_B23 = 22 * BOARD_FILES + 1,     SQ_C23 = 22 * BOARD_FILES + 2,     SQ_D23 = 22 * BOARD_FILES + 3,
  SQ_E23 = 22 * BOARD_FILES + 4,     SQ_F23 = 22 * BOARD_FILES + 5,     SQ_G23 = 22 * BOARD_FILES + 6,     SQ_H23 = 22 * BOARD_FILES + 7,
  SQ_I23 = 22 * BOARD_FILES + 8,     SQ_J23 = 22 * BOARD_FILES + 9,     SQ_K23 = 22 * BOARD_FILES + 10,     SQ_L23 = 22 * BOARD_FILES + 11,
  SQ_M23 = 22 * BOARD_FILES + 12,     SQ_N23 = 22 * BOARD_FILES + 13,     SQ_O23 = 22 * BOARD_FILES + 14,     SQ_P23 = 22 * BOARD_FILES + 15,
  SQ_Q23 = 22 * BOARD_FILES + 16,     SQ_R23 = 22 * BOARD_FILES + 17,     SQ_S23 = 22 * BOARD_FILES + 18,     SQ_T23 = 22 * BOARD_FILES + 19,
  SQ_U23 = 22 * BOARD_FILES + 20,     SQ_V23 = 22 * BOARD_FILES + 21,     SQ_W23 = 22 * BOARD_FILES + 22,     SQ_X23 = 22 * BOARD_FILES + 23,
  SQ_Y23 = 22 * BOARD_FILES + 24,     SQ_Z23 = 22 * BOARD_FILES + 25,     SQ_AA23 = 22 * BOARD_FILES + 26,     SQ_AB23 = 22 * BOARD_FILES + 27,
  SQ_AC23 = 22 * BOARD_FILES + 28,     SQ_AD23 = 22 * BOARD_FILES + 29,     SQ_AE23 = 22 * BOARD_FILES + 30,     SQ_AF23 = 22 * BOARD_FILES + 31,
  SQ_A24 = 23 * BOARD_FILES + 0,     SQ_B24 = 23 * BOARD_FILES + 1,     SQ_C24 = 23 * BOARD_FILES + 2,     SQ_D24 = 23 * BOARD_FILES + 3,
  SQ_E24 = 23 * BOARD_FILES + 4,     SQ_F24 = 23 * BOARD_FILES + 5,     SQ_G24 = 23 * BOARD_FILES + 6,     SQ_H24 = 23 * BOARD_FILES + 7,
  SQ_I24 = 23 * BOARD_FILES + 8,     SQ_J24 = 23 * BOARD_FILES + 9,     SQ_K24 = 23 * BOARD_FILES + 10,     SQ_L24 = 23 * BOARD_FILES + 11,
  SQ_M24 = 23 * BOARD_FILES + 12,     SQ_N24 = 23 * BOARD_FILES + 13,     SQ_O24 = 23 * BOARD_FILES + 14,     SQ_P24 = 23 * BOARD_FILES + 15,
  SQ_Q24 = 23 * BOARD_FILES + 16,     SQ_R24 = 23 * BOARD_FILES + 17,     SQ_S24 = 23 * BOARD_FILES + 18,     SQ_T24 = 23 * BOARD_FILES + 19,
  SQ_U24 = 23 * BOARD_FILES + 20,     SQ_V24 = 23 * BOARD_FILES + 21,     SQ_W24 = 23 * BOARD_FILES + 22,     SQ_X24 = 23 * BOARD_FILES + 23,
  SQ_Y24 = 23 * BOARD_FILES + 24,     SQ_Z24 = 23 * BOARD_FILES + 25,     SQ_AA24 = 23 * BOARD_FILES + 26,     SQ_AB24 = 23 * BOARD_FILES + 27,
  SQ_AC24 = 23 * BOARD_FILES + 28,     SQ_AD24 = 23 * BOARD_FILES + 29,     SQ_AE24 = 23 * BOARD_FILES + 30,     SQ_AF24 = 23 * BOARD_FILES + 31,
  SQ_A25 = 24 * BOARD_FILES + 0,     SQ_B25 = 24 * BOARD_FILES + 1,     SQ_C25 = 24 * BOARD_FILES + 2,     SQ_D25 = 24 * BOARD_FILES + 3,
  SQ_E25 = 24 * BOARD_FILES + 4,     SQ_F25 = 24 * BOARD_FILES + 5,     SQ_G25 = 24 * BOARD_FILES + 6,     SQ_H25 = 24 * BOARD_FILES + 7,
  SQ_I25 = 24 * BOARD_FILES + 8,     SQ_J25 = 24 * BOARD_FILES + 9,     SQ_K25 = 24 * BOARD_FILES + 10,     SQ_L25 = 24 * BOARD_FILES + 11,
  SQ_M25 = 24 * BOARD_FILES + 12,     SQ_N25 = 24 * BOARD_FILES + 13,     SQ_O25 = 24 * BOARD_FILES + 14,     SQ_P25 = 24 * BOARD_FILES + 15,
  SQ_Q25 = 24 * BOARD_FILES + 16,     SQ_R25 = 24 * BOARD_FILES + 17,     SQ_S25 = 24 * BOARD_FILES + 18,     SQ_T25 = 24 * BOARD_FILES + 19,
  SQ_U25 = 24 * BOARD_FILES + 20,     SQ_V25 = 24 * BOARD_FILES + 21,     SQ_W25 = 24 * BOARD_FILES + 22,     SQ_X25 = 24 * BOARD_FILES + 23,
  SQ_Y25 = 24 * BOARD_FILES + 24,     SQ_Z25 = 24 * BOARD_FILES + 25,     SQ_AA25 = 24 * BOARD_FILES + 26,     SQ_AB25 = 24 * BOARD_FILES + 27,
  SQ_AC25 = 24 * BOARD_FILES + 28,     SQ_AD25 = 24 * BOARD_FILES + 29,     SQ_AE25 = 24 * BOARD_FILES + 30,     SQ_AF25 = 24 * BOARD_FILES + 31,
  SQ_A26 = 25 * BOARD_FILES + 0,     SQ_B26 = 25 * BOARD_FILES + 1,     SQ_C26 = 25 * BOARD_FILES + 2,     SQ_D26 = 25 * BOARD_FILES + 3,
  SQ_E26 = 25 * BOARD_FILES + 4,     SQ_F26 = 25 * BOARD_FILES + 5,     SQ_G26 = 25 * BOARD_FILES + 6,     SQ_H26 = 25 * BOARD_FILES + 7,
  SQ_I26 = 25 * BOARD_FILES + 8,     SQ_J26 = 25 * BOARD_FILES + 9,     SQ_K26 = 25 * BOARD_FILES + 10,     SQ_L26 = 25 * BOARD_FILES + 11,
  SQ_M26 = 25 * BOARD_FILES + 12,     SQ_N26 = 25 * BOARD_FILES + 13,     SQ_O26 = 25 * BOARD_FILES + 14,     SQ_P26 = 25 * BOARD_FILES + 15,
  SQ_Q26 = 25 * BOARD_FILES + 16,     SQ_R26 = 25 * BOARD_FILES + 17,     SQ_S26 = 25 * BOARD_FILES + 18,     SQ_T26 = 25 * BOARD_FILES + 19,
  SQ_U26 = 25 * BOARD_FILES + 20,     SQ_V26 = 25 * BOARD_FILES + 21,     SQ_W26 = 25 * BOARD_FILES + 22,     SQ_X26 = 25 * BOARD_FILES + 23,
  SQ_Y26 = 25 * BOARD_FILES + 24,     SQ_Z26 = 25 * BOARD_FILES + 25,     SQ_AA26 = 25 * BOARD_FILES + 26,     SQ_AB26 = 25 * BOARD_FILES + 27,
  SQ_AC26 = 25 * BOARD_FILES + 28,     SQ_AD26 = 25 * BOARD_FILES + 29,     SQ_AE26 = 25 * BOARD_FILES + 30,     SQ_AF26 = 25 * BOARD_FILES + 31,
  SQ_A27 = 26 * BOARD_FILES + 0,     SQ_B27 = 26 * BOARD_FILES + 1,     SQ_C27 = 26 * BOARD_FILES + 2,     SQ_D27 = 26 * BOARD_FILES + 3,
  SQ_E27 = 26 * BOARD_FILES + 4,     SQ_F27 = 26 * BOARD_FILES + 5,     SQ_G27 = 26 * BOARD_FILES + 6,     SQ_H27 = 26 * BOARD_FILES + 7,
  SQ_I27 = 26 * BOARD_FILES + 8,     SQ_J27 = 26 * BOARD_FILES + 9,     SQ_K27 = 26 * BOARD_FILES + 10,     SQ_L27 = 26 * BOARD_FILES + 11,
  SQ_M27 = 26 * BOARD_FILES + 12,     SQ_N27 = 26 * BOARD_FILES + 13,     SQ_O27 = 26 * BOARD_FILES + 14,     SQ_P27 = 26 * BOARD_FILES + 15,
  SQ_Q27 = 26 * BOARD_FILES + 16,     SQ_R27 = 26 * BOARD_FILES + 17,     SQ_S27 = 26 * BOARD_FILES + 18,     SQ_T27 = 26 * BOARD_FILES + 19,
  SQ_U27 = 26 * BOARD_FILES + 20,     SQ_V27 = 26 * BOARD_FILES + 21,     SQ_W27 = 26 * BOARD_FILES + 22,     SQ_X27 = 26 * BOARD_FILES + 23,
  SQ_Y27 = 26 * BOARD_FILES + 24,     SQ_Z27 = 26 * BOARD_FILES + 25,     SQ_AA27 = 26 * BOARD_FILES + 26,     SQ_AB27 = 26 * BOARD_FILES + 27,
  SQ_AC27 = 26 * BOARD_FILES + 28,     SQ_AD27 = 26 * BOARD_FILES + 29,     SQ_AE27 = 26 * BOARD_FILES + 30,     SQ_AF27 = 26 * BOARD_FILES + 31,
  SQ_A28 = 27 * BOARD_FILES + 0,     SQ_B28 = 27 * BOARD_FILES + 1,     SQ_C28 = 27 * BOARD_FILES + 2,     SQ_D28 = 27 * BOARD_FILES + 3,
  SQ_E28 = 27 * BOARD_FILES + 4,     SQ_F28 = 27 * BOARD_FILES + 5,     SQ_G28 = 27 * BOARD_FILES + 6,     SQ_H28 = 27 * BOARD_FILES + 7,
  SQ_I28 = 27 * BOARD_FILES + 8,     SQ_J28 = 27 * BOARD_FILES + 9,     SQ_K28 = 27 * BOARD_FILES + 10,     SQ_L28 = 27 * BOARD_FILES + 11,
  SQ_M28 = 27 * BOARD_FILES + 12,     SQ_N28 = 27 * BOARD_FILES + 13,     SQ_O28 = 27 * BOARD_FILES + 14,     SQ_P28 = 27 * BOARD_FILES + 15,
  SQ_Q28 = 27 * BOARD_FILES + 16,     SQ_R28 = 27 * BOARD_FILES + 17,     SQ_S28 = 27 * BOARD_FILES + 18,     SQ_T28 = 27 * BOARD_FILES + 19,
  SQ_U28 = 27 * BOARD_FILES + 20,     SQ_V28 = 27 * BOARD_FILES + 21,     SQ_W28 = 27 * BOARD_FILES + 22,     SQ_X28 = 27 * BOARD_FILES + 23,
  SQ_Y28 = 27 * BOARD_FILES + 24,     SQ_Z28 = 27 * BOARD_FILES + 25,     SQ_AA28 = 27 * BOARD_FILES + 26,     SQ_AB28 = 27 * BOARD_FILES + 27,
  SQ_AC28 = 27 * BOARD_FILES + 28,     SQ_AD28 = 27 * BOARD_FILES + 29,     SQ_AE28 = 27 * BOARD_FILES + 30,     SQ_AF28 = 27 * BOARD_FILES + 31,
  SQ_A29 = 28 * BOARD_FILES + 0,     SQ_B29 = 28 * BOARD_FILES + 1,     SQ_C29 = 28 * BOARD_FILES + 2,     SQ_D29 = 28 * BOARD_FILES + 3,
  SQ_E29 = 28 * BOARD_FILES + 4,     SQ_F29 = 28 * BOARD_FILES + 5,     SQ_G29 = 28 * BOARD_FILES + 6,     SQ_H29 = 28 * BOARD_FILES + 7,
  SQ_I29 = 28 * BOARD_FILES + 8,     SQ_J29 = 28 * BOARD_FILES + 9,     SQ_K29 = 28 * BOARD_FILES + 10,     SQ_L29 = 28 * BOARD_FILES + 11,
  SQ_M29 = 28 * BOARD_FILES + 12,     SQ_N29 = 28 * BOARD_FILES + 13,     SQ_O29 = 28 * BOARD_FILES + 14,     SQ_P29 = 28 * BOARD_FILES + 15,
  SQ_Q29 = 28 * BOARD_FILES + 16,     SQ_R29 = 28 * BOARD_FILES + 17,     SQ_S29 = 28 * BOARD_FILES + 18,     SQ_T29 = 28 * BOARD_FILES + 19,
  SQ_U29 = 28 * BOARD_FILES + 20,     SQ_V29 = 28 * BOARD_FILES + 21,     SQ_W29 = 28 * BOARD_FILES + 22,     SQ_X29 = 28 * BOARD_FILES + 23,
  SQ_Y29 = 28 * BOARD_FILES + 24,     SQ_Z29 = 28 * BOARD_FILES + 25,     SQ_AA29 = 28 * BOARD_FILES + 26,     SQ_AB29 = 28 * BOARD_FILES + 27,
  SQ_AC29 = 28 * BOARD_FILES + 28,     SQ_AD29 = 28 * BOARD_FILES + 29,     SQ_AE29 = 28 * BOARD_FILES + 30,     SQ_AF29 = 28 * BOARD_FILES + 31,
  SQ_A30 = 29 * BOARD_FILES + 0,     SQ_B30 = 29 * BOARD_FILES + 1,     SQ_C30 = 29 * BOARD_FILES + 2,     SQ_D30 = 29 * BOARD_FILES + 3,
  SQ_E30 = 29 * BOARD_FILES + 4,     SQ_F30 = 29 * BOARD_FILES + 5,     SQ_G30 = 29 * BOARD_FILES + 6,     SQ_H30 = 29 * BOARD_FILES + 7,
  SQ_I30 = 29 * BOARD_FILES + 8,     SQ_J30 = 29 * BOARD_FILES + 9,     SQ_K30 = 29 * BOARD_FILES + 10,     SQ_L30 = 29 * BOARD_FILES + 11,
  SQ_M30 = 29 * BOARD_FILES + 12,     SQ_N30 = 29 * BOARD_FILES + 13,     SQ_O30 = 29 * BOARD_FILES + 14,     SQ_P30 = 29 * BOARD_FILES + 15,
  SQ_Q30 = 29 * BOARD_FILES + 16,     SQ_R30 = 29 * BOARD_FILES + 17,     SQ_S30 = 29 * BOARD_FILES + 18,     SQ_T30 = 29 * BOARD_FILES + 19,
  SQ_U30 = 29 * BOARD_FILES + 20,     SQ_V30 = 29 * BOARD_FILES + 21,     SQ_W30 = 29 * BOARD_FILES + 22,     SQ_X30 = 29 * BOARD_FILES + 23,
  SQ_Y30 = 29 * BOARD_FILES + 24,     SQ_Z30 = 29 * BOARD_FILES + 25,     SQ_AA30 = 29 * BOARD_FILES + 26,     SQ_AB30 = 29 * BOARD_FILES + 27,
  SQ_AC30 = 29 * BOARD_FILES + 28,     SQ_AD30 = 29 * BOARD_FILES + 29,     SQ_AE30 = 29 * BOARD_FILES + 30,     SQ_AF30 = 29 * BOARD_FILES + 31,
  SQ_A31 = 30 * BOARD_FILES + 0,     SQ_B31 = 30 * BOARD_FILES + 1,     SQ_C31 = 30 * BOARD_FILES + 2,     SQ_D31 = 30 * BOARD_FILES + 3,
  SQ_E31 = 30 * BOARD_FILES + 4,     SQ_F31 = 30 * BOARD_FILES + 5,     SQ_G31 = 30 * BOARD_FILES + 6,     SQ_H31 = 30 * BOARD_FILES + 7,
  SQ_I31 = 30 * BOARD_FILES + 8,     SQ_J31 = 30 * BOARD_FILES + 9,     SQ_K31 = 30 * BOARD_FILES + 10,     SQ_L31 = 30 * BOARD_FILES + 11,
  SQ_M31 = 30 * BOARD_FILES + 12,     SQ_N31 = 30 * BOARD_FILES + 13,     SQ_O31 = 30 * BOARD_FILES + 14,     SQ_P31 = 30 * BOARD_FILES + 15,
  SQ_Q31 = 30 * BOARD_FILES + 16,     SQ_R31 = 30 * BOARD_FILES + 17,     SQ_S31 = 30 * BOARD_FILES + 18,     SQ_T31 = 30 * BOARD_FILES + 19,
  SQ_U31 = 30 * BOARD_FILES + 20,     SQ_V31 = 30 * BOARD_FILES + 21,     SQ_W31 = 30 * BOARD_FILES + 22,     SQ_X31 = 30 * BOARD_FILES + 23,
  SQ_Y31 = 30 * BOARD_FILES + 24,     SQ_Z31 = 30 * BOARD_FILES + 25,     SQ_AA31 = 30 * BOARD_FILES + 26,     SQ_AB31 = 30 * BOARD_FILES + 27,
  SQ_AC31 = 30 * BOARD_FILES + 28,     SQ_AD31 = 30 * BOARD_FILES + 29,     SQ_AE31 = 30 * BOARD_FILES + 30,     SQ_AF31 = 30 * BOARD_FILES + 31,
  SQ_A32 = 31 * BOARD_FILES + 0,     SQ_B32 = 31 * BOARD_FILES + 1,     SQ_C32 = 31 * BOARD_FILES + 2,     SQ_D32 = 31 * BOARD_FILES + 3,
  SQ_E32 = 31 * BOARD_FILES + 4,     SQ_F32 = 31 * BOARD_FILES + 5,     SQ_G32 = 31 * BOARD_FILES + 6,     SQ_H32 = 31 * BOARD_FILES + 7,
  SQ_I32 = 31 * BOARD_FILES + 8,     SQ_J32 = 31 * BOARD_FILES + 9,     SQ_K32 = 31 * BOARD_FILES + 10,     SQ_L32 = 31 * BOARD_FILES + 11,
  SQ_M32 = 31 * BOARD_FILES + 12,     SQ_N32 = 31 * BOARD_FILES + 13,     SQ_O32 = 31 * BOARD_FILES + 14,     SQ_P32 = 31 * BOARD_FILES + 15,
  SQ_Q32 = 31 * BOARD_FILES + 16,     SQ_R32 = 31 * BOARD_FILES + 17,     SQ_S32 = 31 * BOARD_FILES + 18,     SQ_T32 = 31 * BOARD_FILES + 19,
  SQ_U32 = 31 * BOARD_FILES + 20,     SQ_V32 = 31 * BOARD_FILES + 21,     SQ_W32 = 31 * BOARD_FILES + 22,     SQ_X32 = 31 * BOARD_FILES + 23,
  SQ_Y32 = 31 * BOARD_FILES + 24,     SQ_Z32 = 31 * BOARD_FILES + 25,     SQ_AA32 = 31 * BOARD_FILES + 26,     SQ_AB32 = 31 * BOARD_FILES + 27,
  SQ_AC32 = 31 * BOARD_FILES + 28,     SQ_AD32 = 31 * BOARD_FILES + 29,     SQ_AE32 = 31 * BOARD_FILES + 30,     SQ_AF32 = 31 * BOARD_FILES + 31,
  SQ_A33 = 32 * BOARD_FILES + 0,     SQ_B33 = 32 * BOARD_FILES + 1,     SQ_C33 = 32 * BOARD_FILES + 2,     SQ_D33 = 32 * BOARD_FILES + 3,
  SQ_E33 = 32 * BOARD_FILES + 4,     SQ_F33 = 32 * BOARD_FILES + 5,     SQ_G33 = 32 * BOARD_FILES + 6,     SQ_H33 = 32 * BOARD_FILES + 7,
  SQ_I33 = 32 * BOARD_FILES + 8,     SQ_J33 = 32 * BOARD_FILES + 9,     SQ_K33 = 32 * BOARD_FILES + 10,     SQ_L33 = 32 * BOARD_FILES + 11,
  SQ_M33 = 32 * BOARD_FILES + 12,     SQ_N33 = 32 * BOARD_FILES + 13,     SQ_O33 = 32 * BOARD_FILES + 14,     SQ_P33 = 32 * BOARD_FILES + 15,
  SQ_Q33 = 32 * BOARD_FILES + 16,     SQ_R33 = 32 * BOARD_FILES + 17,     SQ_S33 = 32 * BOARD_FILES + 18,     SQ_T33 = 32 * BOARD_FILES + 19,
  SQ_U33 = 32 * BOARD_FILES + 20,     SQ_V33 = 32 * BOARD_FILES + 21,     SQ_W33 = 32 * BOARD_FILES + 22,     SQ_X33 = 32 * BOARD_FILES + 23,
  SQ_Y33 = 32 * BOARD_FILES + 24,     SQ_Z33 = 32 * BOARD_FILES + 25,     SQ_AA33 = 32 * BOARD_FILES + 26,     SQ_AB33 = 32 * BOARD_FILES + 27,
  SQ_AC33 = 32 * BOARD_FILES + 28,     SQ_AD33 = 32 * BOARD_FILES + 29,     SQ_AE33 = 32 * BOARD_FILES + 30,     SQ_AF33 = 32 * BOARD_FILES + 31,
  SQ_A34 = 33 * BOARD_FILES + 0,     SQ_B34 = 33 * BOARD_FILES + 1,     SQ_C34 = 33 * BOARD_FILES + 2,     SQ_D34 = 33 * BOARD_FILES + 3,
  SQ_E34 = 33 * BOARD_FILES + 4,     SQ_F34 = 33 * BOARD_FILES + 5,     SQ_G34 = 33 * BOARD_FILES + 6,     SQ_H34 = 33 * BOARD_FILES + 7,
  SQ_I34 = 33 * BOARD_FILES + 8,     SQ_J34 = 33 * BOARD_FILES + 9,     SQ_K34 = 33 * BOARD_FILES + 10,     SQ_L34 = 33 * BOARD_FILES + 11,
  SQ_M34 = 33 * BOARD_FILES + 12,     SQ_N34 = 33 * BOARD_FILES + 13,     SQ_O34 = 33 * BOARD_FILES + 14,     SQ_P34 = 33 * BOARD_FILES + 15,
  SQ_Q34 = 33 * BOARD_FILES + 16,     SQ_R34 = 33 * BOARD_FILES + 17,     SQ_S34 = 33 * BOARD_FILES + 18,     SQ_T34 = 33 * BOARD_FILES + 19,
  SQ_U34 = 33 * BOARD_FILES + 20,     SQ_V34 = 33 * BOARD_FILES + 21,     SQ_W34 = 33 * BOARD_FILES + 22,     SQ_X34 = 33 * BOARD_FILES + 23,
  SQ_Y34 = 33 * BOARD_FILES + 24,     SQ_Z34 = 33 * BOARD_FILES + 25,     SQ_AA34 = 33 * BOARD_FILES + 26,     SQ_AB34 = 33 * BOARD_FILES + 27,
  SQ_AC34 = 33 * BOARD_FILES + 28,     SQ_AD34 = 33 * BOARD_FILES + 29,     SQ_AE34 = 33 * BOARD_FILES + 30,     SQ_AF34 = 33 * BOARD_FILES + 31,
  SQ_A35 = 34 * BOARD_FILES + 0,     SQ_B35 = 34 * BOARD_FILES + 1,     SQ_C35 = 34 * BOARD_FILES + 2,     SQ_D35 = 34 * BOARD_FILES + 3,
  SQ_E35 = 34 * BOARD_FILES + 4,     SQ_F35 = 34 * BOARD_FILES + 5,     SQ_G35 = 34 * BOARD_FILES + 6,     SQ_H35 = 34 * BOARD_FILES + 7,
  SQ_I35 = 34 * BOARD_FILES + 8,     SQ_J35 = 34 * BOARD_FILES + 9,     SQ_K35 = 34 * BOARD_FILES + 10,     SQ_L35 = 34 * BOARD_FILES + 11,
  SQ_M35 = 34 * BOARD_FILES + 12,     SQ_N35 = 34 * BOARD_FILES + 13,     SQ_O35 = 34 * BOARD_FILES + 14,     SQ_P35 = 34 * BOARD_FILES + 15,
  SQ_Q35 = 34 * BOARD_FILES + 16,     SQ_R35 = 34 * BOARD_FILES + 17,     SQ_S35 = 34 * BOARD_FILES + 18,     SQ_T35 = 34 * BOARD_FILES + 19,
  SQ_U35 = 34 * BOARD_FILES + 20,     SQ_V35 = 34 * BOARD_FILES + 21,     SQ_W35 = 34 * BOARD_FILES + 22,     SQ_X35 = 34 * BOARD_FILES + 23,
  SQ_Y35 = 34 * BOARD_FILES + 24,     SQ_Z35 = 34 * BOARD_FILES + 25,     SQ_AA35 = 34 * BOARD_FILES + 26,     SQ_AB35 = 34 * BOARD_FILES + 27,
  SQ_AC35 = 34 * BOARD_FILES + 28,     SQ_AD35 = 34 * BOARD_FILES + 29,     SQ_AE35 = 34 * BOARD_FILES + 30,     SQ_AF35 = 34 * BOARD_FILES + 31,
  SQ_A36 = 35 * BOARD_FILES + 0,     SQ_B36 = 35 * BOARD_FILES + 1,     SQ_C36 = 35 * BOARD_FILES + 2,     SQ_D36 = 35 * BOARD_FILES + 3,
  SQ_E36 = 35 * BOARD_FILES + 4,     SQ_F36 = 35 * BOARD_FILES + 5,     SQ_G36 = 35 * BOARD_FILES + 6,     SQ_H36 = 35 * BOARD_FILES + 7,
  SQ_I36 = 35 * BOARD_FILES + 8,     SQ_J36 = 35 * BOARD_FILES + 9,     SQ_K36 = 35 * BOARD_FILES + 10,     SQ_L36 = 35 * BOARD_FILES + 11,
  SQ_M36 = 35 * BOARD_FILES + 12,     SQ_N36 = 35 * BOARD_FILES + 13,     SQ_O36 = 35 * BOARD_FILES + 14,     SQ_P36 = 35 * BOARD_FILES + 15,
  SQ_Q36 = 35 * BOARD_FILES + 16,     SQ_R36 = 35 * BOARD_FILES + 17,     SQ_S36 = 35 * BOARD_FILES + 18,     SQ_T36 = 35 * BOARD_FILES + 19,
  SQ_U36 = 35 * BOARD_FILES + 20,     SQ_V36 = 35 * BOARD_FILES + 21,     SQ_W36 = 35 * BOARD_FILES + 22,     SQ_X36 = 35 * BOARD_FILES + 23,
  SQ_Y36 = 35 * BOARD_FILES + 24,     SQ_Z36 = 35 * BOARD_FILES + 25,     SQ_AA36 = 35 * BOARD_FILES + 26,     SQ_AB36 = 35 * BOARD_FILES + 27,
  SQ_AC36 = 35 * BOARD_FILES + 28,     SQ_AD36 = 35 * BOARD_FILES + 29,     SQ_AE36 = 35 * BOARD_FILES + 30,     SQ_AF36 = 35 * BOARD_FILES + 31,
  SQ_A37 = 36 * BOARD_FILES + 0,     SQ_B37 = 36 * BOARD_FILES + 1,     SQ_C37 = 36 * BOARD_FILES + 2,     SQ_D37 = 36 * BOARD_FILES + 3,
  SQ_E37 = 36 * BOARD_FILES + 4,     SQ_F37 = 36 * BOARD_FILES + 5,     SQ_G37 = 36 * BOARD_FILES + 6,     SQ_H37 = 36 * BOARD_FILES + 7,
  SQ_I37 = 36 * BOARD_FILES + 8,     SQ_J37 = 36 * BOARD_FILES + 9,     SQ_K37 = 36 * BOARD_FILES + 10,     SQ_L37 = 36 * BOARD_FILES + 11,
  SQ_M37 = 36 * BOARD_FILES + 12,     SQ_N37 = 36 * BOARD_FILES + 13,     SQ_O37 = 36 * BOARD_FILES + 14,     SQ_P37 = 36 * BOARD_FILES + 15,
  SQ_Q37 = 36 * BOARD_FILES + 16,     SQ_R37 = 36 * BOARD_FILES + 17,     SQ_S37 = 36 * BOARD_FILES + 18,     SQ_T37 = 36 * BOARD_FILES + 19,
  SQ_U37 = 36 * BOARD_FILES + 20,     SQ_V37 = 36 * BOARD_FILES + 21,     SQ_W37 = 36 * BOARD_FILES + 22,     SQ_X37 = 36 * BOARD_FILES + 23,
  SQ_Y37 = 36 * BOARD_FILES + 24,     SQ_Z37 = 36 * BOARD_FILES + 25,     SQ_AA37 = 36 * BOARD_FILES + 26,     SQ_AB37 = 36 * BOARD_FILES + 27,
  SQ_AC37 = 36 * BOARD_FILES + 28,     SQ_AD37 = 36 * BOARD_FILES + 29,     SQ_AE37 = 36 * BOARD_FILES + 30,     SQ_AF37 = 36 * BOARD_FILES + 31,
  SQ_A38 = 37 * BOARD_FILES + 0,     SQ_B38 = 37 * BOARD_FILES + 1,     SQ_C38 = 37 * BOARD_FILES + 2,     SQ_D38 = 37 * BOARD_FILES + 3,
  SQ_E38 = 37 * BOARD_FILES + 4,     SQ_F38 = 37 * BOARD_FILES + 5,     SQ_G38 = 37 * BOARD_FILES + 6,     SQ_H38 = 37 * BOARD_FILES + 7,
  SQ_I38 = 37 * BOARD_FILES + 8,     SQ_J38 = 37 * BOARD_FILES + 9,     SQ_K38 = 37 * BOARD_FILES + 10,     SQ_L38 = 37 * BOARD_FILES + 11,
  SQ_M38 = 37 * BOARD_FILES + 12,     SQ_N38 = 37 * BOARD_FILES + 13,     SQ_O38 = 37 * BOARD_FILES + 14,     SQ_P38 = 37 * BOARD_FILES + 15,
  SQ_Q38 = 37 * BOARD_FILES + 16,     SQ_R38 = 37 * BOARD_FILES + 17,     SQ_S38 = 37 * BOARD_FILES + 18,     SQ_T38 = 37 * BOARD_FILES + 19,
  SQ_U38 = 37 * BOARD_FILES + 20,     SQ_V38 = 37 * BOARD_FILES + 21,     SQ_W38 = 37 * BOARD_FILES + 22,     SQ_X38 = 37 * BOARD_FILES + 23,
  SQ_Y38 = 37 * BOARD_FILES + 24,     SQ_Z38 = 37 * BOARD_FILES + 25,     SQ_AA38 = 37 * BOARD_FILES + 26,     SQ_AB38 = 37 * BOARD_FILES + 27,
  SQ_AC38 = 37 * BOARD_FILES + 28,     SQ_AD38 = 37 * BOARD_FILES + 29,     SQ_AE38 = 37 * BOARD_FILES + 30,     SQ_AF38 = 37 * BOARD_FILES + 31,
  SQ_A39 = 38 * BOARD_FILES + 0,     SQ_B39 = 38 * BOARD_FILES + 1,     SQ_C39 = 38 * BOARD_FILES + 2,     SQ_D39 = 38 * BOARD_FILES + 3,
  SQ_E39 = 38 * BOARD_FILES + 4,     SQ_F39 = 38 * BOARD_FILES + 5,     SQ_G39 = 38 * BOARD_FILES + 6,     SQ_H39 = 38 * BOARD_FILES + 7,
  SQ_I39 = 38 * BOARD_FILES + 8,     SQ_J39 = 38 * BOARD_FILES + 9,     SQ_K39 = 38 * BOARD_FILES + 10,     SQ_L39 = 38 * BOARD_FILES + 11,
  SQ_M39 = 38 * BOARD_FILES + 12,     SQ_N39 = 38 * BOARD_FILES + 13,     SQ_O39 = 38 * BOARD_FILES + 14,     SQ_P39 = 38 * BOARD_FILES + 15,
  SQ_Q39 = 38 * BOARD_FILES + 16,     SQ_R39 = 38 * BOARD_FILES + 17,     SQ_S39 = 38 * BOARD_FILES + 18,     SQ_T39 = 38 * BOARD_FILES + 19,
  SQ_U39 = 38 * BOARD_FILES + 20,     SQ_V39 = 38 * BOARD_FILES + 21,     SQ_W39 = 38 * BOARD_FILES + 22,     SQ_X39 = 38 * BOARD_FILES + 23,
  SQ_Y39 = 38 * BOARD_FILES + 24,     SQ_Z39 = 38 * BOARD_FILES + 25,     SQ_AA39 = 38 * BOARD_FILES + 26,     SQ_AB39 = 38 * BOARD_FILES + 27,
  SQ_AC39 = 38 * BOARD_FILES + 28,     SQ_AD39 = 38 * BOARD_FILES + 29,     SQ_AE39 = 38 * BOARD_FILES + 30,     SQ_AF39 = 38 * BOARD_FILES + 31,
  SQ_A40 = 39 * BOARD_FILES + 0,     SQ_B40 = 39 * BOARD_FILES + 1,     SQ_C40 = 39 * BOARD_FILES + 2,     SQ_D40 = 39 * BOARD_FILES + 3,
  SQ_E40 = 39 * BOARD_FILES + 4,     SQ_F40 = 39 * BOARD_FILES + 5,     SQ_G40 = 39 * BOARD_FILES + 6,     SQ_H40 = 39 * BOARD_FILES + 7,
  SQ_I40 = 39 * BOARD_FILES + 8,     SQ_J40 = 39 * BOARD_FILES + 9,     SQ_K40 = 39 * BOARD_FILES + 10,     SQ_L40 = 39 * BOARD_FILES + 11,
  SQ_M40 = 39 * BOARD_FILES + 12,     SQ_N40 = 39 * BOARD_FILES + 13,     SQ_O40 = 39 * BOARD_FILES + 14,     SQ_P40 = 39 * BOARD_FILES + 15,
  SQ_Q40 = 39 * BOARD_FILES + 16,     SQ_R40 = 39 * BOARD_FILES + 17,     SQ_S40 = 39 * BOARD_FILES + 18,     SQ_T40 = 39 * BOARD_FILES + 19,
  SQ_U40 = 39 * BOARD_FILES + 20,     SQ_V40 = 39 * BOARD_FILES + 21,     SQ_W40 = 39 * BOARD_FILES + 22,     SQ_X40 = 39 * BOARD_FILES + 23,
  SQ_Y40 = 39 * BOARD_FILES + 24,     SQ_Z40 = 39 * BOARD_FILES + 25,     SQ_AA40 = 39 * BOARD_FILES + 26,     SQ_AB40 = 39 * BOARD_FILES + 27,
  SQ_AC40 = 39 * BOARD_FILES + 28,     SQ_AD40 = 39 * BOARD_FILES + 29,     SQ_AE40 = 39 * BOARD_FILES + 30,     SQ_AF40 = 39 * BOARD_FILES + 31,
  SQ_A41 = 40 * BOARD_FILES + 0,     SQ_B41 = 40 * BOARD_FILES + 1,     SQ_C41 = 40 * BOARD_FILES + 2,     SQ_D41 = 40 * BOARD_FILES + 3,
  SQ_E41 = 40 * BOARD_FILES + 4,     SQ_F41 = 40 * BOARD_FILES + 5,     SQ_G41 = 40 * BOARD_FILES + 6,     SQ_H41 = 40 * BOARD_FILES + 7,
  SQ_I41 = 40 * BOARD_FILES + 8,     SQ_J41 = 40 * BOARD_FILES + 9,     SQ_K41 = 40 * BOARD_FILES + 10,     SQ_L41 = 40 * BOARD_FILES + 11,
  SQ_M41 = 40 * BOARD_FILES + 12,     SQ_N41 = 40 * BOARD_FILES + 13,     SQ_O41 = 40 * BOARD_FILES + 14,     SQ_P41 = 40 * BOARD_FILES + 15,
  SQ_Q41 = 40 * BOARD_FILES + 16,     SQ_R41 = 40 * BOARD_FILES + 17,     SQ_S41 = 40 * BOARD_FILES + 18,     SQ_T41 = 40 * BOARD_FILES + 19,
  SQ_U41 = 40 * BOARD_FILES + 20,     SQ_V41 = 40 * BOARD_FILES + 21,     SQ_W41 = 40 * BOARD_FILES + 22,     SQ_X41 = 40 * BOARD_FILES + 23,
  SQ_Y41 = 40 * BOARD_FILES + 24,     SQ_Z41 = 40 * BOARD_FILES + 25,     SQ_AA41 = 40 * BOARD_FILES + 26,     SQ_AB41 = 40 * BOARD_FILES + 27,
  SQ_AC41 = 40 * BOARD_FILES + 28,     SQ_AD41 = 40 * BOARD_FILES + 29,     SQ_AE41 = 40 * BOARD_FILES + 30,     SQ_AF41 = 40 * BOARD_FILES + 31,
  SQ_A42 = 41 * BOARD_FILES + 0,     SQ_B42 = 41 * BOARD_FILES + 1,     SQ_C42 = 41 * BOARD_FILES + 2,     SQ_D42 = 41 * BOARD_FILES + 3,
  SQ_E42 = 41 * BOARD_FILES + 4,     SQ_F42 = 41 * BOARD_FILES + 5,     SQ_G42 = 41 * BOARD_FILES + 6,     SQ_H42 = 41 * BOARD_FILES + 7,
  SQ_I42 = 41 * BOARD_FILES + 8,     SQ_J42 = 41 * BOARD_FILES + 9,     SQ_K42 = 41 * BOARD_FILES + 10,     SQ_L42 = 41 * BOARD_FILES + 11,
  SQ_M42 = 41 * BOARD_FILES + 12,     SQ_N42 = 41 * BOARD_FILES + 13,     SQ_O42 = 41 * BOARD_FILES + 14,     SQ_P42 = 41 * BOARD_FILES + 15,
  SQ_Q42 = 41 * BOARD_FILES + 16,     SQ_R42 = 41 * BOARD_FILES + 17,     SQ_S42 = 41 * BOARD_FILES + 18,     SQ_T42 = 41 * BOARD_FILES + 19,
  SQ_U42 = 41 * BOARD_FILES + 20,     SQ_V42 = 41 * BOARD_FILES + 21,     SQ_W42 = 41 * BOARD_FILES + 22,     SQ_X42 = 41 * BOARD_FILES + 23,
  SQ_Y42 = 41 * BOARD_FILES + 24,     SQ_Z42 = 41 * BOARD_FILES + 25,     SQ_AA42 = 41 * BOARD_FILES + 26,     SQ_AB42 = 41 * BOARD_FILES + 27,
  SQ_AC42 = 41 * BOARD_FILES + 28,     SQ_AD42 = 41 * BOARD_FILES + 29,     SQ_AE42 = 41 * BOARD_FILES + 30,     SQ_AF42 = 41 * BOARD_FILES + 31,
  SQ_A43 = 42 * BOARD_FILES + 0,     SQ_B43 = 42 * BOARD_FILES + 1,     SQ_C43 = 42 * BOARD_FILES + 2,     SQ_D43 = 42 * BOARD_FILES + 3,
  SQ_E43 = 42 * BOARD_FILES + 4,     SQ_F43 = 42 * BOARD_FILES + 5,     SQ_G43 = 42 * BOARD_FILES + 6,     SQ_H43 = 42 * BOARD_FILES + 7,
  SQ_I43 = 42 * BOARD_FILES + 8,     SQ_J43 = 42 * BOARD_FILES + 9,     SQ_K43 = 42 * BOARD_FILES + 10,     SQ_L43 = 42 * BOARD_FILES + 11,
  SQ_M43 = 42 * BOARD_FILES + 12,     SQ_N43 = 42 * BOARD_FILES + 13,     SQ_O43 = 42 * BOARD_FILES + 14,     SQ_P43 = 42 * BOARD_FILES + 15,
  SQ_Q43 = 42 * BOARD_FILES + 16,     SQ_R43 = 42 * BOARD_FILES + 17,     SQ_S43 = 42 * BOARD_FILES + 18,     SQ_T43 = 42 * BOARD_FILES + 19,
  SQ_U43 = 42 * BOARD_FILES + 20,     SQ_V43 = 42 * BOARD_FILES + 21,     SQ_W43 = 42 * BOARD_FILES + 22,     SQ_X43 = 42 * BOARD_FILES + 23,
  SQ_Y43 = 42 * BOARD_FILES + 24,     SQ_Z43 = 42 * BOARD_FILES + 25,     SQ_AA43 = 42 * BOARD_FILES + 26,     SQ_AB43 = 42 * BOARD_FILES + 27,
  SQ_AC43 = 42 * BOARD_FILES + 28,     SQ_AD43 = 42 * BOARD_FILES + 29,     SQ_AE43 = 42 * BOARD_FILES + 30,     SQ_AF43 = 42 * BOARD_FILES + 31,
  SQ_A44 = 43 * BOARD_FILES + 0,     SQ_B44 = 43 * BOARD_FILES + 1,     SQ_C44 = 43 * BOARD_FILES + 2,     SQ_D44 = 43 * BOARD_FILES + 3,
  SQ_E44 = 43 * BOARD_FILES + 4,     SQ_F44 = 43 * BOARD_FILES + 5,     SQ_G44 = 43 * BOARD_FILES + 6,     SQ_H44 = 43 * BOARD_FILES + 7,
  SQ_I44 = 43 * BOARD_FILES + 8,     SQ_J44 = 43 * BOARD_FILES + 9,     SQ_K44 = 43 * BOARD_FILES + 10,     SQ_L44 = 43 * BOARD_FILES + 11,
  SQ_M44 = 43 * BOARD_FILES + 12,     SQ_N44 = 43 * BOARD_FILES + 13,     SQ_O44 = 43 * BOARD_FILES + 14,     SQ_P44 = 43 * BOARD_FILES + 15,
  SQ_Q44 = 43 * BOARD_FILES + 16,     SQ_R44 = 43 * BOARD_FILES + 17,     SQ_S44 = 43 * BOARD_FILES + 18,     SQ_T44 = 43 * BOARD_FILES + 19,
  SQ_U44 = 43 * BOARD_FILES + 20,     SQ_V44 = 43 * BOARD_FILES + 21,     SQ_W44 = 43 * BOARD_FILES + 22,     SQ_X44 = 43 * BOARD_FILES + 23,
  SQ_Y44 = 43 * BOARD_FILES + 24,     SQ_Z44 = 43 * BOARD_FILES + 25,     SQ_AA44 = 43 * BOARD_FILES + 26,     SQ_AB44 = 43 * BOARD_FILES + 27,
  SQ_AC44 = 43 * BOARD_FILES + 28,     SQ_AD44 = 43 * BOARD_FILES + 29,     SQ_AE44 = 43 * BOARD_FILES + 30,     SQ_AF44 = 43 * BOARD_FILES + 31,
  SQ_A45 = 44 * BOARD_FILES + 0,     SQ_B45 = 44 * BOARD_FILES + 1,     SQ_C45 = 44 * BOARD_FILES + 2,     SQ_D45 = 44 * BOARD_FILES + 3,
  SQ_E45 = 44 * BOARD_FILES + 4,     SQ_F45 = 44 * BOARD_FILES + 5,     SQ_G45 = 44 * BOARD_FILES + 6,     SQ_H45 = 44 * BOARD_FILES + 7,
  SQ_I45 = 44 * BOARD_FILES + 8,     SQ_J45 = 44 * BOARD_FILES + 9,     SQ_K45 = 44 * BOARD_FILES + 10,     SQ_L45 = 44 * BOARD_FILES + 11,
  SQ_M45 = 44 * BOARD_FILES + 12,     SQ_N45 = 44 * BOARD_FILES + 13,     SQ_O45 = 44 * BOARD_FILES + 14,     SQ_P45 = 44 * BOARD_FILES + 15,
  SQ_Q45 = 44 * BOARD_FILES + 16,     SQ_R45 = 44 * BOARD_FILES + 17,     SQ_S45 = 44 * BOARD_FILES + 18,     SQ_T45 = 44 * BOARD_FILES + 19,
  SQ_U45 = 44 * BOARD_FILES + 20,     SQ_V45 = 44 * BOARD_FILES + 21,     SQ_W45 = 44 * BOARD_FILES + 22,     SQ_X45 = 44 * BOARD_FILES + 23,
  SQ_Y45 = 44 * BOARD_FILES + 24,     SQ_Z45 = 44 * BOARD_FILES + 25,     SQ_AA45 = 44 * BOARD_FILES + 26,     SQ_AB45 = 44 * BOARD_FILES + 27,
  SQ_AC45 = 44 * BOARD_FILES + 28,     SQ_AD45 = 44 * BOARD_FILES + 29,     SQ_AE45 = 44 * BOARD_FILES + 30,     SQ_AF45 = 44 * BOARD_FILES + 31,
  SQ_A46 = 45 * BOARD_FILES + 0,     SQ_B46 = 45 * BOARD_FILES + 1,     SQ_C46 = 45 * BOARD_FILES + 2,     SQ_D46 = 45 * BOARD_FILES + 3,
  SQ_E46 = 45 * BOARD_FILES + 4,     SQ_F46 = 45 * BOARD_FILES + 5,     SQ_G46 = 45 * BOARD_FILES + 6,     SQ_H46 = 45 * BOARD_FILES + 7,
  SQ_I46 = 45 * BOARD_FILES + 8,     SQ_J46 = 45 * BOARD_FILES + 9,     SQ_K46 = 45 * BOARD_FILES + 10,     SQ_L46 = 45 * BOARD_FILES + 11,
  SQ_M46 = 45 * BOARD_FILES + 12,     SQ_N46 = 45 * BOARD_FILES + 13,     SQ_O46 = 45 * BOARD_FILES + 14,     SQ_P46 = 45 * BOARD_FILES + 15,
  SQ_Q46 = 45 * BOARD_FILES + 16,     SQ_R46 = 45 * BOARD_FILES + 17,     SQ_S46 = 45 * BOARD_FILES + 18,     SQ_T46 = 45 * BOARD_FILES + 19,
  SQ_U46 = 45 * BOARD_FILES + 20,     SQ_V46 = 45 * BOARD_FILES + 21,     SQ_W46 = 45 * BOARD_FILES + 22,     SQ_X46 = 45 * BOARD_FILES + 23,
  SQ_Y46 = 45 * BOARD_FILES + 24,     SQ_Z46 = 45 * BOARD_FILES + 25,     SQ_AA46 = 45 * BOARD_FILES + 26,     SQ_AB46 = 45 * BOARD_FILES + 27,
  SQ_AC46 = 45 * BOARD_FILES + 28,     SQ_AD46 = 45 * BOARD_FILES + 29,     SQ_AE46 = 45 * BOARD_FILES + 30,     SQ_AF46 = 45 * BOARD_FILES + 31,
  SQ_A47 = 46 * BOARD_FILES + 0,     SQ_B47 = 46 * BOARD_FILES + 1,     SQ_C47 = 46 * BOARD_FILES + 2,     SQ_D47 = 46 * BOARD_FILES + 3,
  SQ_E47 = 46 * BOARD_FILES + 4,     SQ_F47 = 46 * BOARD_FILES + 5,     SQ_G47 = 46 * BOARD_FILES + 6,     SQ_H47 = 46 * BOARD_FILES + 7,
  SQ_I47 = 46 * BOARD_FILES + 8,     SQ_J47 = 46 * BOARD_FILES + 9,     SQ_K47 = 46 * BOARD_FILES + 10,     SQ_L47 = 46 * BOARD_FILES + 11,
  SQ_M47 = 46 * BOARD_FILES + 12,     SQ_N47 = 46 * BOARD_FILES + 13,     SQ_O47 = 46 * BOARD_FILES + 14,     SQ_P47 = 46 * BOARD_FILES + 15,
  SQ_Q47 = 46 * BOARD_FILES + 16,     SQ_R47 = 46 * BOARD_FILES + 17,     SQ_S47 = 46 * BOARD_FILES + 18,     SQ_T47 = 46 * BOARD_FILES + 19,
  SQ_U47 = 46 * BOARD_FILES + 20,     SQ_V47 = 46 * BOARD_FILES + 21,     SQ_W47 = 46 * BOARD_FILES + 22,     SQ_X47 = 46 * BOARD_FILES + 23,
  SQ_Y47 = 46 * BOARD_FILES + 24,     SQ_Z47 = 46 * BOARD_FILES + 25,     SQ_AA47 = 46 * BOARD_FILES + 26,     SQ_AB47 = 46 * BOARD_FILES + 27,
  SQ_AC47 = 46 * BOARD_FILES + 28,     SQ_AD47 = 46 * BOARD_FILES + 29,     SQ_AE47 = 46 * BOARD_FILES + 30,     SQ_AF47 = 46 * BOARD_FILES + 31,
  SQ_A48 = 47 * BOARD_FILES + 0,     SQ_B48 = 47 * BOARD_FILES + 1,     SQ_C48 = 47 * BOARD_FILES + 2,     SQ_D48 = 47 * BOARD_FILES + 3,
  SQ_E48 = 47 * BOARD_FILES + 4,     SQ_F48 = 47 * BOARD_FILES + 5,     SQ_G48 = 47 * BOARD_FILES + 6,     SQ_H48 = 47 * BOARD_FILES + 7,
  SQ_I48 = 47 * BOARD_FILES + 8,     SQ_J48 = 47 * BOARD_FILES + 9,     SQ_K48 = 47 * BOARD_FILES + 10,     SQ_L48 = 47 * BOARD_FILES + 11,
  SQ_M48 = 47 * BOARD_FILES + 12,     SQ_N48 = 47 * BOARD_FILES + 13,     SQ_O48 = 47 * BOARD_FILES + 14,     SQ_P48 = 47 * BOARD_FILES + 15,
  SQ_Q48 = 47 * BOARD_FILES + 16,     SQ_R48 = 47 * BOARD_FILES + 17,     SQ_S48 = 47 * BOARD_FILES + 18,     SQ_T48 = 47 * BOARD_FILES + 19,
  SQ_U48 = 47 * BOARD_FILES + 20,     SQ_V48 = 47 * BOARD_FILES + 21,     SQ_W48 = 47 * BOARD_FILES + 22,     SQ_X48 = 47 * BOARD_FILES + 23,
  SQ_Y48 = 47 * BOARD_FILES + 24,     SQ_Z48 = 47 * BOARD_FILES + 25,     SQ_AA48 = 47 * BOARD_FILES + 26,     SQ_AB48 = 47 * BOARD_FILES + 27,
  SQ_AC48 = 47 * BOARD_FILES + 28,     SQ_AD48 = 47 * BOARD_FILES + 29,     SQ_AE48 = 47 * BOARD_FILES + 30,     SQ_AF48 = 47 * BOARD_FILES + 31,
  SQ_NONE = BOARD_SQUARES,

  SQUARE_ZERO = 0,
  SQ_MIN = SQ_A1,
  SQUARE_NB = BOARD_SQUARES,
  SQUARE_BIT_MASK = (1 << SQUARE_BITS) - 1,
  SQ_MAX = SQUARE_NB - 1,
  SQUARE_NB_CHESS = 64,
  SQUARE_NB_SHOGI = 81,
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
  return Move((from << SQUARE_BITS) + to);
}

template<MoveType T>
inline Move make(Square from, Square to, PieceType pt = NO_PIECE_TYPE) {
  return Move((pt << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + T + (from << SQUARE_BITS) + to);
}

constexpr Move make_drop(Square to, PieceType pt_in_hand, PieceType pt_dropped) {
  return Move((pt_in_hand << (2 * SQUARE_BITS + MOVE_TYPE_BITS + PIECE_TYPE_BITS)) + (pt_dropped << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + DROP + to);
}

constexpr Move reverse_move(Move m) {
  return make_move(to_sq(m), from_sq(m));
}

template<MoveType T>
constexpr Move make_gating(Square from, Square to, PieceType pt, Square gate) {
  return Move((gate << (2 * SQUARE_BITS + MOVE_TYPE_BITS + PIECE_TYPE_BITS)) + (pt << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + T + (from << SQUARE_BITS) + to);
}

constexpr Move make_lion(Square from, int path, Square to) {
  return Move((path << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + LION + (from << SQUARE_BITS) + to);
}

constexpr Move make_hook(Square from, Square hook, Square to) {
  return Move((hook << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + HOOK + (from << SQUARE_BITS) + to);
}

constexpr Move make_double_move(Square from, Square intermediate, Square to) {
  return Move((intermediate << (2 * SQUARE_BITS + MOVE_TYPE_BITS)) + DOUBLE_MOVE + (from << SQUARE_BITS) + to);
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
