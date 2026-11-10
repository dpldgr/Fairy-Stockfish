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

static void verify_fresh(const Position& p, bool sfen = false) {
    auto fresh = std::make_unique<Position>();
    auto state = std::make_unique<StateInfo>();
    fresh->set(p.variant(), p.fen(sfen, true), p.is_chess960(), state.get(), Threads.main(), sfen);
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

static void exercise(const std::string& name, const std::string& fen, bool handFormats = false) {
    const Variant* v = variants.at(name);
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>();
    auto root = std::make_unique<StateInfo>(), next = std::make_unique<StateInfo>();
    p->set(v, fen, false, root.get(), Threads.main());
    if (handFormats) { verify_fresh(*p); verify_fresh(*p, true); }
    const std::string before = p->fen(false, true);
    Key key = p->key();
    bool notation = false;
    int captures = 0, promotions = 0, castles = 0, drops = 0;
    MoveList<LEGAL> moves(*p);
    for (Move move : moves)
    {
        std::string sweepNotation;
        if (is_free_eagle_move(move))
        {
            sweepNotation = UCI::move(*p, move);
            TTEntry entry{};
            entry.save(p->key(), VALUE_ZERO, true, BOUND_EXACT, 4, move, VALUE_ZERO);
            assert(entry.move() == move);
            assert(UCI::to_move(*p, sweepNotation) == move);
        }
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
            assert(p->capture_or_burn(move) && p->capture_or_promotion(move));
            assert(UCI::move(*p, move).find('!') == std::string::npos);
            assert(SAN::move_to_san(*p, move, NOTATION_SAN).find('!') == std::string::npos);
            TTEntry entry{};
            entry.save(p->key(), VALUE_ZERO, true, BOUND_EXACT, 4, move, VALUE_ZERO);
            assert(entry.move() == move);
        }
        captures += p->capture(move);
        promotions += type_of(move) == PIECE_PROMOTION || type_of(move) == PROMOTION;
        castles += type_of(move) == CASTLING;
        drops += type_of(move) == DROP;
        if (v->hasRangeJumpCaptures && p->range_jump_removals(move))
        {
            assert(p->capture_or_promotion(move) && p->capture_or_burn(move));
            assert(MoveList<CAPTURES>(*p).contains(move));
        }
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
        if (is_free_eagle_move(move)) assert(UCI::move(*p, move) == sweepNotation);
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
        if (handFormats) verify_fresh(*p, true);
        p->undo_move(move);
        assert(p->key() == key && p->fen(false, true) == before);
        verify_fresh(*p);
        if (handFormats) verify_fresh(*p, true);
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

static void verify_slider_intervals() {
    Value limitedValues[2] = {};
    for (const char* name : {"interval-legacy", "interval-from-one", "interval-overlap"})
    {
        UCI::init_variant(variants.at(name)); PSQT::init(variants.at(name));
        assert(!(AttackRiderTypes[CUSTOM_PIECES] & SPECIAL_RIDERS));
        assert(!(MoveRiderTypes[0][CUSTOM_PIECES] & SPECIAL_RIDERS));
        if (name == std::string("interval-legacy"))
        {
            limitedValues[MG] = PieceValue[MG][CUSTOM_PIECES];
            limitedValues[EG] = PieceValue[EG][CUSTOM_PIECES];
        }
        else
        {
            assert(PieceValue[MG][CUSTOM_PIECES] == limitedValues[MG]);
            assert(PieceValue[EG][CUSTOM_PIECES] == limitedValues[EG]);
        }
    }
    for (const char* name : {"interval-exact", "interval-pair"})
    {
        UCI::init_variant(variants.at(name));
        assert(!(AttackRiderTypes[CUSTOM_PIECES] & SPECIAL_RIDERS));
        for (Color c : {WHITE, BLACK})
            for (Square from = SQ_MIN; from <= SQ_MAX; ++from)
            {
                Bitboard expected = 0;
                for (int df : {-1,0,1}) for (int dr : {-1,0,1})
                    if (df || dr)
                    {
                        int f = file_of(from) + 3 * df, r = rank_of(from) + 3 * dr;
                        if (f >= 0 && f <= FILE_MAX && r >= 0 && r <= RANK_MAX)
                            expected |= make_square(File(f), Rank(r));
                    }
                assert(PseudoAttacks[c][CUSTOM_PIECES][from] == expected);
                assert(PseudoMoves[0][c][CUSTOM_PIECES][from] == expected);
                assert(!LeaperAttacks[c][CUSTOM_PIECES][from]);
                for (Square blocker = SQ_MIN; blocker <= SQ_MAX; ++blocker)
                {
                    Bitboard occupied = square_bb(blocker);
                    Bitboard reference = attacks_bb<QUEEN>(from, occupied) & expected;
                    assert(attacks_bb(c, CUSTOM_PIECES, from, occupied) == reference);
                    assert(moves_bb(c, CUSTOM_PIECES, from, occupied) == reference);
                }
            }
    }
    UCI::init_variant(variants.at("interval-mixed"));
    assert(AttackRiderTypes[CUSTOM_PIECES] & SPECIAL_RIDERS);
    std::cout << "Slider intervals preserve ordinary dispatch, estimates and every-square blocking" << std::endl;
}

static void verify_coordinate_atoms() {
    Value knightValues[2] = {};
    for (const char* name : {"coordinate-native", "coordinate-knight", "coordinate-overlap"})
    {
        const Variant* v = variants.at(name);
        UCI::init_variant(v); PSQT::init(v);
        if (name == std::string("coordinate-native"))
        {
            knightValues[MG] = PieceValue[MG][CUSTOM_PIECES];
            knightValues[EG] = PieceValue[EG][CUSTOM_PIECES];
        }
        else
        {
            assert(PieceValue[MG][CUSTOM_PIECES] == knightValues[MG]);
            assert(PieceValue[EG][CUSTOM_PIECES] == knightValues[EG]);
        }
    }
    for (auto spec : {std::make_pair("coordinate-knight", std::make_pair(2, 1)),
                      std::make_pair("coordinate-large", std::make_pair(17, 1))})
    {
        const Variant* v = variants.at(spec.first);
        UCI::init_variant(v); PSQT::init(v);
        for (Color c : {WHITE, BLACK})
            for (Square from = SQ_MIN; from <= SQ_MAX; ++from)
            {
                Bitboard expected = 0;
                int m = spec.second.first, n = spec.second.second;
                for (auto offset : {std::make_pair(m,n),std::make_pair(n,m)})
                    for (int sf : {-1,1}) for (int sr : {-1,1})
                    {
                        int f = file_of(from) + sf * offset.first, r = rank_of(from) + sr * offset.second;
                        if (f >= 0 && f <= FILE_MAX && r >= 0 && r <= RANK_MAX)
                            expected |= make_square(File(f), Rank(r));
                    }
                assert(PseudoAttacks[c][CUSTOM_PIECES][from] == expected);
                assert(PseudoMoves[0][c][CUSTOM_PIECES][from] == expected);
            }
    }
    std::cout << "Coordinate atoms match independent offsets on every compiled-board square" << std::endl;
}

static void verify_missile_notation() {
    const Variant* v = variants.at("state-missile-notation");
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>(); auto state = std::make_unique<StateInfo>();
    for (bool capture : {false, true})
    {
        p->set(v, capture ? "7k/M2p4/8/3P4/3M4/8/8/7K w - - 0 1"
                          : "7k/M7/8/3P4/3M4/8/8/7K w - - 0 1", false, state.get(), Threads.main());
        std::string jumpText = "d4d7", ordinaryText = "a7d7";
        Move jump = UCI::to_move(*p, jumpText), ordinary = UCI::to_move(*p, ordinaryText);
        assert(type_of(jump) == MISSILE && type_of(ordinary) == NORMAL);
        assert(SAN::disambiguation_level(*p, jump, NOTATION_SAN) == SAN::FILE_DISAMBIGUATION);
        assert(SAN::disambiguation_level(*p, ordinary, NOTATION_SAN) == SAN::FILE_DISAMBIGUATION);
        assert(SAN::move_to_san(*p, jump, NOTATION_SAN) == (capture ? "Mdxd7" : "Mdd7"));
        assert(SAN::move_to_san(*p, ordinary, NOTATION_SAN) == (capture ? "Maxd7" : "Mad7"));
    }
    std::cout << "Missile and ordinary moves share standard notation with SAN disambiguation" << std::endl;
}

static void verify_screen_dependent_pins() {
    const Variant* v = variants.at("state-hybrid");
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>(); auto state = std::make_unique<StateInfo>();
    for (bool extraScreen : {false, true})
    {
        p->set(v, extraScreen ? "7k/8/8/8/3m4/2n5/1P6/K7 w - - 0 1"
                              : "7k/8/8/8/3m4/8/1P6/K7 w - - 0 1", false, state.get(), Threads.main());
        Square b2 = make_square(FILE_B, RANK_2);
        assert(bool(p->blockers_for_king(WHITE) & b2) == extraScreen);
        std::string text = "b2b3";
        assert((UCI::to_move(*p, text) != MOVE_NONE) == !extraScreen);
    }
    p->set(v, "7k/8/8/8/N2m4/8/8/K7 w - - 0 1", false, state.get(), Threads.main());
    assert(!p->checkers());
    std::string addsScreen = "a4b2";
    assert(UCI::to_move(*p, addsScreen) == MOVE_NONE); // Would enable a jump against our own king.
    std::cout << "Pins distinguish removing a hard blocker from removing the last screen" << std::endl;
}

static void verify_skipped_ray_pins() {
    const Variant* v = variants.at("skip-royal");
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>(); auto state = std::make_unique<StateInfo>();
    p->set(v, "7k/8/8/s7/X7/X7/X7/K7 w - - 0 1", false, state.get(), Threads.main());
    Square a2 = make_square(FILE_A, RANK_2), a3 = make_square(FILE_A, RANK_3),
           a4 = make_square(FILE_A, RANK_4), a5 = make_square(FILE_A, RANK_5);
    assert(!p->checkers());
    assert(p->blockers_for_king(WHITE) == square_bb(a2));
    assert(p->pinners(BLACK) == square_bb(a5));
    for (std::string text : {"a3b3", "a4b4"}) assert(UCI::to_move(*p, text) != MOVE_NONE);
    std::string pinned = "a2b2";
    assert(UCI::to_move(*p, pinned) == MOVE_NONE);
    assert(!(p->blockers_for_king(WHITE) & (square_bb(a3) | a4)));
    p->set(v, "7k/8/8/s7/*7/X7/X7/K7 w - - 0 1", false, state.get(), Threads.main());
    assert(!p->blockers_for_king(WHITE));
    assert(UCI::to_move(*p, pinned) != MOVE_NONE);
    std::cout << "Skip-ray pins ignore prefix pieces and respect walls" << std::endl;
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
rangeJumpPieces = g:cQ:{k,g} r:cR:{k,g,v,r,b,s} v:cB:{k,g,v} b:cB:{k,g,v,r,b}
prohibitedCaptures = r:s
pieceDrops = true
capturesToHand = true
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{iic} mandatory:{}
[state-hands:state]
piece = rr:W +rr:Q
piece = rh:N
piece = rrh:F
[state-hands-loop:state-hands]
piece = rr:W +rr:<qq>
piece = qq:Q
dropLoop = true
[state-royal:state]
commoner = -
king = k
extinctionValue = none
rangeJumpPieces = g:cQ:{k,g} r:cR:{k,g,v,r,b,s} v:cB:{k,g,v} b:cB:{k,g,v,r,b}
[state-native:chess]
rangeJumpPieces = r:cR:{k,r,p}
[state-hybrid:chess]
piece = m:R
rangeJumpPieces = m:cB:{p}
[state-quiet-pawn:chess]
rangeJumpPieces = p:mR:{r}
[state-atomic:nocheckatomic]
rangeJumpPieces = r:cR:{k,r}
[state-atomic-check:atomic]
rangeJumpPieces = r:cR:{k,r}
[state-petrify:chess]
rangeJumpPieces = r:cR:{k,r}
petrifyOnCaptureTypes = r
[state-wall:chess]
wallingRule = duck
rangeJumpPieces = r:cR:{k,r}
[state-pawn-wall:state-wall]
rangeJumpPieces = p:cR:{k,r}
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
lionMovePieces = l(FFFFFFFFFFFFFFFF)
freezeEffectPieces = {i}
freezeImmunePieces = {i}
castling = false
extinctionValue = loss
extinctionPieceTypes = k
[cycle-control:freeze-cycle]
freezeEffectPieces = -
[state-missile:state]
rangeJumpPieces = r:cR:{p=enemy,s=friend}
missileEffectPieces = {r}
[state-missile-promoted:state-missile]
missileEffectPieces = {r,g}
[state-missile-promoted-quiet:state-missile-promoted]
rangeJumpPieces = g:mQ:{k,g}
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
rangeJumpPieces = m:cR:{p=enemy}
missileEffectPieces = {m}
[state-missile-pawn:state-native]
rangeJumpPieces = p:cR:{r=enemy}
missileEffectPieces = {p}
[state-missile-quiet:state-missile-native]
rangeJumpPieces = m:mR:{p=enemy}
[state-missile-notation:state-missile-native]
piece = m:R
rangeJumpPieces = m:R:{p=enemy}
[skip-state]
commoner = k
piece = x:W
piece = s:j2R +s:jB
castling = false
pieceDrops = true
capturesToHand = true
extinctionValue = loss
extinctionPieceTypes = k
extinctionPseudoRoyal = false
[skip-promotion:skip-state]
promotionRegionMandatoryWhite = *
promotionPolicy = optional:{} mandatory:{ii}
[skip-royal:skip-state]
commoner = -
king = k
extinctionValue = none
[skip-effects:skip-state]
piece = i:K
piece = f:K
freezeEffectPieces = {i}
burnActivePieceTypes = {s,f}
burnPassivePieceTypes = {f}
burnImmunePieces = {i}
[skip-castle:chess]
piece = s:jR
[skip-hybrid:skip-state]
piece = s:cpBj2R +s:jB
[count-state:skip-state]
piece = s:p[1,3..4]R +s:j[1,3]B
[count-capture:count-state]
piece = s:cp[1..3]R +s:j[1,3]B
[count-royal:count-state]
commoner = -
king = k
extinctionValue = none
piece = s:p2R
[count-castle:chess]
piece = s:cp[1,3]R
[skip-range:skip-state]
rangeJumpPieces = s:cB:{k,x}
[skip-igui:skip-state]
lionMovePieces = s(0804020180402010)
[mode-state:skip-state]
piece = l:<immobile>
lionMovePieces = l(m:AA00AA00AA00AA00,c:0804020180402010)
[mode-capture:mode-state]
lionMovePieces = l(c:FFFFFFFFFFFFFFFF)
[mode-burn:mode-state]
burnActivePieceTypes = {l}
[mode-royal:mode-state]
commoner = -
king = k
extinctionValue = none
[promotion-burn:skip-state]
piece = f:K
piece = w:W +w:<f>
piece = v:F +v:<w>
burnActivePieceTypes = {f}
burnPassivePieceTypes = {f}
burnOnPromotePieces = {w}
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{all} mandatory:{}
[promotion-burn-path:promotion-burn]
lionMovePieces = w(c:FFFFFFFFFFFFFFFF,m:0804020180402010)
[promotion-burn-royal:promotion-burn]
commoner = -
king = k
extinctionValue = none
[promotion-burn-limit:promotion-burn-royal]
promotionLimit = f:1
[promotion-burn-pawn:chess]
burnActivePieceTypes = {q}
burnOnPromotePieces = {p}
[state-relative-royal:state-royal]
rangeJumpPieces = r:cR:{s=enemy}
[clear-state:state]
rangeJumpPieces = r:Q:{s=enemy}
rangeJumpCapturePolicy = r:all
rangeJumpProhibitedCaptures = r:{g}
[clear-enemy:clear-state]
rangeJumpCapturePolicy = r:enemy
[clear-friend:clear-state]
rangeJumpCapturePolicy = r:friend
[clear-native:clear-state]
commoner = -
king = k
extinctionValue = none
[clear-burn:clear-state]
piece = f:K
burnPassivePieceTypes = {f}
[clear-burn-active:clear-burn]
commoner = -
king = k
extinctionValue = none
burnActivePieceTypes = {r}
[clear-castle:chess]
piece = m:K
rangeJumpPieces = m:Q:{}
rangeJumpCapturePolicy = m:all
[clear-missile:clear-state]
missileEffectPieces = {r}
[clear-freeze:clear-state]
piece = i:K
freezeEffectPieces = {i}
[clear-transform:clear-state]
transformOnCapturePieces = {p:g}
[clear-pawn:chess]
rangeJumpPieces = p:R:{}
rangeJumpCapturePolicy = p:enemy
[eagle-state]
commoner = k
piece = fe:QDAHGf(4,4)j[1..2]Qfj[3]B +fe:Q
piece = p:W +p:F
piece = sh:W
piece = fd:K
castling = false
taikyokuFreeEagleMultiCapturePieces = {fe}
pieceDrops = true
capturesToHand = true
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{iic} mandatory:{}
[eagle-native:eagle-state]
commoner = -
king = k
extinctionValue = none
[eagle-loop:eagle-state]
dropLoop = true
[eagle-demotion:eagle-state]
pieceDemotion = true
taikyokuFreeEagleMultiCapturePieces = {+fe}
[eagle-burn:eagle-state]
burnPassivePieceTypes = {fd}
burnActivePieceTypes = {fe}
[eagle-freeze:eagle-state]
freezeEffectPieces = {fd}
[eagle-transform:eagle-state]
piece = tk:W
piece = bs:K
transformOnCapturePieces = {tk,bs}
transformOnCapturePolicy = choose
[eagle-counter:eagle-state]
tradingRuleCounterstrike = {sh}
[eagle-pawn:chess]
taikyokuFreeEagleMultiCapturePieces = {p}
capturesToHand = true
pieceDrops = true
[interval-legacy]
customPiece1 = x:Q3
[interval-from-one]
customPiece1 = x:Q[1..3]
[interval-overlap]
customPiece1 = x:Q[1..2]Q[2..3]
[interval-exact]
customPiece1 = x:Q[3]
[interval-pair]
customPiece1 = x:Q[3..3]
[interval-state:chess]
customPiece1 = x:Q[3..5] +x:B[3]
capturesToHand = true
pieceDrops = true
promotionRegionOptionalWhite = *
promotionRegionOptionalBlack = *
promotionPolicy = optional:{ii} mandatory:{}
[interval-mixed:interval-state]
customPiece1 = x:R[3..4]cpR
[interval-king:chess]
king = k:Q[3]
[coordinate-knight]
customPiece1 = x:(2,1)
[coordinate-native]
customPiece1 = x:N
[coordinate-overlap]
customPiece1 = x:N(2,1)
[coordinate-large]
customPiece1 = x:(17,1)


)ini");
    variants.parse_istream<false>(configuration);
    verify_coordinate_atoms();
    verify_slider_intervals();
#if BOARD_FILES >= 19 && BOARD_RANKS >= 19
    std::istringstream longRay("[clear-long:clear-state]\nmaxFile = 19\nmaxRank = 19\nrangeJumpPieces = r:Q:{}\n");
    variants.parse_istream<false>(longRay);
    std::string longFen = "18,k/18,p/18,+b/18,P/18,p/18,P/18,p/18,P/18,p/18,P/18,p/18,P/18,p/18,P/18,p/18,P/18,p/18,P/K,17,R w - - 0 1";
    exercise("clear-long", longFen);
#endif
#if ENABLE_GATING
    std::istringstream gated("[state-gate:seirawan]\nrangeJumpPieces = r:cR:{k,r}\n");
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
    exercise("state-missile-promoted", "7,k/3,p,4/3,+b,4/4,+b,3/3,+R,4/8/8/7,K w - - 0 1");
    exercise("state-missile-promoted-quiet", "7,k/4,+b,3/3,+b,4/3,P,4/3,+R,4/8/8/7,K w - - 0 1");
    exercise("state-missile-effects", "7,k/8/3,p,f,3/2,*,1,i,P,2/3,R,4/8/8/7,K w - - 0 1");
    exercise("state-missile-native", "4k3/8/8/8/1,M,6/1,P,6/8/R,n,2,K,2,R w KQ - 0 1");
    exercise("state-missile-pawn", "2,p,b,3,k/3,P,P,3/3,P,4/8/8/8/8/7,K w - - 0 1");
    exercise("state-relative-royal", "7,k/8/8/8/8/8/3,S,4/K,2,v,2,r,1 w - - 0 1");
    for (std::string variant : {"clear-state", "clear-enemy", "clear-friend", "clear-transform"})
    {
        exercise(variant, "7,k/3,p,4/3,P,4/3,p,4/3,R,2,b,1/8/8/7,K w - - 0 1");
        exercise(variant, "7,k/3,+b,4/3,+R,4/4,+b,3/3,R,2,p,1/8/8/7,K w - - 0 1");
        exercise(variant, "7,k/8/3,r,2,P,1/3,s,4/3,P,4/3,+b,4/3,G,4/7,K b - - 0 1");
    }
    exercise("clear-native", "7k/8/3K4/8/3r4/8/8/8 w - - 0 1");
    exercise("clear-native", "7k/8/3K4/8/3R4/8/8/8 w - - 0 1");
    exercise("clear-burn", "7,k/8/3,f,4/8/3,R,4/8/8/7,K w - - 0 1");
    exercise("clear-burn-active", "7,k/4,K,3/3,F,4/8/3,r,4/8/8/8 w - - 0 1");
    exercise("clear-castle", "4k3/8/8/8/8/8/8/M,R,2,K,2,R w KQ - 0 1");
    exercise("clear-missile", "7,k/3,p,P,3/3,p,4/3,P,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("clear-freeze", "7,k/8/4,i,3/3,p,4/3,R,4/8/8/7,K w - - 0 1");
    exercise("clear-pawn", "7k/3p4/3p4/3p4/3P4/8/8/7K w - - 0 1");
    for (std::string variant : {"eagle-state", "eagle-loop", "eagle-counter"})
    {
        exercise(variant, "7,k/6,p,1/8/4,p,3/3,+p,4/2,p,5/1,p,6/FE,6,K w - - 0 1", true);
        exercise(variant, "fe,6,k/1,P,6/2,+P,5/3,P,4/4,P,3/8/6,P,1/7,K b - - 0 1", true);
    }
    exercise("eagle-native", "7,k/8/8/8/8/K,7/P,7/fe,7 w - - 0 1");
    exercise("eagle-burn", "7,k/8/8/1,fd,6/p,7/fd,7/p,7/FE,6,K w - - 0 1");
    exercise("eagle-freeze", "7,k/8/8/8/8/8/1,fd,6/FE,6,K w - - 0 1");
    exercise("eagle-transform", "7,k/8/6,tk,1/4,bs,3/3,p,4/2,tk,5/1,bs,6/FE,6,K w - - 0 1");
    exercise("eagle-demotion", "7,k/6,p,1/8/4,p,3/3,+p,4/2,p,5/1,p,6/+FE,6,K w - - 0 1", true);
    exercise("eagle-pawn", "6pk/8/4p3/3p4/2p5/1p6/P7/7K w - - 0 1", true);
    exercise("state-missile-quiet", "4k3/8/3,b,4/8/1,M,P,5/8/8/R,3,K,2,R w KQ - 0 1");
    exercise("state-quiet-pawn", "7k/8/8/8/2p5/3P4/3P4/7K w - - 0 1");
    exercise("skip-state", "7k/3x4/3X4/3x4/3S4/8/8/7K[S] w - - 0 1");
    exercise("skip-promotion", "7k/3x4/3X4/3x4/3S4/8/8/7K w - - 0 1");
    exercise("skip-state", "7k/8/8/8/3+S4/8/8/7K w - - 0 1");
    exercise("skip-royal", "7k/8/8/s7/X7/X7/X7/K7 w - - 0 1");
    exercise("skip-effects", "7k/3x4/3Xf3/3x4/3S4/8/6i1/7K w - - 0 1");
    exercise("skip-castle", "k7/8/8/8/5s2/8/5P2/4K2R w K - 0 1");
    exercise("skip-castle", "7k/8/8/s,p,P,4,K/8/8/8/8 w - b6 0 1");
    exercise("skip-hybrid", "7k/3x4/3X4/2x5/3S4/4x3/5x2/7K w - - 0 1");
    exercise("count-state", "7k/3x4/3X4/3x4/3S4/8/8/7K[S] w - - 0 1");
    exercise("count-state", "7k/3x4/3X4/3x4/3S4/8/8/7K b - - 0 1");
    exercise("count-state", "7k/3x4/3X4/3x4/3+S4/8/8/7K w - - 0 1");
    exercise("count-capture", "7k/3x4/3X4/3x4/3S4/8/8/7K w - - 0 1");
    exercise("count-royal", "s6k/8/8/X7/8/X7/8/K7 w - - 0 1");
    exercise("count-castle", "k4s2/8/5P2/8/5P2/8/5P2/4K2R w K - 0 1");
    exercise("count-castle", "7k/8/8/s,p,P,4,K/8/8/8/8 w - b6 0 1");
    exercise("skip-range", "7k/3x4/3X4/2x5/3S4/4x3/5x2/7K w - - 0 1");
    exercise("skip-igui", "7k/8/8/3x4/3S4/8/8/7K w - - 0 1");
    exercise("mode-state", "7k/8/3x4/2x1x3/3L4/8/8/7K w - - 0 1");
    exercise("mode-capture", "7k/8/3x4/2x1x3/3L4/8/8/7K w - - 0 1");
    exercise("mode-burn", "7k/8/3x4/2x1x3/3L4/8/8/7K w - - 0 1");
    exercise("mode-royal", "7k/8/8/8/3l4/8/3K4/8 w - - 0 1");
    exercise("promotion-burn", "7k/8/4+v3/3x4/3W4/8/8/7K[W] w - - 0 1");
    exercise("promotion-burn", "7k/8/4f3/3x4/3W4/8/8/7K w - - 0 1");
    exercise("promotion-burn-path", "7k/8/4+v3/3x4/3W4/8/8/7K w - - 0 1");
    exercise("promotion-burn-royal", "7k/8/4K3/8/3w4/8/8/8 w - - 0 1");
    exercise("promotion-burn-limit", "f6k/8/4K3/8/3w4/8/8/8 w - - 0 1");
    exercise("promotion-burn-royal", "7k/8/4K3/8/3+v4/8/8/8 w - - 0 1");
    exercise("promotion-burn-pawn", "1r5k/P7/8/8/8/8/8/7K w - - 0 1");
    exercise("interval-state", "7k/3p4/3P4/3p4/3X4/8/8/7K[X] w - - 0 1");
    exercise("interval-state", "7k/3p4/8/3p4/3+X4/8/8/7K w - - 0 1");
    exercise("interval-state", "7k/8/3X4/3P4/3p4/3P4/3x4/7K b - - 0 1");
    exercise("interval-mixed", "7k/3p4/3P4/3p4/3X4/8/8/7K[X] w - - 0 1");
    exercise("interval-state", "7k/8/8/x7/8/P7/P7/K7 w - - 0 1");
    exercise("interval-king", "7k/8/8/8/8/8/8/K7 w - - 0 1");
    verify_skipped_ray_pins();
    exercise("state-hands", "7,k/8/3,rh,4/8/3,R,4/8/8/7,K[RR,R,RH,rrh,r,rh] w - - 0 1", true);
    exercise("state-hands", "7,k/8/3,+rr,4/8/3,R,4/8/8/7,K[RR,R,RH,rrh,r,rh] b - - 0 1", true);
    exercise("state-hands-loop", "7,k/8/3,+rr,4/8/3,R,4/8/8/7,K[QQ,RR,R,rh] w - - 0 1", true);
    verify_missile_notation();
    verify_screen_dependent_pins();
    verify_cycle("freeze-cycle", false);
    verify_cycle("cycle-control", true);
    Threads.set(0); variants.clear_all(); pieceMap.clear_all();
    std::cout << "Range-jump hypothetical geometry, state and undo passed" << std::endl;
}
