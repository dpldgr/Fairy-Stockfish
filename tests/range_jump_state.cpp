// Link against matching engine objects except main.o; see range_jumps.md.
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
    // Existing Seirawan gating has a FEN-reload key mismatch even without
    // range jumping. Keep geometry, material and exact undo checks for it.
    if (!p.seirawan_gating()) assert(p.key() == fresh->key());
    assert(p.pawn_key() == fresh->pawn_key());
    if (!p.seirawan_gating()) assert(p.material_key() == fresh->material_key());
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
    int captures = 0, promotions = 0, castles = 0, drops = 0;
    MoveList<LEGAL> moves(*p);
    for (Move move : moves)
    {
        if ((!notation && p->capture(move)) || type_of(move) == MISSILE)
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
        if (type_of(move) == MISSILE)
        {
            assert(SAN::move_to_san(*p, move, NOTATION_SAN).find('!') != std::string::npos);
            TTEntry entry{};
            entry.save(p->key(), VALUE_ZERO, true, BOUND_EXACT, 4, move, VALUE_ZERO);
            assert(entry.move() == move);
        }
        captures += p->capture(move);
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
            if (expected.added & s) assert(p->piece_on(s) == expected.placements[s]);
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
              << " promotions, " << castles << " castles, " << drops << " drops" << std::endl;
}

static void verify_cycle(const std::string& name, bool expected) {
    const Variant* v = variants.at(name);
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>();
    std::deque<StateInfo> states(1);
    p->set(v, "7,k/7,l/8/1,i,6/8/8/8/R,6,K b - - 0 1", false, &states.back(), Threads.main());
    for (std::string text : {"h7h6h7", "a1a4", "h7h6h7"})
    {
        Move move = UCI::to_move(*p, text);
        assert(move != MOVE_NONE);
        states.emplace_back(); p->do_move(move, states.back());
    }
    assert(p->has_game_cycle(4) == expected);
    std::string reverse = "a4a1";
    assert((UCI::to_move(*p, reverse) != MOVE_NONE) == expected);
    std::cout << name << ": reversible-move cycle prediction " << expected << std::endl;
}

int main(int argc, char** argv) {
    pieceMap.init(); variants.init(); CommandLine::init(argc, argv); UCI::init(Options);
    PSQT::init(variants.at("chess")); Bitboards::init(); Position::init(); Bitbases::init(); Endgames::init();
    Threads.set(1); Search::clear(); Eval::useNNUE = false;
    std::istringstream configuration(R"ini(
[state]
commoner = k
piece = g:Q
piece = r:R +r:<g>
piece = v:B
piece = b:B +b:<v>
piece = p:W
piece = s:<immobile>
castling = false
rangeJumpPieces = g:Q:{k,g} r:R:{k,g,v,r,b,s} v:B:{k,g,v} b:B:{k,g,v,r,b}
prohibitedCaptures = r:s
pieceDrops = true
capturesToHand = true
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{iic} mandatory:{}
[state-royal:state]
commoner = -
king = k
extinctionValue = none
rangeJumpPieces = g:Q:{k,g} r:R:{k,g,v,r,b,s} v:B:{k,g,v} b:B:{k,g,v,r,b}
[state-native:chess]
rangeJumpPieces = r:R:{k,r,p}
[state-atomic:nocheckatomic]
rangeJumpPieces = r:R:{k,r}
[state-atomic-check:atomic]
rangeJumpPieces = r:R:{k,r}
[state-petrify:chess]
rangeJumpPieces = r:R:{k,r}
petrifyOnCaptureTypes = r
[state-wall:chess]
wallingRule = duck
rangeJumpPieces = r:R:{k,r}
[state-pawn-wall:state-wall]
rangeJumpPieces = p:R:{k,r}
[state-freeze:state]
piece = i:K
piece = f:K
freezeEffectPieces = {i}
freezeImmunePieces = {i}
burnActivePieceTypes = {f}
burnPassivePieceTypes = {f}
burnImmunePieces = {i}
[state-freeze-royal:state-native]
piece = i:K
freezeEffectPieces = {i}
[state-freeze-mutual:state-freeze]
freezeImmunePieces = {}
[state-freeze-promote:state-freeze]
promotedPieceType = p:i
promotionRegionMandatoryWhite<p> = *
promotionPolicy = optional:{} mandatory:{oi,iiq,iic}
[state-freeze-promote-immune:state-freeze-promote]
burnImmunePieces = {p}
[freeze-cycle:chess]
king = -
commoner = k
piece = i:K
piece = l:KNAD
lionMovePieces = l:FFFFFFFFFFFFFFFF
freezeEffectPieces = {i}
freezeImmunePieces = {i}
castling = false
extinctionValue = loss
extinctionPieceTypes = k
[cycle-control:freeze-cycle]
freezeEffectPieces = -
[state-missile:state]
rangeJumpPieces = r:R:{p=enemy,s=friend}
missileEffectPieces = {r}
[state-missile-promoted:state-missile]
missileEffectPieces = {r,g}
[state-missile-effects:state-missile]
piece = i:K
piece = f:K
freezeEffectPieces = {i}
freezeImmunePieces = {r,i}
burnActivePieceTypes = {f}
burnPassivePieceTypes = {f}
burnImmunePieces = {r,i,f,p}
[state-missile-native:chess]
piece = m:K
rangeJumpPieces = m:R:{p=enemy}
missileEffectPieces = {m}
[state-missile-pawn:state-native]
rangeJumpPieces = p:R:{r=enemy}
missileEffectPieces = {p}
[state-relative-royal:state-royal]
rangeJumpPieces = r:R:{s=enemy}


)ini");
    variants.parse_istream<false>(configuration);
#if ENABLE_GATING
    std::istringstream gated("[state-gate:seirawan]\nrangeJumpPieces = r:R:{k,r}\n");
    variants.parse_istream<false>(gated);
#endif
    exercise("state", "7,k/3,p,4/3,P,4/3,p,4/3,R,2,b,1/8/8/7,K w - - 0 1");
    exercise("state", "7,k/3,s,4/3,p,4/8/3,R,4/8/8/7,K[R] w - - 0 1");
    exercise("state", "7,k/8/3,+b,4/4,s,3/3,+R,4/8/8/7,K w - - 0 1");
    exercise("state-royal", "8/7,k/8/8/8/8/1,G,6/K,1,r,1,g,3 w - - 0 1");
    exercise("state-native", "4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1");
    exercise("state-native", "k3r3/8/8/3pP3/8/4P3/8/4K3 w - d6 0 1");
    exercise("state-atomic", "7k/8/3p4/3p4/3R4/8/8/7K w - - 0 1");
    exercise("state-atomic-check", "8/8/8/8/3k4/3K4/8/R7 w - - 0 1");
    exercise("state-petrify", "7k/8/8/3p4/3R4/8/8/7K w - - 0 1");
#if ENABLE_GATING
    exercise("state-gate", variants.at("state-gate")->startFen);
#endif
    exercise("state-wall", variants.at("state-wall")->startFen);
    exercise("state-pawn-wall", "7k/8/8/8/3Pp1p1/8/8/7K w - - 0 1");
    exercise("state-freeze", "7,k/8/4,f,3/3,R,4/3,I,4/8/8/7,K[P] w - - 0 1");
    exercise("state-freeze-mutual", "7,k/8/8/3,i,4/2,r,I,4/8/8/7,K w - - 0 1");
    exercise("state-freeze-royal", "k6r/6,I,1/8/8/8/8/8/7K w - - 0 1");
    exercise("state-freeze-promote", "7,k/8/8/3,P,r,3/8/8/8/7,K w - - 0 1");
    exercise("state-freeze-promote-immune", "7,k/8/4,f,3/3,p,4/3,P,4/8/8/7,K w - - 0 1");
    exercise("state-missile", "7,k/3,p,P,3/3,p,4/3,P,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("state-missile-promoted", "7,k/8/3,+b,4/4,+b,3/3,+R,4/8/8/7,K w - - 0 1");
    exercise("state-missile-effects", "7,k/8/3,p,f,3/2,*,1,i,P,2/3,R,4/8/8/7,K w - - 0 1");
    exercise("state-missile-native", "4k3/8/8/8/1,M,6/8/8/R,n,2,K,2,R w KQ - 0 1");
    exercise("state-missile-pawn", "2,p,b,3,k/4,P,3/3,P,4/8/8/8/8/7,K w - - 0 1");
    exercise("state-relative-royal", "7,k/8/8/8/8/8/3,S,4/K,2,v,2,r,1 w - - 0 1");
    verify_cycle("freeze-cycle", false);
    verify_cycle("cycle-control", true);
    Threads.set(0); variants.clear_all(); pieceMap.clear_all();
    std::cout << "Range-jump hypothetical geometry, state and undo passed" << std::endl;
}
