// Link against matching engine objects except main.o. Run with a debug build.
#include <cassert>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include "../src/bitboard.h"
#include "../src/endgame.h"
#include "../src/evaluate.h"
#include "../src/piece.h"
#include "../src/position.h"
#include "../src/psqt.h"
#include "../src/search.h"
#include "../src/thread.h"
#include "../src/uci.h"

using namespace Stockfish;

static std::string fen(const std::map<Square, std::string>& board) {
    std::ostringstream out;
    for (int r = RANK_MAX; r >= RANK_1; --r)
    {
        if (r != RANK_MAX) out << '/';
        int empty = 0;
        bool first = true;
        auto emit = [&](const std::string& token) { if (!first) out << ','; out << token; first = false; };
        for (int f = FILE_A; f <= FILE_MAX; ++f)
        {
            auto it = board.find(SQ(File(f), Rank(r)));
            if (it == board.end()) ++empty;
            else
            {
                if (empty) { emit(std::to_string(empty)); empty = 0; }
                emit(it->second);
            }
        }
        if (empty) emit(std::to_string(empty));
    }
    return out.str() + " w - - 0 1";
}

static void fresh(const Position& p) {
    auto copy = std::make_unique<Position>();
    auto state = std::make_unique<StateInfo>();
    copy->set(p.variant(), p.fen(false, true), false, state.get(), Threads.main());
    assert(copy->key() == p.key());
    assert(copy->pawn_key() == p.pawn_key());
    assert(copy->material_key() == p.material_key());
    assert(copy->psq_score() == p.psq_score());
    assert(copy->checkers() == p.checkers());
    for (Square s = SQ_MIN; s <= SQ_MAX; ++s)
    {
        assert(copy->piece_on(s) == p.piece_on(s));
        assert(copy->unpromoted_piece_on(s) == p.unpromoted_piece_on(s));
        assert(copy->is_promoted(s) == p.is_promoted(s));
    }
}

int main(int argc, char** argv) {
    static_assert(BOARD_SQUARES > 384);
    pieceMap.init(); variants.init(); CommandLine::init(argc, argv); UCI::init(Options);
    PSQT::init(variants.at("chess")); Bitboards::init(); Position::init();
    Bitbases::init(); Endgames::init(); Threads.set(1); Search::clear(); Eval::useNNUE = false;
    std::ostringstream text;
    text << "[large-state]\nmaxFile=" << FILE_NB << "\nmaxRank=" << RANK_NB << R"ini(
piece = k:<commoner>
piece = r:R
piece = a:K +a:<r>
piece = t:K
piece = h:R
piece = l:KNAD
piece = d:KADGH
castling = false
doubleStep = false
extinctionValue = loss
extinctionPieceTypes = k
extinctionPseudoRoyal = false
nMoveRule = 0
nFoldRule = 3
promotionRegionMandatoryWhite = *
promotionRegionMandatoryBlack = *
promotionPolicy = optional:{} mandatory:{iic}
lionMovePieces = l(FFFFFFFFFFFFFFFF)
lionDogMovePieces = d:FFFFFFFFFFFF
hookMovePieces = h:R-sR:1!
tenjikuTripleStepPieceTypes = {t}
)ini";
    std::istringstream config(text.str()); variants.parse_istream<false>(config);
    const Variant* v = variants.at("large-state"); UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>();
    auto root = std::make_unique<StateInfo>(), next = std::make_unique<StateInfo>();
    const Square near = SQ(File(FILE_MAX - 1), Rank(RANK_MAX - 1));
    std::map<Square, std::string> board = {{SQ_MIN,"K"}, {SQ(FILE_C,RANK_3),"k"}, {near,"r"}};
    size_t exercised = 0;
    for (const char* pc : {"A", "T", "H", "L", "D"})
    {
        board[SQ_MAX] = pc;
        p->set(v, fen(board), false, root.get(), Threads.main());
        const Key key = p->key(); const std::string before = p->fen(false, true);
        for (Move move : MoveList<LEGAL>(*p))
        {
            std::string notation = UCI::move(*p, move);
            assert(UCI::to_move(*p, notation) == move);
            p->do_move(move, *next); fresh(*p);
            p->undo_move(move); fresh(*p);
            assert(p->key() == key && p->fen(false, true) == before);
            ++exercised;
        }
    }
    // The normal repetition rule must survive removal of the cycle shortcut.
    board = {{SQ_MIN,"K"}, {SQ_MAX,"k"}};
    std::deque<StateInfo> states(1);
    p->set(v, fen(board), false, &states.back(), Threads.main());
    const Square whiteVia = SQ(FILE_A,RANK_2), blackVia = SQ(FILE_MAX,Rank(RANK_MAX-1));
    for (int round = 0; round < 2; ++round)
        for (Move move : {make_move(SQ_MIN,whiteVia), make_move(SQ_MAX,blackVia),
                          make_move(whiteVia,SQ_MIN), make_move(blackVia,SQ_MAX)})
        {
            assert(MoveList<LEGAL>(*p).contains(move));
            states.emplace_back(); p->do_move(move, states.back());
        }
    Value result;
    assert(p->is_optional_game_end(result, 0) && result == VALUE_DRAW);
#if BOARD_SQUARES > 640
    assert(!p->has_game_cycle(8));
    board = {{SQ_MIN,"K"}, {SQ_MAX,"k"}};
    for (int s = 1; s <= 120; ++s) board[Square(s)] = "R";
    p->set(v, fen(board), false, root.get(), Threads.main());
    assert(mg_value(p->psq_score()) > 32767 && eg_value(p->psq_score()) > 32767);
    Value eval = Eval::evaluate(*p);
    assert(eval > VALUE_DRAW && eval < VALUE_TB_WIN_IN_MAX_PLY);
    fresh(*p);
#endif
    std::cout << "PASS " << FILE_NB << 'x' << RANK_NB << ": " << exercised
              << " make/undo/reload routes; repetition; evaluation; worker=" << sizeof(Thread) << std::endl;
    Threads.set(0); variants.clear_all();
}
