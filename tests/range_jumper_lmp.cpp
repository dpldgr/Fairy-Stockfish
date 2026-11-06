// Link against matching engine objects except main.o; see range_jumps.md.
#include <algorithm>
#include <cassert>
#include <cctype>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <vector>
#include "../src/bitboard.h"
#include "../src/endgame.h"
#include "../src/evaluate.h"
#include "../src/movegen.h"
#include "../src/movepick.h"
#include "../src/piece.h"
#include "../src/position.h"
#include "../src/psqt.h"
#include "../src/search.h"
#include "../src/thread.h"
#include "../src/uci.h"
#include "../src/variant.h"

using namespace Stockfish;

static std::string fen(std::map<Square, std::string> board, Color side, std::string pocket) {
    if (side == BLACK)
    {
        for (auto& item : board)
            for (char& c : item.second) c = std::islower(c) ? std::toupper(c) : std::tolower(c);
        for (char& c : pocket) c = std::tolower(c);
    }
    std::ostringstream out;
    for (int r = 7; r >= 0; --r)
    {
        if (r != 7) out << '/';
        bool first = true;
        int empty = 0;
        auto write = [&](const std::string& text) { if (!first) out << ','; out << text; first = false; };
        for (int f = 0; f < 8; ++f)
        {
            auto it = board.find(make_square(File(f), Rank(r)));
            if (it == board.end()) ++empty;
            else
            {
                if (empty) { write(std::to_string(empty)); empty = 0; }
                write(it->second);
            }
        }
        if (empty) write(std::to_string(empty));
    }
    if (!pocket.empty()) out << '[' << pocket << ']';
    out << (side == WHITE ? " w" : " b") << " - - 0 1";
    return out.str();
}

static bool protected_type(const Position& p, Move m) {
    return bool(p.variant()->rangeJumpTypes & type_of(p.moved_piece(m)));
}

static void exercise(const char* name, const std::map<Square, std::string>& board,
                     Color side, const std::string& pocket = "") {
    const Variant* v = variants.at(name);
    UCI::init_variant(v); PSQT::init(v);
    auto p = std::make_unique<Position>();
    auto state = std::make_unique<StateInfo>();
    p->set(v, fen(board, side, pocket), false, state.get(), Threads.main());
    assert(!p->checkers());
    std::set<Move> all, captures, protectedQuiets;
    std::vector<Move> normalQuiets;
    for (Move m : MoveList<NON_EVASIONS>(*p)) all.insert(m);
    for (Move m : MoveList<CAPTURES>(*p)) captures.insert(m);
    for (Move m : MoveList<QUIETS>(*p))
        if (protected_type(*p, m)) protectedQuiets.insert(m);
        else if (!captures.count(m)) normalQuiets.push_back(m);
    assert(!normalQuiets.empty());
    if (std::string(name) == "lmp-free")
        assert(p->free_drops() && !protectedQuiets.empty());
    if (std::string(name) == "lmp-chess")
    {
        std::string text = "a2a3";
        Move bad = UCI::to_move(*p, text);
        assert(bad != MOVE_NONE && p->capture(bad) && !p->see_ge(bad));
    }

    auto th = Threads.main();
    th->mainHistory.fill(0); th->gateHistory.fill(0);
    th->lowPlyHistory.fill(0);
    auto history = std::make_unique<PieceToHistory>();
    history->fill(0);
    const PieceToHistory* cont[6] = {history.get(), history.get(), history.get(),
                                    history.get(), history.get(), history.get()};
    // Force protected quiets behind ordinary quiets; their history score must
    // not let LMP discard them when the threshold is crossed mid-list.
    for (Move m : protectedQuiets) th->mainHistory[side][from_to(m)] = -13000;

    for (int mode = 0; mode < 4; ++mode)
    {
        if (mode == 3 && protectedQuiets.size() < 2) continue;
        Move tt = MOVE_NONE, cm = MOVE_NONE, killers[2] = {MOVE_NONE, MOVE_NONE};
        std::set<Move> expected = captures;
        expected.insert(protectedQuiets.begin(), protectedQuiets.end());
        if (mode == 3)
        {
            auto it = protectedQuiets.begin();
            killers[0] = *it++;
            tt = *it;
            killers[1] = normalQuiets.front();
            cm = killers[0];
            expected.insert(killers[1]);
        }
        auto picker = std::make_unique<MovePicker>(*p, tt, 4, &th->mainHistory, &th->gateHistory,
                          &th->lowPlyHistory, &th->captureHistory, cont, cm, killers, 0);
        bool skip = mode == 1 || mode == 3;
        std::set<Move> got;
        while (Move m = picker->next_move(skip))
        {
            assert(all.count(m));
            bool inserted = got.insert(m).second;
            if (!inserted)
                std::cerr << name << ": duplicate " << UCI::move(*p, m) << std::endl;
            assert(inserted && got.size() <= all.size());
            if (mode == 2 && !captures.count(m) && !protected_type(*p, m) && !skip)
            {
                expected.insert(m);
                skip = true;
            }
        }
        if (mode == 0) expected = all;
        if (mode == 2) assert(skip);
        if (got != expected)
            std::cerr << name << " mode " << mode << ": got " << got.size()
                      << ", expected " << expected.size() << std::endl;
        assert(got == expected);
    }
    std::cout << name << (side == WHITE ? " white" : " black") << ": "
              << protectedQuiets.size() << " protected quiets, " << all.size() << " total moves" << std::endl;
}

int main(int argc, char** argv) {
    pieceMap.init(); variants.init(); CommandLine::init(argc, argv); UCI::init(Options);
    PSQT::init(variants.at("chess")); Bitboards::init(); Position::init(); Bitbases::init(); Endgames::init();
    Threads.set(1); Search::clear(); Eval::useNNUE = false;
    Threads.main()->captureHistory.fill(0);
    std::istringstream rules(R"ini(
[lmp]
maxFile = 8
maxRank = 8
piece = k:<commoner>
piece = rg:R
piece = bg:B
piece = lo:<rook>
piece = x:W
castling = false
rangeJumpPieces = rg:cR:{k} bg:mB:{k}
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
[lmp-absent:lmp]
[lmp-plain:lmp]
rangeJumpPieces = -
[lmp-path:lmp]
lionMovePieces = rg(FFFFFFFFFFFFFFFF)
[lmp-drop]
maxFile = 8
maxRank = 8
piece = k:<commoner>
piece = r:R
piece = b:F +b:<r>
castling = false
rangeJumpPieces = r:cR:{k}
pieceDrops = true
capturesToHand = true
dropPromoted = true
extinctionValue = loss
extinctionPseudoRoyal = false
extinctionPieceTypes = k
[lmp-chess:chess]
rook = lo
pawn = x
castling = false
)ini");
    variants.parse_istream<false>(rules);
    auto free = new Variant(*variants.at("lmp-drop"));
    free->capturesToHand = false;
    free->freeDrops = true;
    variants.insert({"lmp-free", free->conclude()});
#if PIECE_TYPE_CAPACITY >= 256
    std::istringstream high(R"ini(
[lmp-high:lmp]
customPiece200 = hi:R
rangeJumpPieces = hi:cR:{k}
)ini");
    variants.parse_istream<false>(high);
#endif
    auto sq = [](int f, int r) { return make_square(File(f), Rank(r)); };
    for (Color c : {WHITE, BLACK})
    {
        std::map<Square, std::string> board = {{sq(7,0),"K"}, {sq(7,7),"k"}, {sq(0,1),"LO"},
                                              {sq(3,3),"RG"}, {sq(5,2),"BG"}, {sq(4,3),"X"},
                                              {sq(3,6),"x"}};
        exercise("lmp", board, c);
        exercise("lmp-path", board, c);
        exercise("lmp-plain", board, c);
        board[sq(3,3)] = "rg"; board[sq(5,2)] = "bg";
        exercise("lmp", board, c); // Only the opponent has range jumpers.
        board.erase(sq(3,3)); board.erase(sq(5,2));
        exercise("lmp-absent", board, c);
        board = {{sq(7,0),"K"}, {sq(7,7),"k"}};
        exercise("lmp-drop", board, c, "R");
        exercise("lmp-drop", board, c, "B"); // Promoted drop's placed type.
        exercise("lmp-free", board, c);
        board = {{sq(7,0),"K"}, {sq(7,7),"k"}, {sq(0,1),"LO"},
                 {sq(0,2),"x"}, {sq(0,3),"lo"}};
        exercise("lmp-chess", board, c); // Bad captures survive skipping quiets.
#if PIECE_TYPE_CAPACITY >= 256
        board = {{sq(7,0),"K"}, {sq(7,7),"k"}};
        board[sq(3,3)] = "HI"; board[sq(0,1)] = "LO";
        exercise("lmp-high", board, c);
#endif
    }
    Threads.set(0); variants.clear_all(); pieceMap.clear_all();
}
