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

#include <cstdlib>
#include <iostream>

#include "bitboard.h"
#include "misc.h"
#include "endgame.h"
#include "position.h"
#include "psqt.h"
#include "search.h"
#include "syzygy/tbprobe.h"
#include "thread.h"
#include "tt.h"
#include "uci.h"

#include "piece.h"
#include "variant.h"
#include "xboard.h"


using namespace Stockfish;

namespace {

void startup_telemetry(const char* message) {

  if (std::getenv("FSF_INIT_TELEMETRY"))
      sync_cout << "info string " << message << sync_endl;
}

} // namespace

int main(int argc, char* argv[]) {

  std::cout << engine_info() << std::endl;

  startup_telemetry("pieceMap.init(): entered");
  pieceMap.init();
  startup_telemetry("variants.init(): entered");
  variants.init();
  startup_telemetry("CommandLine::init(): entered");
  CommandLine::init(argc, argv);
  startup_telemetry("UCI::init(): entered");
  UCI::init(Options);
  startup_telemetry("Tune::init(): entered");
  Tune::init();
  startup_telemetry("PSQT::init(): entered");
  PSQT::init(variants.find(Options["UCI_Variant"])->second);
  startup_telemetry("main(): before Bitboards::init()");
  Bitboards::init();
  startup_telemetry("main(): before Position::init()");
  Position::init();
  startup_telemetry("main(): before Bitbases::init()");
  Bitbases::init();
  startup_telemetry("main(): before Endgames::init()");
  Endgames::init();
  startup_telemetry("main(): before Threads.set()");
  Threads.set(size_t(Options["Threads"]));
  startup_telemetry("main(): before Search::clear()");
  Search::clear(); // After threads are up
  startup_telemetry("main(): before Eval::NNUE::init()");
  Eval::NNUE::init();
  startup_telemetry("main(): before UCI::loop()");

  UCI::loop(argc, argv);

  Threads.set(0);
  variants.clear_all();
  pieceMap.clear_all();
  delete XBoard::stateMachine;
  return 0;
}
