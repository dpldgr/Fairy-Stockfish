/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

// Included privately by mate_table.cpp. Ordinary K/K needs no retrograde work:
// every nonoverlapping, nonadjacent placement is a draw on a rectangular board.
struct TwoTable {
  const Variant* variant;
  const std::string variantName;
  const int n;
  const uint32_t count;
  const uint64_t budget;
  std::vector<Square> squares;
  std::array<int, SQUARE_NB> squareIndex;
  std::vector<Bitboard> kings;
  uint64_t legal = 0, signature = 14695981039346656037ULL;
  TimePoint elapsed = 0;

  TwoTable(const Variant* v, std::string name, uint64_t bytes)
      : variant(v), variantName(std::move(name)),
        n((int(v->maxFile) + 1) * (int(v->maxRank) + 1)), count(2 * n * n), budget(bytes) {}

  Node read(uint32_t i) const {
    int wk = (i / 2) / n, bk = (i / 2) % n;
    Node node;
    if (wk != bk && !(kings[wk] & squares[bk])) node.result = DRAW;
    return node;
  }

  bool build(const std::atomic_bool& cancelled, std::string& error) {
    TimePoint started = now();
    if (uint64_t(n) * (sizeof(Square) + sizeof(Bitboard)) + sizeof(squareIndex) + 1024 > budget)
    { error = "two-piece memory budget exceeded"; return false; }
    squareIndex.fill(-1);
    for (Rank r = RANK_1; r <= variant->maxRank; ++r)
        for (File f = FILE_A; f <= variant->maxFile; ++f)
        {
            Square sq = make_square(f, r);
            squareIndex[sq] = int(squares.size()); squares.push_back(sq);
        }
    Bitboard board = board_size_bb(variant->maxFile, variant->maxRank);
    for (Square sq : squares) kings.push_back(attacks_bb<KING>(sq) & board);
    for (uint32_t i = 0; i < count; ++i)
    {
        if (!(i & 1023) && cancelled.load(std::memory_order_relaxed)) return false;
        Node node = read(i);
        legal += node.result == DRAW;
        signature = (signature ^ uint8_t(node.result)) * 1099511628211ULL;
        for (int byte = 0; byte < 4; ++byte) signature *= 1099511628211ULL; // Draw/invalid distance storage is zero.
    }
    elapsed = now() - started;
    return true;
  }

  void stats(bool raw, Format format) const {
    message("two-piece variant " + variantName + " material "
            + variant->pieceToSymbol[make_piece(WHITE, KING)] + " "
            + variant->pieceToSymbol[make_piece(BLACK, KING)]
            + " files " + std::to_string(int(variant->maxFile) + 1)
            + " ranks " + std::to_string(int(variant->maxRank) + 1)
            + " nmove ignored castling-rights none", format);
    for (Color c : {WHITE, BLACK})
        message("summary stm " + std::string(color_name(c)) + " legal " + std::to_string(legal / 2)
                + " wins 0 draws " + std::to_string(legal / 2)
                + " losses 0 checkmates 0 max_dtm_plies 0", format);
    if (raw)
        message("diagnostics time " + std::to_string(elapsed)
                + " index_slots " + std::to_string(count)
                + " distinct_states " + std::to_string(2 * uint64_t(n) * (n - 1))
                + " legal_states " + std::to_string(legal)
                + " table_bytes 0 signature " + std::to_string(signature), format);
    else message("all legal positions draw", format);
  }

  void probe(const Position& pos) const {
    if (   pos.variant() != variant || pos.count<KING>(WHITE) != 1 || pos.count<KING>(BLACK) != 1
        || pos.count<ALL_PIECES>() != 2 || pos.castling_rights(WHITE) || pos.castling_rights(BLACK)
        || pos.state()->wallSquares)
    { message("error probe requires K versus K with no castling rights or walls"); return; }
    int wk = squareIndex[pos.square<KING>(WHITE)], bk = squareIndex[pos.square<KING>(BLACK)];
    if (wk < 0 || bk < 0) { message("error position outside table"); return; }
    if (read(2 * (wk * n + bk) + pos.side_to_move()).result == INVALID)
    { message("error illegal table position"); return; }
    Move best = MOVE_NONE;
    for (Move move : MoveList<LEGAL>(pos)) { best = move; break; }
    message("probe result draw bestmove " + (best == MOVE_NONE ? std::string("0000") : UCI::move(pos, best)));
  }
};
