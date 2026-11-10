// Link against engine objects except main.o; see uci_verbosity.md.
#include <cassert>
#include <iostream>
#include <regex>
#include <sstream>
#include "../src/bitboard.h"
#include "../src/endgame.h"
#include "../src/evaluate.h"
#include "../src/piece.h"
#include "../src/position.h"
#include "../src/psqt.h"
#include "../src/search.h"
#include "../src/thread.h"
#include "../src/timeman.h"
#include "../src/uci.h"
#include "../src/variant.h"

using namespace Stockfish;
namespace Stockfish::Tablebases { extern bool RootInTB; }

template<class F> static std::string capture(F action) {
    std::ostringstream out;
    std::streambuf* previous = std::cout.rdbuf(out.rdbuf());
    action();
    std::cout.rdbuf(previous);
    return out.str();
}

int main(int argc, char** argv) {
    pieceMap.init(); variants.init(); CommandLine::init(argc, argv); UCI::init(Options);
    PSQT::init(variants.at("chess")); Bitboards::init(); Position::init(); Bitbases::init(); Endgames::init();
    Threads.set(1); Search::clear(); Eval::useNNUE = false;
    MainThread* main = Threads.main();
    main->rootPos.set(variants.at("chess"), variants.at("chess")->startFen, false, &main->rootState, main);
    std::string text = "e2e4";
    Move move = UCI::to_move(main->rootPos, text);
    assert(move != MOVE_NONE);
    main->rootMoves.emplace_back(move);
    main->rootMoves[0].score = VALUE_ZERO;
    main->rootMoves[0].selDepth = 1;
    main->pvIdx = 0;
    main->nodes = 4096; main->tbHits = 7;
    Search::Limits = Search::LimitsType();
    Search::Limits.startTime = now();
    Time.init(main->rootPos, Search::Limits, WHITE, 0);
    CurrentProtocol = UCI_GENERAL;
    Threads.stop = false;

    assert(int(Options["UCI_Verbosity"]) == 3);
    Options["UCI_Verbosity"] = std::string("2");
    Options["UCI_Verbosity"] = std::string("0");
    assert(int(Options["UCI_Verbosity"]) == 2);
    Options["UCI_Verbosity"] = std::string("4");
    assert(int(Options["UCI_Verbosity"]) == 2);

    for (int level : {1, 2})
    {
        main->uciVerbosity = level;
        std::string line = capture([&] { main->report_currmove(main->rootPos, move, 2, 5); });
        assert(line == "info depth 2 currmove e2e4 currmovenumber 5\n");
        main->lastSearchInfoTime = now() - 16000; main->callsCnt = 0;
        assert(capture([&] { main->check_time(); }).empty());
    }
    main->uciVerbosity = 3;
    std::string line = capture([&] { main->report_currmove(main->rootPos, move, 2, 5); });
    assert(std::regex_match(line, std::regex("info depth 2 currmove e2e4 currmovenumber 5 nodes 4096 nps [0-9]+ hashfull [0-9]+ tbhits 7 time [0-9]+\\n")));
    main->lastSearchInfoTime = now() - 14000; main->callsCnt = 0;
    assert(capture([&] { main->check_time(); }).empty());
    main->lastSearchInfoTime = now() - 16000; main->callsCnt = 0;
    line = capture([&] { main->check_time(); });
    assert(std::regex_match(line, std::regex("info nodes 4096 nps [0-9]+ hashfull [0-9]+ tbhits 7 time [0-9]+\\n")));
    assert(now() - main->lastSearchInfoTime < 1000);
    main->callsCnt = 0;
    assert(capture([&] { main->check_time(); }).empty());

    // Both kinds of existing search reports suppress the next heartbeat.
    main->lastSearchInfoTime = now() - 16000;
    capture([&] { main->report_currmove(main->rootPos, move, 2, 5); });
    main->callsCnt = 0;
    assert(capture([&] { main->check_time(); }).empty());
    main->lastSearchInfoTime = now() - 16000;
    line = capture([&] { main->report_pv(main->rootPos, 1, -VALUE_INFINITE, VALUE_INFINITE); });
    assert(line.find("info depth 1 seldepth 1 multipv 1 score cp 0") == 0);
    main->callsCnt = 0;
    assert(capture([&] { main->check_time(); }).empty());

    // Wall-clock liveness is independent of the nodes-as-time clock.
    Search::Limits.npmsec = 1;
    main->lastSearchInfoTime = now() - 16000; main->callsCnt = 0;
    line = capture([&] { main->check_time(); });
    assert(line.find("info nodes 4096 ") == 0 && line.find(" time 4097\n") != std::string::npos);
    Search::Limits.npmsec = 0;
    Tablebases::RootInTB = true;
    line = capture([&] { main->report_currmove(main->rootPos, move, 2, 5); });
    assert(line.find(" tbhits 8 ") != std::string::npos);
    Tablebases::RootInTB = false;

    for (Protocol protocol : {USI, UCCI, UCI_CYCLONE})
    {
        CurrentProtocol = protocol;
        main->lastSearchInfoTime = now() - 16000; main->callsCnt = 0;
        assert(capture([&] { main->check_time(); }).find("info nodes 4096 ") == 0);
    }
    CurrentProtocol = XBOARD;
    main->lastSearchInfoTime = now() - 16000; main->callsCnt = 0;
    assert(capture([&] { main->check_time(); }).empty());
    CurrentProtocol = UCI_GENERAL; Threads.stop = true;
    main->lastSearchInfoTime = now() - 16000; main->callsCnt = 0;
    assert(capture([&] { main->check_time(); }).empty());
    Threads.set(0); variants.clear_all(); pieceMap.clear_all();
    std::cout << "Verbosity formatting, heartbeat suppression, clocks and protocol guards passed\n";
}
