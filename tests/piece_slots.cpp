// Compile/run with the same board and type-capacity defines as the engine.
#include <iostream>
#include "../src/bitboard.h"
#include "../src/tt.h"
#include "../src/nnue/features/half_ka_v2.h"

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
    assert(double_move_sq(make_double_move(SQ_MIN, SQ_MAX, SQ_MIN)) == SQ_MAX);
    assert(lion_path_index(make_lion(SQ_MIN, 63, SQ_MAX)) == 63);
    assert(sizeof(TTEntry) == (sizeof(MoveStorage) == 4 ? 12 : 16));
    std::cout << BOARD_FILES << 'x' << BOARD_RANKS << " slots=" << PIECE_TYPE_NB
              << " stride=" << PIECE_COLOR_STRIDE << " move=" << sizeof(MoveStorage) * 8 << '\n';
}
