// Link against the engine objects except main.o, using the same build defines.
// This exercises state that protocol/perft output alone cannot validate.
#include <cassert>
#include <iostream>
#include <memory>
#include <sstream>
#include "../src/bitboard.h"
#include "../src/endgame.h"
#include "../src/evaluate.h"
#include "../src/movegen.h"
#include "../src/piece.h"
#include "../src/position.h"
#include "../src/psqt.h"
#include "../src/search.h"
#include "../src/thread.h"
#include "../src/uci.h"
#include "../src/variant.h"

using namespace Stockfish;

static void verify_state(const Position& p) {
    auto fresh = std::make_unique<Position>();
    auto state = std::make_unique<StateInfo>();
    fresh->set(p.variant(), p.fen(false, true), false, state.get(), Threads.main());
    if (p.key() != fresh->key())
        std::cerr << "Key mismatch after " << UCI::move(p, p.state()->move) << ": "
                  << p.fen(false, true) << "\n";
    assert(p.key() == fresh->key());
    assert(p.pawn_key() == fresh->pawn_key());
    assert(p.material_key() == fresh->material_key());
    assert(p.psq_score() == fresh->psq_score());
    assert(p.checkers() == fresh->checkers());
    for (Color c : {WHITE, BLACK})
    {
        assert(p.non_pawn_material(c) == fresh->non_pawn_material(c));
        for (PieceSet ps = p.piece_types(); ps;)
        {
            PieceType pt = pop_lsb(ps);
            assert(p.count(c, pt) == fresh->count(c, pt));
            assert(p.pieces(c, pt) == fresh->pieces(c, pt));
            assert(p.count_in_hand(c, pt) == fresh->count_in_hand(c, pt));
        }
    }
    for (Square s = SQ_MIN; s <= SQ_MAX; ++s)
    {
        assert(p.piece_on(s) == fresh->piece_on(s));
        assert(p.is_promoted(s) == fresh->is_promoted(s));
        assert(p.unpromoted_piece_on(s) == fresh->unpromoted_piece_on(s));
    }
}

static void exercise(const Variant* v, const std::string& fen) {
    UCI::init_variant(v);
    PSQT::init(v);
    auto p = std::make_unique<Position>();
    auto root = std::make_unique<StateInfo>();
    p->set(v, fen, false, root.get(), Threads.main());
    std::string before = p->fen(false, true);
    Key key = p->key();
    auto state = std::make_unique<StateInfo>();
    auto replyState = std::make_unique<StateInfo>();
    MoveList<LEGAL> all(*p);
    bool checkedNotation = false;
    for (Move m : all)
    {
        if (!checkedNotation && is_triple_move(m))
        {
            for (Protocol protocol : {UCI_GENERAL, USI})
            {
                CurrentProtocol = protocol;
                std::string notation = UCI::move(*p, m);
                assert(UCI::to_move(*p, notation) == m);
            }
            CurrentProtocol = UCI_GENERAL;
            checkedNotation = true;
        }
        bool check = p->gives_check(m);
        assert(p->pseudo_legal(m));
        p->do_move(m, *state);
        assert(check == bool(p->checkers()));
        verify_state(*p);
        if (!p->is_immediate_game_end())
        {
            MoveList<LEGAL> replies(*p);
            if (replies.size())
            {
                Move reply = *replies.begin();
                p->do_move(reply, *replyState);
                verify_state(*p);
                p->undo_move(reply);
                verify_state(*p);
            }
        }
        p->undo_move(m);
        assert(before == p->fen(false, true) && key == p->key());
        verify_state(*p);
    }
    std::cout << "state/undo: " << all.size() << " routes" << std::endl;
}

int main(int argc, char** argv) {
    static_assert(WIDE_MOVES, "Run state integration tests with a wide-move build");
    pieceMap.init();
    variants.init();
    CommandLine::init(argc, argv);
    UCI::init(Options);
    PSQT::init(variants.find("chess")->second);
    Bitboards::init();
    Position::init();
    Bitbases::init();
    Endgames::init();
    Threads.set(1);
    Search::clear();
    Eval::useNNUE = false;
    std::istringstream config(R"ini(
[state]
commoner = k
piece = p:<pawn>
piece = g:<gold>
piece = d:K +d:<g>
piece = a:W +a:<g>
piece = b:W +b:<g>
piece = t:<immobile>
castling = false
pieceDrops = true
capturesToHand = true
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
tenjikuTripleStepPieceTypes = {d}
burnActivePieceTypes = {d}
burnPassivePieceTypes = {d,t}
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{iic} mandatory:{}
[plain:state]
burnActivePieceTypes = {}
burnPassivePieceTypes = {}
[royal:state]
commoner = -
king = k
extinctionValue = none
[king-area:royal]
tenjikuTripleStepPieceTypes = {k,d}
[royal-pawn:royal]
tenjikuTripleStepPieceTypes = {}
burnActivePieceTypes = {p}
)ini");
    variants.parse_istream<false>(config);
    exercise(variants.find("state")->second, "7,k/3,t,4/2,+a,b,a,3/2,a,1,+b,3/3,D,4/8/8/7,K w - - 0 1");
    exercise(variants.find("state")->second, "7,k/3,+a,4/2,p,+b,a,3/8/3,D,4/8/8/7,K w - - 0 1");
    exercise(variants.find("state")->second, "7,k/8/8/4,t,3/3,+D,4/8/8/7,K w - - 0 1");
    exercise(variants.find("royal")->second, "7,k/r,7/8/1,D,6/8/8/8/K,7 w - - 0 1");
    exercise(variants.find("king-area")->second, "7,k/8/8/8/3,K,4/8/8/8 w - - 0 1");
    exercise(variants.find("royal-pawn")->second, "8/8/8/4,k,3/8/8/3,P,4/7,K b - - 0 1");
    {
        const Variant* pawnVariant = variants.find("royal-pawn")->second;
        UCI::init_variant(pawnVariant); PSQT::init(pawnVariant);
        auto pawnPosition = std::make_unique<Position>();
        auto pawnState = std::make_unique<StateInfo>();
        pawnPosition->set(pawnVariant, "8/8/8/4,k,3/8/8/3,P,4/7,K b - - 0 1", false, pawnState.get(), Threads.main());
        assert(pawnPosition->checkers() & SQ(FILE_D, RANK_2));
    }

    // TRIPLE_MOVE is an encoding with three capture slots, even though the
    // Tenjiku area generator itself stops at its first capture.
    const Variant* v = variants.find("plain")->second;
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>();
    auto root = std::make_unique<StateInfo>(), state = std::make_unique<StateInfo>();
    p->set(v, "7,k/3,+a,4/3,b,4/3,a,4/3,D,4/8/8/7,K w - - 0 1", false, root.get(), Threads.main());
    std::string before = p->fen(false, true);
    Move triple = make_triple_move(SQ(FILE_D,RANK_4), SQ(FILE_D,RANK_5), SQ(FILE_D,RANK_6), SQ(FILE_D,RANK_7));
    p->do_move(triple, *state);
    assert(p->count_in_hand(WHITE, ALL_PIECES) == 3);
    assert(p->count(BLACK, ALL_PIECES) == 1);
    verify_state(*p);
    p->undo_move(triple);
    assert(before == p->fen(false, true));
    verify_state(*p);
    Threads.set(0);
    variants.clear_all(); pieceMap.clear_all();
    std::cout << "Triple captures and full burn/area state checks passed\n";
}
