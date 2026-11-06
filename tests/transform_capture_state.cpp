// Link against matching engine objects except main.o; see transform_on_capture.md.
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
#include "../src/tt.h"
#include "../src/apiutil.h"

using namespace Stockfish;

static void verify_fresh(const Position& p) {
    auto fresh = std::make_unique<Position>();
    auto state = std::make_unique<StateInfo>();
    fresh->set(p.variant(), p.fen(false, true), p.is_chess960(), state.get(), Threads.main());
    if (p.key() != fresh->key())
        std::cerr << "FEN reload key mismatch: " << p.fen(false, true) << std::endl;
    assert(p.key() == fresh->key());
    assert(p.pawn_key() == fresh->pawn_key());
    assert(p.material_key() == fresh->material_key());
    assert(p.psq_score() == fresh->psq_score());
    assert(p.checkers() == fresh->checkers());
    for (Color c : {WHITE, BLACK}) assert(p.frozen_pieces(c) == fresh->frozen_pieces(c));
    for (Color c : {WHITE, BLACK})
    {
        assert(p.non_pawn_material(c) == fresh->non_pawn_material(c));
        for (PieceSet ps = p.piece_types(); ps;)
        {
            PieceType pt = pop_lsb(ps);
            assert(p.pieces(c, pt) == fresh->pieces(c, pt));
            assert(p.count(c, pt) == fresh->count(c, pt));
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

static void exercise(const std::string& name, const std::string& fen) {
    const Variant* v = variants.at(name);
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>();
    auto root = std::make_unique<StateInfo>(), next = std::make_unique<StateInfo>();
    p->set(v, fen, false, root.get(), Threads.main());
    const std::string before = p->fen(false, true);
    Key key = p->key();
    bool notation = false;
    int captures = 0, transformations = 0, promotions = 0, castles = 0, drops = 0;
    MoveList<LEGAL> moves(*p);
    for (Move move : moves)
    {
        if ((!notation && p->capture(move)) || p->contagious_promotion_type(move))
        {
            for (Protocol protocol : {UCI_GENERAL, USI})
            {
                CurrentProtocol = protocol;
                std::string text = UCI::move(*p, move);
                assert(UCI::to_move(*p, text) == move);
            }
            CurrentProtocol = UCI_GENERAL;
            notation = true;
        }
        if (p->contagious_promotion_type(move))
        {
            assert(p->capture_or_burn(move) && p->capture_or_promotion(move));
            assert(SAN::move_to_san(*p, move, NOTATION_SAN).find('=') != std::string::npos);
            assert(SAN::move_to_san(*p, move, NOTATION_SAN).find('!') == std::string::npos);
            TTEntry entry{};
            entry.save(p->key(), VALUE_ZERO, true, BOUND_EXACT, 4, move, VALUE_ZERO);
            assert(entry.move() == move);
        }
        captures += p->capture(move);
        transformations += bool(p->contagious_promotion_type(move));
        promotions += type_of(move) == PIECE_PROMOTION || type_of(move) == PROMOTION;
        castles += type_of(move) == CASTLING;
        drops += type_of(move) == DROP;

        assert(p->pseudo_legal(move));
        AttackView expected = p->move_attack_view(move);
        Bitboard expectedAttacks[COLOR_NB][SQUARE_NB];
        Bitboard expectedFrozen[COLOR_NB] = {expected.frozen_pieces(WHITE), expected.frozen_pieces(BLACK)};
        // Compute all queries while the base board is still the original one.
        for (Color c : {WHITE, BLACK})
            for (Bitboard targets = board_size_bb(v->maxFile, v->maxRank); targets;)
            {
                Square s = pop_lsb(targets);
                expectedAttacks[c][s] = p->attackers_to_view(s, c, expected);
            }
        bool check = p->gives_check(move);
        p->do_move(move, *next);
        assert(check == bool(p->checkers()));
        assert(expected.occupied == p->pieces());
        for (Color c : {WHITE, BLACK}) assert(expectedFrozen[c] == p->frozen_pieces(c));
        assert(expected.walls == p->state()->wallSquares);
        // After making the move, inspect stored placements/removals directly;
        // expected.pos now refers to the changed board and is not queried again.
        for (Square s = SQ_MIN; s <= SQ_MAX; ++s)
            if (expected.added & s)
            {
                assert(p->piece_on(s) == expected.placements[s]);
                assert(p->is_promoted(s) == bool(expected.promotedAdded & s));
            }
            else if (expected.removed & s) assert(p->empty(s));
        for (Color c : {WHITE, BLACK})
            for (Bitboard targets = board_size_bb(v->maxFile, v->maxRank); targets;)
            {
                Square s = pop_lsb(targets);
                if (expectedAttacks[c][s] != p->attackers_to(s, c))
                    std::cerr << name << ": attack mismatch after " << UCI::move(*p, move) << " target " << UCI::square(*p, s) << std::endl;
                assert(expectedAttacks[c][s] == p->attackers_to(s, c));
            }
        verify_fresh(*p);
        p->undo_move(move);
        assert(p->key() == key && p->fen(false, true) == before);
        verify_fresh(*p);
    }
    std::cout << name << ": " << moves.size() << " moves, " << captures << " captures, " << promotions
              << " promotions, " << transformations << " transformations, " << castles << " castles, " << drops << " drops" << std::endl;
}

int main(int argc, char** argv) {
    assert(argc == 2);
    pieceMap.init(); variants.init(); CommandLine::init(argc, argv); UCI::init(Options);
    PSQT::init(variants.at("chess")); Bitboards::init(); Position::init(); Bitbases::init(); Endgames::init();
    Threads.set(1); Search::clear(); Eval::useNNUE = false;
    variants.parse<false>(argv[1]);
    for (std::string name : {"transform", "transform-first", "transform-last", "transform-immune", "transform-limit"})
    {
        exercise(name, "7,k/3,ds,4/3,bs,4/3,dv,4/3,LD,4/8/8/7,K w - - 0 1");
        exercise(name, "7,k/8/5,ds,2/4,dv,3/3,L,4/8/8/7,K w - - 0 1");
    }
    exercise("transform", "7,k/8/8/4,ds,3/3,+P,4/8/8/7,K w - - 0 1");
    exercise("transform", "7,k/8/8/3,dv,4/3,TK,4/8/8/7,K w - - 0 1");
    exercise("transform-limit", "7,k/8/8/3,dv,4/3,G,4/8/8/7,K w - - 0 1");
    exercise("transform-flip", "7,k/8/8/4,ds,3/3,+P,4/8/8/7,K w - - 0 1");
    exercise("transform-flip", "7,k/8/8/4,ds,3/3,TK~,4/8/8/7,K w - - 0 1");
    exercise("transform", "7,k/8/3,dv,1,ds,2/8/3,H,4/8/8/7,K w - - 0 1");
    exercise("transform", "7,k/8/8/8/3,Z,dv,ds,2/8/8/7,K w - - 0 1");
    exercise("transform-ep", "7,k/8/8/3,O,o,3/8/8/8/7,K w - e6 0 1");
    exercise("transform-ep", "7,k/8/4,dv,3/3,O,4/8/8/8/7,K w - - 0 1");
    exercise("transform-atomic", "7,k/8/8/3,dv,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("transform-pawn-result", "7,k/8/8/3,dv,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("transform-pawn-result", "7,k/8/8/4,dv,3/3,O,4/8/8/7,K w - - 0 1");
    exercise("transform-hand", "7,k/8/8/3,x,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("transform-range", "7,k/3,ds,4/8/3,dv,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("transform-burn", "7,k/8/8/3,dv,ds,3/3,R,4/8/8/7,K w - - 0 1");
    exercise("transform-passive", "7,k/8/8/3,dv,r,3/3,R,4/8/8/7,K w - - 0 1");
    exercise("transform-promote-burn", "7,k/8/8/3,dv,x,3/3,P,4/8/8/7,K w - - 0 1");
    exercise("transform-promote-burn", "7,k/8/3,ds,4/3,dv,x,3/3,LD,4/8/8/7,K w - - 0 1");
    exercise("transform-freeze", "7,k/8/8/3,dv,x,3/3,P,4/8/8/7,K w - - 0 1");
    exercise("transform-native", "4,k,3/8/8/8/3,X,dv,3/8/8/7,K w - - 0 1");
    if (variants.count("transform-area"))
        exercise("transform-area", "7,k/3,dv,4/8/8/3,A,4/8/8/7,K w - - 0 1");
    if (variants.count("transform-high"))
        exercise("transform-high", "7,k/8/8/3,dv,4/3,R,4/8/8/7,K w - - 0 1");
    Threads.set(0); variants.clear_all(); pieceMap.clear_all();
}
