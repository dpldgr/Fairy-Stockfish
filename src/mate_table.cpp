/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#include "mate_table.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <iomanip>
#include <map>
#include <new>
#include <sstream>
#include <thread>

#include "bitboard.h"
#include "misc.h"
#include "movegen.h"
#include "piece.h"
#include "position.h"
#include "tds.hpp"
#include "thread.h"
#include "uci.h"
#include "variant.h"

namespace Stockfish {

namespace {

// Retrograde analysis of K+X versus K, as in H. G. Muller's Checkmating Applet:
// https://www.chessvariants.com/rules/checkmating-applet
// Seed terminal positions, propagate a win through any losing child, and a
// loss when every reply wins. Here both turns are explicit, with 32-bit DTM.
enum Result : uint8_t { INVALID, UNKNOWN, DRAW, WIN, LOSS };
enum Turn { STRONG, WEAK };
enum class Format { INFO, INFO_TABLE, TABLE };

struct Node {
  uint32_t distance = 0;
  uint16_t remaining = 0;
  Result result = INVALID;
};
static_assert(sizeof(Node) == 8, "Unexpected mate-table node size");

void message(const std::string& text, Format format = Format::INFO_TABLE) {
  sync_cout << (format == Format::TABLE ? "" : "info string mate-table ") << text << sync_endl;
}

bool parse_format(const std::string& text, Format& format) {
  if (text == "info") format = Format::INFO;
  else if (text == "info-table") format = Format::INFO_TABLE;
  else if (text == "table") format = Format::TABLE;
  else return false;
  return true;
}

const char* color_name(Color c) { return c == WHITE ? "white" : "black"; }

PieceType resolve_piece(const Variant* v, const std::string& symbol) {
  PieceType found = NO_PIECE_TYPE;
  const std::string name = Variant::white_symbol(symbol);
  for (PieceSet types = v->pieceTypes; types; )
  {
      PieceType pt = pop_lsb(types);
      if (   v->pieceToSymbol[make_piece(WHITE, pt)] == name
          || v->pieceToSymbolSynonyms[make_piece(WHITE, pt)] == name)
      {
          if (found != NO_PIECE_TYPE) return NO_PIECE_TYPE;
          found = pt;
      }
  }
  return found;
}

std::string unsupported(const Variant* v, PieceType pt) {
  if (!(v->pieceTypes & KING) || v->kingType != KING || !v->checking)
      return "ordinary checkmating kings are required";
  if (v->checkmateValue != -VALUE_MATE)
      return "nonstandard checkmate results are not supported";
  if (v->stalemateValue != -VALUE_MATE && v->stalemateValue != VALUE_DRAW && v->stalemateValue != VALUE_MATE)
      return "stalemate must be win, loss or draw";
  if (v->maxFile < FILE_C || v->maxRank < RANK_3 || v->maxFile > File(15) || v->maxRank > Rank(15))
      return "rectangular boards from 3x3 through 16x16 are supported";
  if (   v->extinctionValue != VALUE_NONE || v->extinctionCondition.type != EXTINCTION_CONDITION_NONE
      || v->extinctionPseudoRoyal || v->dupleCheck || v->baringRule
      || v->flagRegion[WHITE] || v->flagRegion[BLACK]
      || v->checkCounting || v->connectN || v->connectNxN || v->collinearN
      || v->materialCounting != NO_MATERIAL_COUNTING || v->adjudicateFullBoard)
      return "additional winning conditions are not supported";
  if (   v->twoBoards || v->pieceDrops || v->capturesToHand || v->freeDrops
      || v->gating || v->wallingRule != NO_WALLING || v->flipEnclosedPieces != NO_ENCLOSING
      || v->mustCapture || v->mustDrop || v->pass[WHITE] || v->pass[BLACK]
      || v->passOnStalemate[WHITE] || v->passOnStalemate[BLACK]
      || v->immobilityIllegal || v->cambodianMoves || v->diagonalLines
      || v->makpongRule || v->flyingGeneral || v->bikjangRule || v->shatarMateRule
      || v->stalematePieceCount || v->castlingWins)
      return "additional move or stalemate rules are not supported";
  if (   v->perpetualCheckIllegal || v->moveRepetitionIllegal || v->chasingRule != NO_CHASING
      || (v->nFoldRule && v->nFoldValue != VALUE_DRAW))
      return "history-dependent move or decisive repetition rules are not supported";
  if (   v->hasBurn || v->hasMissile || v->hasFreeze || v->hasContagiousCaptures
      || v->blastOnCapture || v->hasTradingRules || v->pieceDemotion
      || v->mutuallyImmuneTypes || v->petrifyOnCaptureTypes || v->petrifyBlastPieces)
      return "capture effects, trading restrictions and transformations are not supported";
  if (   v->combined_lion_mask(pt) || v->lionDogMoveSpecified[pt]
      || !v->hookMoveSpecs[pt].empty() || !v->doubleMoveSpecs[pt].empty()
      || (v->tenjikuTripleStepPieceTypes & pt) || (v->rangeJumpTypes & pt)
      || (v->taikyokuFreeEagleMultiCapturePieces & pt))
      return "multi-leg and range-jumping moves are not supported";
  if (v->startFen.substr(0, v->startFen.find(' ')).find('*') != std::string::npos)
      return "boards with walls are not supported";
  if (pt == SOLDIER || pt == JANGGI_CANNON)
      return "position-dependent built-in piece movement is not supported";
  for (Color c : {WHITE, BLACK})
  {
      if (v->mobilityRegion[c][KING]) return "restricted king regions are not supported";
      if (   (v->promotionPawnTypes[c] & (piece_set(pt) | KING))
          || v->promotedPieceType[pt] || v->promotedPieceType[KING]
          || v->prohibitedCaptures[c][pt] || v->prohibitedCaptures[c][KING])
          return "promotions or prohibited captures involving the table pieces are not supported";
  }
  const PieceInfo* piece = pieceMap.at(pt);
  for (MoveModality mode : {MODALITY_QUIET, MODALITY_CAPTURE})
      for (bool initial : {false, true})
      {
          if (   !piece->hopper[initial][mode].empty() || !piece->skipped[initial][mode].empty()
              || !piece->counted[initial][mode].empty())
              return "hoppers and skipped rays are not supported";
          for (auto step : piece->steps[initial][mode])
              if (step.second) return "lame leapers are not supported";
          if (initial && (   !piece->steps[initial][mode].empty() || !piece->slider[initial][mode].empty()
                         || !piece->coordinate[initial][mode].empty() || !piece->intervals[initial][mode].empty()
                         || piece->universal[initial][mode]))
              return "initial-move privileges are not supported";
      }
  return "";
}

struct Table {
  const Variant* variant;
  const PieceType piece;
  const Color strong;
  const std::string variantName, symbol;
  const int n;
  const uint32_t count;
  const uint64_t budget;
  std::unique_ptr<Node[]> nodes;
  std::vector<Square> squares;
  std::array<int, SQUARE_NB> squareIndex;
  std::vector<Bitboard> kings, attacks;
  std::vector<std::vector<int>> reverseQuiet;
  Bitboard board, pieceRegion;
  uint64_t legal[2] = {}, wins[2] = {}, losses[2] = {}, draws[2] = {}, mates[2] = {};
  uint32_t maximum[2] = {};
  uint64_t signature = 14695981039346656037ULL;
  std::map<uint32_t, std::array<uint64_t, 4>> histogram;
  TimePoint elapsed = 0;

  Table(const Variant* v, PieceType pt, Color c, std::string name, std::string sym, uint64_t bytes)
      : variant(v), piece(pt), strong(c), variantName(std::move(name)), symbol(std::move(sym)),
        n((int(v->maxFile) + 1) * (int(v->maxRank) + 1)), count(2 * n * n * n), budget(bytes) {}

  uint32_t index(int wk, int x, int bk, int turn) const {
    return 2 * ((wk * n + x) * n + bk) + turn;
  }

  uint64_t distinct_states() const {
    return 2 * uint64_t(n) * (n - 1) * (n - 2);
  }

  Bitboard quiet(int wk, int x, int bk) const {
    Bitboard occupied = square_bb(squares[wk]) | squares[x] | squares[bk];
    return moves_bb(strong, piece, squares[x], occupied) & pieceRegion & ~occupied;
  }

  bool build(const std::atomic_bool& cancelled, std::string& error) {
    const TimePoint started = now();
    if (cancelled.load(std::memory_order_relaxed)) return false;
    // Include the maximum queue, geometry, inverse moves and a fixed allowance
    // for metadata/histograms. Large allocations fail without throwing.
    uint64_t required = uint64_t(count) * (sizeof(Node) + sizeof(uint32_t))
                      + uint64_t(n) * n * (sizeof(Bitboard) + sizeof(int)) + 1024 * 1024;
    if (required > budget) { error = "memory budget exceeded; estimated MiB " + std::to_string((required + 1048575) / 1048576); return false; }
    nodes.reset(new (std::nothrow) Node[count]);
    std::unique_ptr<uint32_t[]> queue(new (std::nothrow) uint32_t[count]);
    if (!nodes || !queue) { error = "allocation failed"; return false; }
    board = board_size_bb(variant->maxFile, variant->maxRank);
    pieceRegion = variant->mobilityRegion[strong][piece];
    pieceRegion = pieceRegion ? pieceRegion & board : board;
    squareIndex.fill(-1);
    for (Rank r = RANK_1; r <= variant->maxRank; ++r)
        for (File f = FILE_A; f <= variant->maxFile; ++f)
        {
            Square s = make_square(f, r);
            squareIndex[s] = int(squares.size()); squares.push_back(s);
        }
    kings.resize(n); attacks.resize(n * n); reverseQuiet.resize(n);
    for (int x = 0; x < n; ++x)
    {
        if (cancelled.load(std::memory_order_relaxed)) return false;
        kings[x] = attacks_bb<KING>(squares[x]) & board;
        Bitboard destinations = moves_bb(strong, piece, squares[x], 0) & pieceRegion;
        while (destinations)
            reverseQuiet[squareIndex[pop_lsb(destinations)]].push_back(x);
        for (int wk = 0; wk < n; ++wk)
            attacks[wk * n + x] = attacks_bb(strong, piece, squares[x], square_bb(squares[wk])) & pieceRegion;
    }
    uint32_t head = 0, tail = 0;
    auto terminal = [&](uint32_t i, bool checked) {
        Node& node = nodes[i];
        if (node.remaining) return;
        node.result = checked || variant->stalemateValue < VALUE_DRAW ? LOSS
                    : variant->stalemateValue > VALUE_DRAW ? WIN : DRAW;
        if (node.result == WIN || node.result == LOSS) queue[tail++] = i;
        if (checked) ++mates[i & 1];
    };
    for (int wk = 0; wk < n; ++wk)
        for (int x = 0; x < n; ++x)
        {
            if (cancelled.load(std::memory_order_relaxed)) return false;
            if (wk == x) continue;
            for (int bk = 0; bk < n; ++bk)
            {
                if (bk == wk || bk == x || (kings[wk] & squares[bk])) continue;
                bool checked = bool(attacks[wk * n + x] & squares[bk]);
                uint32_t i = index(wk, x, bk, WEAK);
                nodes[i].result = UNKNOWN;
                // Capturing X is a legal drawing exit only when X is unguarded.
                Bitboard escapes = kings[bk] & ~kings[wk] & ~square_bb(squares[wk]);
                escapes &= ~attacks[wk * n + x] | square_bb(squares[x]);
                nodes[i].remaining = uint16_t(popcount(escapes));
                terminal(i, checked);
                // The nonmoving king cannot already be in check.
                if (checked) continue;
                --i;
                nodes[i].result = UNKNOWN;
                Bitboard kingMoves = kings[wk] & ~kings[bk] & ~(square_bb(squares[x]) | squares[bk]);
                nodes[i].remaining = uint16_t(popcount(kingMoves) + popcount(quiet(wk, x, bk)));
                terminal(i, false);
            }
        }
    TimePoint reportTime = now();
    while (head < tail)
    {
        if (!(head & 4095))
        {
            if (cancelled.load(std::memory_order_relaxed)) return false;
            if (now() - reportTime > 2000)
            {
                message("progress processed " + std::to_string(head) + " queued " + std::to_string(tail));
                reportTime = now();
            }
        }
        uint32_t i = queue[head++], tuple = i / 2;
        const Node child = nodes[i];
        int bk = tuple % n; tuple /= n;
        int x = tuple % n, wk = tuple / n;
        auto visit = [&](uint32_t parent) {
            Node& node = nodes[parent];
            if (node.result != UNKNOWN) return;
            if (child.result == LOSS) node.result = WIN;
            else if (--node.remaining == 0) node.result = LOSS;
            else return;
            // FIFO processes nondecreasing DTM: first losing child gives the
            // shortest win; last winning child gives the longest forced loss.
            node.distance = child.distance + 1;
            queue[tail++] = parent;
        };
        if ((i & 1) == STRONG)
        {
            Bitboard from = kings[bk];
            while (from) visit(index(wk, x, squareIndex[pop_lsb(from)], WEAK));
        }
        else
        {
            Bitboard from = kings[wk];
            while (from) visit(index(squareIndex[pop_lsb(from)], x, bk, STRONG));
            for (int oldX : reverseQuiet[x])
            {
                uint32_t parent = index(wk, oldX, bk, STRONG);
                if (nodes[parent].result == UNKNOWN && (quiet(wk, oldX, bk) & squares[x])) visit(parent);
            }
        }
    }
    for (uint32_t i = 0; i < count; ++i)
    {
        if (!(i & 65535) && cancelled.load(std::memory_order_relaxed)) return false;
        Node& node = nodes[i];
        int turn = i & 1;
        if (node.result == UNKNOWN) node.result = DRAW;
        // Deterministic signature of every indexed WDL/DTM record, including
        // invalid placements. Useful when independently verifying generators.
        signature = (signature ^ uint8_t(node.result)) * 1099511628211ULL;
        for (unsigned shift = 0; shift < 32; shift += 8)
            signature = (signature ^ uint8_t(node.distance >> shift)) * 1099511628211ULL;
        if (node.result == INVALID) continue;
        ++legal[turn];
        if (node.result == DRAW) ++draws[turn];
        else
        {
            (node.result == WIN ? wins[turn] : losses[turn])++;
            maximum[turn] = std::max(maximum[turn], node.distance);
            ++histogram[node.distance][2 * turn + (node.result == LOSS)];
        }
    }
    elapsed = now() - started;
    return true;
  }

  void formatted_stats(Format format) const {
    // The applet groups both turns by the number of attacking moves: a win
    // from the strong side's turn uses ceil(DTM/2), a weak-side loss floor(DTM/2).
    std::map<uint32_t, std::array<uint64_t, 2>> rows;
    rows[0] = {};
    for (const auto& item : histogram)
    {
        if (item.second[0]) rows[(item.first + 1) / 2][0] += item.second[0];
        if (item.second[3]) rows[item.first / 2][1] += item.second[3];
    }

    // Match the applet's denominator: all distinct placements, including
    // adjacent kings and other immediate king captures. Raw legal WDL summaries
    // deliberately exclude those placements.
    const uint64_t placements = distinct_states() / 2;
    const uint64_t kingCaptures = placements - legal[STRONG];
    auto percent = [&](uint64_t numerator) {
        uint64_t tenths = (1000 * numerator + placements / 2) / placements;
        return std::to_string(tenths / 10) + "." + std::to_string(tenths % 10) + "%";
    };
    const std::string matePercent = percent(wins[STRONG] + kingCaptures);
    const std::string matedPercent = percent(losses[WEAK]);
    if (format == Format::INFO)
    {
        for (const auto& row : rows)
            message("mate " + std::to_string(row.second[0]) + " mated " + std::to_string(row.second[1])
                  + " in " + std::to_string(row.first));
        message("king_captures " + std::to_string(kingCaptures));
        message("mate " + matePercent + " mated " + matedPercent + " tot");
        message("time " + std::to_string(elapsed));
        return;
    }
    auto output = [format](const std::string& text) { message(text, format); };
    size_t first = std::max(size_t(6), std::to_string(kingCaptures).size()), second = 6, third = 3;
    for (const auto& row : rows)
    {
        first = std::max(first, std::to_string(row.second[0]).size());
        second = std::max(second, std::to_string(row.second[1]).size());
        third = std::max(third, std::to_string(row.first).size());
    }
    auto line = [&](const std::string& a, const std::string& b, const std::string& c) {
        std::ostringstream out;
        out << "| " << std::setw(int(first)) << a << " | " << std::setw(int(second)) << b
            << " | " << std::setw(int(third)) << c << " |";
        output(out.str());
    };
    const std::string border = "+" + std::string(first + 2, '-') + "+" + std::string(second + 2, '-')
                             + "+" + std::string(third + 2, '-') + "+";
    output("Statistics");
    output(border);
    line("mate", "mated", "in");
    output(border);
    for (const auto& row : rows)
        line(row.first == 0 && row.second[0] == 0 ? "" : std::to_string(row.second[0]),
             std::to_string(row.second[1]), std::to_string(row.first));
    output(border);
    std::ostringstream captures;
    captures << "| " << std::setw(int(first)) << kingCaptures << " | "
             << std::setw(int(second + third + 3)) << "King capt" << " |";
    output(captures.str());
    line(matePercent, matedPercent, "tot");
    output(border);
    output("Done in " + std::to_string(elapsed) + " ms");
  }

  void stats(bool raw = false, Format format = Format::INFO_TABLE) const {
    message("variant " + variantName + " piece " + symbol + " color " + color_name(strong)
          + " goal checkmate files " + std::to_string(int(variant->maxFile) + 1)
          + " ranks " + std::to_string(int(variant->maxRank) + 1)
          + " stalemate " + (variant->stalemateValue == VALUE_DRAW ? "draw" : variant->stalemateValue < VALUE_DRAW ? "loss" : "win")
          + " nmove ignored castling-rights none", format);
    if (!raw)
    {
        formatted_stats(format);
        return;
    }
    for (int turn : {STRONG, WEAK})
        message("summary stm " + std::string(color_name(turn == STRONG ? strong : ~strong))
              + " legal " + std::to_string(legal[turn]) + " wins " + std::to_string(wins[turn])
              + " draws " + std::to_string(draws[turn]) + " losses " + std::to_string(losses[turn])
              + " checkmates " + std::to_string(mates[turn]) + " max_dtm_plies " + std::to_string(maximum[turn]));
    for (const auto& row : histogram)
        message("dtm plies " + std::to_string(row.first)
              + " strong_wins " + std::to_string(row.second[0]) + " strong_losses " + std::to_string(row.second[1])
              + " weak_wins " + std::to_string(row.second[2]) + " weak_losses " + std::to_string(row.second[3]));
    message("diagnostics time " + std::to_string(elapsed)
          + " index_slots " + std::to_string(count)
          + " distinct_states " + std::to_string(distinct_states())
          + " legal_states " + std::to_string(legal[STRONG] + legal[WEAK])
          + " table_bytes " + std::to_string(uint64_t(count) * sizeof(Node))
          + " signature " + std::to_string(signature));
  }

  void probe(const Position& pos) const {
    if (   pos.variant() != variant || pos.count<KING>(strong) != 1 || pos.count<KING>(~strong) != 1
        || pos.count(strong, piece) != 1 || pos.count(~strong, piece) || pos.count<ALL_PIECES>() != 3
        || pos.castling_rights(WHITE) || pos.castling_rights(BLACK) || pos.state()->wallSquares)
    { message("error probe requires K+selected-piece versus K with no castling rights or walls"); return; }
    int wk = squareIndex[pos.square<KING>(strong)], bk = squareIndex[pos.square<KING>(~strong)];
    int x = squareIndex[lsb(pos.pieces(strong, piece))];
    if (wk < 0 || bk < 0 || x < 0) { message("error position outside table"); return; }
    int turn = pos.side_to_move() == strong ? STRONG : WEAK;
    const Node& node = nodes[index(wk, x, bk, turn)];
    if (node.result == INVALID) { message("error illegal table position"); return; }
    Move best = MOVE_NONE;
    uint32_t distance = node.result == LOSS ? 0 : UINT32_MAX;
    for (Move move : MoveList<LEGAL>(pos))
    {
        Result childResult = DRAW;
        uint32_t childDistance = 0;
        if (!pos.capture(move))
        {
            int to = squareIndex[to_sq(move)], kw = wk, kb = bk, xp = x;
            if (turn == WEAK) kb = to;
            else if (from_sq(move) == squares[wk]) kw = to;
            else xp = to;
            const Node& child = nodes[index(kw, xp, kb, 1 - turn)];
            childResult = child.result; childDistance = child.distance;
        }
        if (   (node.result == WIN && childResult == LOSS && childDistance < distance)
            || (node.result == LOSS && childResult == WIN && (best == MOVE_NONE || childDistance > distance))
            || (node.result == DRAW && childResult == DRAW && best == MOVE_NONE))
        { best = move; distance = childDistance; }
    }
    message("probe result " + std::string(node.result == WIN ? "win" : node.result == LOSS ? "loss" : "draw")
          + (node.result == DRAW ? "" : " dtm_plies " + std::to_string(node.distance))
          + " bestmove " + (best == MOVE_NONE ? "0000" : UCI::move(pos, best)));
  }
};

} // namespace

struct MateTable::Impl {
  std::unique_ptr<Table> table;
  std::thread worker;
  std::atomic_bool cancelled{false}, building{false};
};

MateTable::MateTable() : impl(new Impl) {}
MateTable::~MateTable() { stop(); }

void MateTable::stop() {
  impl->cancelled.store(true, std::memory_order_relaxed);
  wait();
}

void MateTable::wait() {
  if (impl->worker.joinable()) impl->worker.join();
}

void MateTable::command(std::istream& input, const Position& pos) {
  std::string verb;
  input >> verb;
  const Variant* v = variants.at(std::string(Options["UCI_Variant"]));
  if (verb == "status")
  {
      message(std::string("status ") + (impl->building.load(std::memory_order_acquire) ? "building"
            : impl->table && impl->table->variant == v ? "ready" : "empty"));
      return;
  }
  if (verb == "clear") { stop(); impl->table.reset(); message("status empty"); return; }
  if (verb == "stats" || verb == "probe")
  {
      Format format = Format::INFO_TABLE;
      bool raw = false;
      std::string option, value, extra;
      if (verb == "stats" && (input >> option))
      {
          if (option == "raw") raw = true;
          else if (option != "format" || !(input >> value) || !parse_format(value, format))
          { message("error usage: mate-table stats [raw | format info|info-table|table]"); return; }
          if (input >> extra)
          { message("error usage: mate-table stats [raw | format info|info-table|table]"); return; }
      }
      if (impl->building.load(std::memory_order_acquire)) { message("status building"); return; }
      if (!impl->table || impl->table->variant != v) { message("error no table for selected variant"); return; }
      if (verb == "stats") impl->table->stats(raw, format); else impl->table->probe(pos);
      return;
  }
  std::string symbol, option;
  if (verb == "build") input >> verb;
  if (verb == "piece") input >> symbol;
  else symbol = verb;
  if (symbol.empty()) { message("error usage: mate-table piece SYMBOL [color white|black] [memory MiB] [format info|info-table|table]"); return; }
  Color color = WHITE;
  uint64_t memory = 512;
  Format format = Format::INFO_TABLE;
  while (input >> option)
  {
      std::string value;
      if (!(input >> value)) { message("error missing option value"); return; }
      if (option == "color" && (value == "white" || value == "black")) color = value == "white" ? WHITE : BLACK;
      else if (option == "format")
      {
          if (!parse_format(value, format))
          { message("error format must be info, info-table or table"); return; }
      }
      else if (option == "memory")
      {
          std::istringstream number(value);
          char extra;
          if (!(number >> memory) || (number >> extra) || memory < 1 || memory > 4096)
          { message("error memory must be 1..4096 MiB"); return; }
      }
      else { message("error unknown option or invalid value"); return; }
  }
  PieceType pt = resolve_piece(v, symbol);
  if (pt == NO_PIECE_TYPE || pt == KING) { message("error unknown, ambiguous or royal piece symbol"); return; }
  // Finish any previous job before checking/using the shared piece tables.
  stop();
  Threads.stop = true;
  TDS::wait();
  Threads.main()->wait_for_search_finished();
  std::string reason = unsupported(v, pt);
  if (!reason.empty()) { message("error unsupported: " + reason); return; }
  impl->table.reset();
  impl->cancelled.store(false, std::memory_order_relaxed);
  impl->building.store(true, std::memory_order_release);
  std::string name = Options["UCI_Variant"];
  message("building variant " + name + " piece " + symbol + " color " + color_name(color), format);
  impl->worker = std::thread([this, v, pt, color, name, symbol, memory, format] {
      std::unique_ptr<Table> table(new Table(v, pt, color, name, symbol, memory * 1048576));
      std::string error;
      bool complete = table->build(impl->cancelled, error);
      if (!complete)
      {
          impl->building.store(false, std::memory_order_release);
          message(error.empty() ? "cancelled" : "error " + error, format);
          return;
      }
      impl->table = std::move(table);
      impl->building.store(false, std::memory_order_release);
      impl->table->stats(false, format);
      message("complete time " + std::to_string(impl->table->elapsed), format);
  });
}

} // namespace Stockfish
