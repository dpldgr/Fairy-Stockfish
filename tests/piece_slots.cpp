// Compile/run with the same board and type-capacity defines as the engine.
#include <iostream>
#include "../src/bitboard.h"
#include "../src/tt.h"
#include "../src/nnue/features/half_ka_v2.h"
#include "../src/thread.h"

using namespace Stockfish;

uint8_t Stockfish::PopCnt16[1 << 16];

constexpr bool encoding_constants() {
    for (int pt = PAWN; pt < PIECE_TYPE_NB; ++pt)
        for (Color c : {WHITE, BLACK})
            if (type_of(make_piece(c, PieceType(pt))) != pt)
                return false;
    return CHESS_PIECES.count() == 6 && SHOGI_PIECES.count() == 8
        && (~NO_PIECE_SET).count() == PIECE_TYPE_NB
        && (piece_set(KING) & CHESS_PIECES) == piece_set(KING);
}
static_assert(encoding_constants());

int main() {
    for (int i = 1; i < (1 << 16); ++i)
        PopCnt16[i] = PopCnt16[i >> 1] + (i & 1);
    assert(popcount(AllSquares) == BOARD_SQUARES);
    assert(!(AllSquares & ~((Bitboard(1) << (BOARD_SQUARES - 1))
                           | ((Bitboard(1) << (BOARD_SQUARES - 1)) - 1))));
    for (int s = 0; s < BOARD_SQUARES; ++s)
    {
        Bitboard bit = Bitboard(1) << s;
        assert(popcount(bit) == 1 && lsb(bit) == s && msb(bit) == s);
        assert((bit >> s) == Bitboard(1));
        assert(pop_lsb(bit) == s && !bit);
    }
    Score score = make_score(-123, 456);
    assert(mg_value(score) == -123 && eg_value(score) == 456);
    assert(mg_value(score * 3) == -369 && eg_value(score * 3) == 1368);
#if BOARD_SQUARES > 640
    static_assert(!USE_CONTINUATION_HISTORY);
    static_assert(sizeof(Score) == 8);
    // No hidden multi-GiB continuation table remains in the worker layout.
    static_assert(sizeof(Thread) < sizeof(CapturePieceToHistory) + 64 * 1024 * 1024);
    score = make_score(900000, -700000);
    score += make_score(-200000, 300000);
    assert(mg_value(score) == 700000 && eg_value(score) == -400000);
    score = 3 * score / 2;
    assert(mg_value(score) == 1050000 && eg_value(score) == -600000);
    assert(mg_value(-score) == -1050000 && eg_value(-score) == 600000);
#else
    static_assert(USE_CONTINUATION_HISTORY);
    static_assert(sizeof(Score) == 4);
    static_assert(sizeof(Thread) >= 4 * sizeof(ContinuationHistory));
#endif
    PieceSet all = {};
    for (int id = 0; id < PIECE_TYPE_NB; ++id)
    {
        PieceType pt = PieceType(id);
        PieceSet singleton = piece_set(pt);
        assert(popcount(singleton) == 1 && lsb(singleton) == pt && msb(singleton) == pt);
        all |= pt;
        for (Color c : {WHITE, BLACK})
        {
            Piece pc = make_piece(c, pt);
            assert(type_of(pc) == pt);
            assert(~pc == make_piece(~c, pt));
            if (pc != NO_PIECE) assert(color_of(pc) == c);
        }
        for (Square square : {SQ_MIN, SQ_MAX})
        {
            Move drop = make_drop(square, pt, KING);
            assert(to_sq(drop) == square && from_sq(drop) == SQ_NONE);
            assert(in_hand_piece_type(drop) == pt && dropped_piece_type(drop) == KING);
            Move reverseDrop = make_drop(square, KING, pt);
            assert(in_hand_piece_type(reverseDrop) == KING && dropped_piece_type(reverseDrop) == pt);
            Move promotion = make<PROMOTION>(SQ_MIN, square, pt);
            assert(promotion_type(promotion) == pt);
            Move gate = make_gating<CASTLING>(SQ_MIN, square, pt, SQ_MAX);
            assert(gating_type(gate) == pt && gating_square(gate) == SQ_MAX);
            assert(from_sq(gate) == SQ_MIN && to_sq(gate) == square && type_of(gate) == CASTLING);
        }
    }
    Move missile = make<MISSILE>(SQ_MIN, SQ_MAX);
    assert(type_of(missile) == MISSILE && from_sq(missile) == SQ_MIN && to_sq(missile) == SQ_MAX);
    assert(!is_multi_move(missile) && !is_gating(missile) && !is_path_promotion(missile));
    assert(!is_hook(missile) && !is_double_move(missile) && !is_triple_move(missile));
    assert(promotion_type(missile) == NO_PIECE_TYPE);
    assert(all == ~NO_PIECE_SET);
    assert(popcount(all) == PIECE_TYPE_NB);
    auto descending = all;
    for (int id = 0; id < PIECE_TYPE_NB; ++id)
    {
        assert(pop_lsb(all) == id);
        assert(pop_msb(descending) == PIECE_TYPE_NB - 1 - id);
    }
    assert(!all && !descending);
    for (int path = 0; path < 32; ++path)
    {
        Move m = make_lion_dog(SQ_MIN, path, SQ_MAX);
        assert(type_of(m) == LION_DOG && lion_dog_path_index(m) == path);
        for (bool mapped : {false, true})
        {
            Move p = with_path_promotion(m, KING, mapped);
            assert(path_promotion_type(p) == KING && is_path_promotion(p));
            assert(is_path_pawn_promotion(p) == !mapped);
            assert(lion_dog_path_index(p) == path && to_sq(p) == SQ_MAX && from_sq(p) == SQ_MIN);
        }
        Move demote = with_path_promotion(m, NO_PIECE_TYPE);
        assert(is_path_demotion(demote) && !is_path_promotion(demote));
    }
    assert(hook_sq(make_hook(SQ_MIN, SQ_MAX, SQ_MIN)) == SQ_MAX);
    for (Move m : {make_hook(SQ_MIN, SQ_MAX, SQ_MIN), make_double_move(SQ_MIN, SQ_MAX, SQ_MIN)})
    {
        assert(!is_path_promotion(m) && !is_path_demotion(m));
        for (bool mapped : {false, true})
        {
            Move p = with_path_promotion(m, KING, mapped);
            assert(path_promotion_type(p) == KING && is_path_pawn_promotion(p) == !mapped);
            assert((type_of(p) == HOOK ? hook_sq(p) : double_move_sq(p)) == SQ_MAX);
            assert(from_sq(p) == SQ_MIN && to_sq(p) == SQ_MIN);
        }
        assert(is_path_demotion(with_path_promotion(m, NO_PIECE_TYPE)));
    }
    if constexpr (WIDE_MOVES)
    {
        Move m = make_triple_move(SQ_MIN, SQ_MAX, Square(SQ_MAX - 1), SQ_MIN);
        assert(is_triple_move(m) && is_multi_move(m));
        for (bool mapped : {false, true})
            for (PieceType pt : {KING, PieceType(PIECE_TYPE_NB - 1)})
            {
                Move promoted = with_path_promotion(m, pt, mapped);
                assert(path_promotion_type(promoted) == pt && is_path_pawn_promotion(promoted) == !mapped);
                assert(triple_move_sq(promoted, 0) == SQ_MAX && triple_move_sq(promoted, 1) == SQ_MAX - 1);
                assert(from_sq(promoted) == SQ_MIN && to_sq(promoted) == SQ_MIN && is_triple_move(promoted));
            }
        assert(is_path_demotion(with_path_promotion(m, NO_PIECE_TYPE)));
        assert(!is_path_promotion(m) && !is_path_demotion(m));
    }
    assert(double_move_sq(make_double_move(SQ_MIN, SQ_MAX, SQ_MIN)) == SQ_MAX);
    assert(lion_path_index(make_lion(SQ_MIN, 63, SQ_MAX)) == 63);
    assert(sizeof(TTEntry) == (sizeof(MoveStorage) == 4 ? 12 : 16));
    std::cout << BOARD_FILES << 'x' << BOARD_RANKS << " slots=" << PIECE_TYPE_NB
              << " stride=" << PIECE_COLOR_STRIDE << " move=" << sizeof(MoveStorage) * 8
              << " worker=" << sizeof(Thread) << " continuation=" << USE_CONTINUATION_HISTORY << '\n';
}
