/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

/* Experimental four-piece implementation, included privately by mate_table.cpp.
 * Fixed material, ordinary checkmating kings; no search-path integration.
 */

struct FourTable {
  using Placement = std::array<int, 4>; // white king, black king, support A, support B
  const Variant* variant;
  std::array<PieceType, 2> types;
  std::array<Color, 2> owners;
  std::array<std::string, 2> symbols;
  std::string variantName;
  int n;
  uint32_t count;
  uint64_t budget;
  MateTableStorage::Nodes nodes;
  std::array<std::unique_ptr<Table>, 2> bases;
  std::vector<Square> squares;
  std::array<int, SQUARE_NB> squareIndex;
  std::vector<Bitboard> kings;
  std::array<std::vector<Bitboard>, 2> attackCache;
  std::array<std::vector<std::vector<int>>, 2> reverseQuiet;
  std::array<Bitboard, 2> regions;
  uint64_t legal[2] = {}, wins[2] = {}, losses[2] = {}, draws[2] = {}, mates[2] = {};
  uint32_t maximum[2] = {};
  std::map<uint32_t, std::array<uint64_t, 4>> histogram;
  uint64_t signature = 14695981039346656037ULL;
  uint64_t captureEdges = 0, processed = 0, peakQueueBytes = 0, verified = 0;
  TimePoint elapsed = 0, baseTime = 0, initializeTime = 0, propagateTime = 0, verifyTime = 0;

  FourTable(const Variant* v, std::array<PieceType, 2> pt, std::array<Color, 2> colors,
            std::array<std::string, 2> names, std::string name, uint64_t bytes)
      : variant(v), types(pt), owners(colors), symbols(names), variantName(std::move(name)),
        n((int(v->maxFile) + 1) * (int(v->maxRank) + 1)),
        count(uint32_t(2 * uint64_t(n) * n * n * n)), budget(bytes) {}

  uint32_t index(const Placement& p, int turn) const {
    return 2 * (((p[0] * n + p[1]) * n + p[2]) * n + p[3]) + turn;
  }

  Node read(uint32_t i) const {
    auto value = nodes.get(i);
    Node node;
    node.distance = value.distance;
    node.remaining = value.remaining;
    switch (value.status)
    {
    case MateTableStorage::Status::INVALID: node.result = INVALID; break;
    case MateTableStorage::Status::UNRESOLVED_DRAW: node.result = nodes.generating() ? UNKNOWN : DRAW; break;
    case MateTableStorage::Status::WIN: node.result = WIN; break;
    case MateTableStorage::Status::LOSS: node.result = LOSS; break;
    }
    return node;
  }

  bool store(uint32_t i, const Node& node) {
    auto status = node.result == INVALID ? MateTableStorage::Status::INVALID
                : node.result == WIN ? MateTableStorage::Status::WIN
                : node.result == LOSS ? MateTableStorage::Status::LOSS
                : MateTableStorage::Status::UNRESOLVED_DRAW;
    return nodes.set(i, status, node.distance, node.remaining);
  }

  Placement decode(uint32_t i) const {
    i /= 2;
    Placement p;
    for (int j = 3; j >= 0; --j) { p[j] = int(i % n); i /= n; }
    return p;
  }

  Bitboard occupied(const Placement& p) const {
    Bitboard bb = square_bb(squares[p[0]]) | squares[p[1]];
    for (int j = 2; j < 4; ++j) if (p[j] >= 0) bb |= squares[p[j]];
    return bb;
  }

  bool attacked(int target, Color by, const Placement& p) const {
    if (kings[p[by]] & squares[target]) return true;
    for (int s = 0; s < 2; ++s)
        if (owners[s] == by && p[s + 2] >= 0)
        {
            int other = p[3 - s];
            Bitboard attacks = other >= 0
                ? attackCache[s][(p[s + 2] * n + p[by]) * n + other]
                : attacks_bb(by, types[s], squares[p[s + 2]], square_bb(squares[p[by]])) & regions[s];
            if (attacks & squares[target]) return true;
        }
    return false;
  }

  Node lookup(const Placement& p, int turn) const {
    if (p[2] >= 0 && p[3] >= 0) return read(index(p, turn));
    if (p[2] < 0 && p[3] < 0) { Node draw; draw.result = DRAW; return draw; }
    int s = p[2] >= 0 ? 0 : 1;
    return bases[s]->nodes[bases[s]->index(p[owners[s]], p[s + 2], p[~owners[s]],
                                          turn == owners[s] ? STRONG : WEAK)];
  }

  template<typename Visitor>
  void successors(const Placement& p, Color turn, Visitor visit) const {
    Bitboard occ = occupied(p), friends = square_bb(squares[p[turn]]);
    Bitboard enemies = square_bb(squares[p[~turn]]);
    for (int s = 0; s < 2; ++s)
        if (p[s + 2] >= 0)
            (owners[s] == turn ? friends : enemies) |= squares[p[s + 2]];
    for (int mover = 0; mover < 4; ++mover)
    {
        if (mover < 2 ? mover != turn : owners[mover - 2] != turn || p[mover] < 0) continue;
        Bitboard destinations;
        if (mover < 2) destinations = kings[p[mover]] & ~friends;
        else
        {
            int s = mover - 2;
            destinations = ((moves_bb(turn, types[s], squares[p[mover]], occ) & ~occ)
                          | (attacks_bb(turn, types[s], squares[p[mover]], occ) & enemies)) & regions[s];
        }
        destinations &= ~square_bb(squares[p[~turn]]);
        while (destinations)
        {
            int to = squareIndex[pop_lsb(destinations)];
            Placement child = p;
            for (int s = 0; s < 2; ++s)
                if (owners[s] != turn && child[s + 2] == to) child[s + 2] = -1;
            child[mover] = to;
            if (!attacked(child[turn], ~turn, child)) visit(child, mover, to);
        }
    }
  }

  bool build(const std::atomic_bool& cancelled, std::string& error, Format format) {
    const TimePoint started = now();
    uint64_t cacheBytes = 2 * uint64_t(n) * n * n * sizeof(Bitboard);
    uint64_t basePeak = uint64_t(n) * n * n * (4 * sizeof(Node) + 2 * sizeof(uint32_t));
    uint64_t overhead = cacheBytes + basePeak + 4 * 1048576;
    uint64_t queueAllowance = uint64_t(count) * sizeof(uint32_t);
    uint64_t required = uint64_t(count) * 3 + queueAllowance + overhead;
    if (required > budget) { error = "four-piece memory budget exceeded"; return false; }
    // Build the two possible three-piece capture destinations first.
    for (int s = 0; s < 2; ++s)
    {
        bases[s].reset(new Table(variant, types[s], owners[s], variantName, symbols[s], budget));
        if (!bases[s]->build(cancelled, error)) return false;
    }
    baseTime = now() - started;
    if (!nodes.allocate(count, budget - overhead - queueAllowance))
    { error = nodes.error(); return false; }
    squareIndex.fill(-1);
    Bitboard board = board_size_bb(variant->maxFile, variant->maxRank);
    for (Rank r = RANK_1; r <= variant->maxRank; ++r)
        for (File f = FILE_A; f <= variant->maxFile; ++f)
        { Square sq = make_square(f, r); squareIndex[sq] = int(squares.size()); squares.push_back(sq); }
    kings.resize(n);
    for (int i = 0; i < n; ++i) kings[i] = attacks_bb<KING>(squares[i]) & board;
    for (int s = 0; s < 2; ++s)
    {
        regions[s] = variant->mobilityRegion[owners[s]][types[s]];
        regions[s] = regions[s] ? regions[s] & board : board;
        attackCache[s].resize(n * n * n);
        reverseQuiet[s].resize(n);
        for (int x = 0; x < n; ++x)
        {
            if (cancelled.load(std::memory_order_relaxed)) return false;
            Bitboard destinations = moves_bb(owners[s], types[s], squares[x], 0) & regions[s];
            while (destinations) reverseQuiet[s][squareIndex[pop_lsb(destinations)]].push_back(x);
            for (int a = 0; a < n; ++a)
                for (int b = 0; b < n; ++b)
                    attackCache[s][(x * n + a) * n + b] = attacks_bb(owners[s], types[s], squares[x],
                        square_bb(squares[a]) | squares[b]) & regions[s];
        }
    }
    // Distance buckets handle capture exits with nonzero DTM. A tentative
    // winning distance may improve before it is popped; old entries are skipped.
    std::vector<std::vector<uint32_t>> buckets;
    uint64_t queueBytes = 0;
    auto enqueue = [&](uint32_t i) {
        uint32_t d = read(i).distance;
        if (buckets.size() <= d) buckets.resize(d + 1);
        auto& bucket = buckets[d];
        uint64_t oldBytes = bucket.capacity() * sizeof(uint32_t);
        bucket.push_back(i);
        queueBytes += bucket.capacity() * sizeof(uint32_t) - oldBytes;
        peakQueueBytes = std::max(peakQueueBytes, queueBytes);
    };
    TimePoint report = now();
    for (int wk = 0; wk < n; ++wk)
        for (int bk = 0; bk < n; ++bk)
        {
            if (cancelled.load(std::memory_order_relaxed)) return false;
            if (wk == bk || (kings[wk] & squares[bk])) continue;
            if (now() - report > 2000)
            { message("four-piece phase initialize white_king " + std::to_string(wk), format); report = now(); }
            for (int x = 0; x < n; ++x)
                if (x != wk && x != bk)
                    for (int y = 0; y < n; ++y)
                    {
                        if (y == wk || y == bk || y == x) continue;
                        Placement p = {wk, bk, x, y};
                        bool check[2] = {attacked(wk, BLACK, p), attacked(bk, WHITE, p)};
                        for (Color turn : {WHITE, BLACK})
                        {
                            if (check[~turn]) continue;
                            uint32_t i = index(p, turn);
                            Node node;
                            node.result = UNKNOWN;
                            uint32_t winningDistance = UINT32_MAX, losingDistance = 0;
                            uint16_t moveCount = 0;
                            successors(p, turn, [&](const Placement& child, int, int) {
                                ++moveCount;
                                if (child[2] >= 0 && child[3] >= 0) { ++node.remaining; return; }
                                ++captureEdges;
                                Node target = lookup(child, ~turn);
                                if (target.result == LOSS) winningDistance = std::min(winningDistance, target.distance + 1);
                                else if (target.result == WIN) losingDistance = std::max(losingDistance, target.distance + 1);
                                else ++node.remaining; // Drawing exits can never force a loss.
                            });
                            if (!moveCount)
                            {
                                node.result = check[turn] || variant->stalemateValue < VALUE_DRAW ? LOSS
                                            : variant->stalemateValue > VALUE_DRAW ? WIN : DRAW;
                                if (check[turn]) ++mates[turn];
                            }
                            else if (winningDistance != UINT32_MAX)
                            { node.result = WIN; node.distance = winningDistance; }
                            else
                            { node.distance = losingDistance; if (!node.remaining) node.result = LOSS; }
                            if (!store(i, node)) { error = nodes.error(); return false; }
                            if (node.result == WIN || node.result == LOSS) enqueue(i);
                        }
                    }
        }
    initializeTime = now() - started - baseTime;
    for (uint32_t d = 0; d < buckets.size(); ++d)
    {
        for (size_t offset = 0; offset < buckets[d].size(); ++offset)
        {
            if (!(processed & 65535))
            {
                if (cancelled.load(std::memory_order_relaxed)) return false;
                if (now() - report > 2000)
                { message("four-piece phase propagate dtm " + std::to_string(d) + " processed " + std::to_string(processed), format); report = now(); }
            }
            uint32_t i = buckets[d][offset];
            const Node child = read(i);
            if (child.distance != d) continue;
            ++processed;
            Placement p = decode(i);
            Color mover = Color(1 - (i & 1));
            auto visit = [&](const Placement& parent) {
                uint32_t j = index(parent, mover);
                Node node = read(j);
                if (node.result != UNKNOWN && node.result != WIN) return;
                // Stalemate draws share the unresolved code but have no edges.
                if (node.result == UNKNOWN && !node.remaining) return;
                if (child.result == LOSS)
                {
                    if (node.result == WIN && node.distance <= d + 1) return;
                    node.result = WIN; node.distance = d + 1;
                    if (store(j, node)) enqueue(j);
                }
                else if (node.result == UNKNOWN)
                {
                    node.distance = std::max(node.distance, d + 1);
                    if (!--node.remaining) node.result = LOSS;
                    if (store(j, node) && node.result == LOSS) enqueue(j);
                }
            };
            Bitboard from = kings[p[mover]] & ~occupied(p);
            while (from)
            { Placement parent = p; parent[mover] = squareIndex[pop_lsb(from)]; visit(parent); }
            for (int s = 0; s < 2; ++s)
                if (owners[s] == mover)
                    for (int old : reverseQuiet[s][p[s + 2]])
                    {
                        Placement parent = p; parent[s + 2] = old;
                        uint32_t j = index(parent, mover);
                        Result result = read(j).result;
                        if ((result == UNKNOWN || result == WIN)
                            && (moves_bb(mover, types[s], squares[old], occupied(parent)) & regions[s] & squares[p[s + 2]]))
                            visit(parent);
                    }
            if (!nodes.good()) { error = nodes.error(); return false; }
        }
        queueBytes -= buckets[d].capacity() * sizeof(uint32_t);
        std::vector<uint32_t>().swap(buckets[d]);
    }
    propagateTime = now() - started - baseTime - initializeTime;
    nodes.finish(); // Remaining unresolved entries are draws; counters are no longer needed.
    for (uint32_t i = 0; i < count; ++i)
    {
        if (!(i & 65535) && cancelled.load(std::memory_order_relaxed)) return false;
        Node node = read(i);
        if (node.result == DRAW)
        {
            node.distance = 0;
            if (!store(i, node)) { error = nodes.error(); return false; }
        }
        signature = (signature ^ uint8_t(node.result)) * 1099511628211ULL;
        for (unsigned shift = 0; shift < 32; shift += 8)
            signature = (signature ^ uint8_t(node.distance >> shift)) * 1099511628211ULL;
        if (node.result == INVALID) continue;
        int turn = i & 1;
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

  bool verify(const std::atomic_bool& cancelled, std::string& error, Format format) {
    const TimePoint started = now();
    TimePoint report = started;
    for (uint32_t i = 0; i < count; ++i)
    {
        if (!(i & 65535))
        {
            if (cancelled.load(std::memory_order_relaxed)) return false;
            if (now() - report > 2000)
            { message("four-piece phase verify positions " + std::to_string(verified), format); report = now(); }
        }
        const Node node = read(i);
        if (node.result == INVALID) continue;
        Placement p = decode(i);
        Color turn = Color(i & 1);
        uint32_t winDistance = UINT32_MAX, lossDistance = 0;
        bool hasDraw = false;
        int moves = 0;
        successors(p, turn, [&](const Placement& child, int, int) {
            ++moves;
            Node target = lookup(child, ~turn);
            if (target.result == LOSS) winDistance = std::min(winDistance, target.distance + 1);
            else if (target.result == WIN) lossDistance = std::max(lossDistance, target.distance + 1);
            else if (target.result == DRAW) hasDraw = true;
            else error = "invalid successor";
        });
        Result result;
        uint32_t distance = 0;
        if (!moves) result = attacked(p[turn], ~turn, p) || variant->stalemateValue < VALUE_DRAW ? LOSS
                            : variant->stalemateValue > VALUE_DRAW ? WIN : DRAW;
        else if (winDistance != UINT32_MAX) { result = WIN; distance = winDistance; }
        else if (hasDraw) result = DRAW;
        else { result = LOSS; distance = lossDistance; }
        if (!error.empty() || result != node.result || distance != node.distance)
        { error = "four-piece Bellman verification failed at index " + std::to_string(i); return false; }
        ++verified;
    }
    verifyTime = now() - started;
    return true;
  }

  void stats(bool raw, Format format) const {
    message("four-piece variant " + variantName + " material " + symbols[0] + " " + color_name(owners[0])
          + " " + symbols[1] + " " + color_name(owners[1]), format);
    for (int turn = 0; turn < 2; ++turn)
        message("summary stm " + std::string(color_name(Color(turn)))
              + " legal " + std::to_string(legal[turn]) + " wins " + std::to_string(wins[turn])
              + " draws " + std::to_string(draws[turn]) + " losses " + std::to_string(losses[turn])
              + " checkmates " + std::to_string(mates[turn]) + " max_dtm_plies " + std::to_string(maximum[turn]), format);
    if (!raw)
        for (int army = 0; army < 2; ++army)
        {
            std::map<uint32_t, std::array<uint64_t, 2>> rows;
            rows[0] = {};
            for (const auto& row : histogram)
            {
                if (row.second[2 * army]) rows[(row.first + 1) / 2][0] += row.second[2 * army];
                if (row.second[2 * (1 - army) + 1]) rows[row.first / 2][1] += row.second[2 * (1 - army) + 1];
            }
            if (format == Format::INFO)
            {
                for (const auto& row : rows)
                    message("army " + std::string(color_name(Color(army))) + " mate " + std::to_string(row.second[0])
                          + " mated " + std::to_string(row.second[1]) + " in " + std::to_string(row.first), format);
                continue;
            }
            size_t first = std::max(size_t(6), std::to_string(wins[army]).size());
            size_t second = std::max(size_t(6), std::to_string(losses[1 - army]).size());
            auto line = [&](const std::string& a, const std::string& b, const std::string& c) {
                std::ostringstream out;
                out << "| " << std::setw(int(first)) << a << " | " << std::setw(int(second)) << b
                    << " | " << std::setw(3) << c << " |";
                message(out.str(), format);
            };
            const std::string border = "+" + std::string(first + 2, '-') + "+" + std::string(second + 2, '-') + "+-----+";
            message("Statistics " + std::string(color_name(Color(army))), format);
            message(border, format);
            line("mate", "mated", "in");
            message(border, format);
            for (const auto& row : rows)
                line(row.first == 0 && !row.second[0] ? "" : std::to_string(row.second[0]),
                     std::to_string(row.second[1]), std::to_string(row.first));
            message(border, format);
            line(std::to_string(wins[army]), std::to_string(losses[1 - army]), "tot");
            message(border, format);
        }
    if (raw)
        for (const auto& row : histogram)
            message("dtm plies " + std::to_string(row.first)
                  + " white_wins " + std::to_string(row.second[0]) + " white_losses " + std::to_string(row.second[1])
                  + " black_wins " + std::to_string(row.second[2]) + " black_losses " + std::to_string(row.second[3]), format);
    message("timing bases " + std::to_string(baseTime) + " initialize " + std::to_string(initializeTime)
          + " propagate " + std::to_string(propagateTime) + " total " + std::to_string(elapsed)
          + " verify " + std::to_string(verifyTime), format);
    message("verified positions " + std::to_string(verified) + " capture_edges " + std::to_string(captureEdges), format);
    if (raw)
    {
        const auto& header = nodes.header();
        message("storage_header version " + std::to_string(header.version)
              + " dtm_bits " + std::to_string(header.dtmBits) + " status_bits " + std::to_string(header.statusBits)
              + " record_bytes " + std::to_string(header.recordBytes), format);
        message("diagnostics table_bytes " + std::to_string(nodes.record_bytes())
              + " counter_bytes " + std::to_string(nodes.counter_bytes())
              + " construction_peak_bytes " + std::to_string(nodes.peak_bytes())
              + " peak_queue_bytes " + std::to_string(peakQueueBytes) + " signature " + std::to_string(signature), format);
    }
  }

  void probe(const Position& pos) const {
    if (pos.count<KING>(WHITE) != 1 || pos.count<KING>(BLACK) != 1
        || pos.castling_rights(WHITE) || pos.castling_rights(BLACK) || pos.state()->wallSquares)
    { message("error four-piece probe requires ordinary kings without castling rights or walls"); return; }
    Placement p = {squareIndex[pos.square<KING>(WHITE)], squareIndex[pos.square<KING>(BLACK)], -1, -1};
    Bitboard used = pos.pieces(KING);
    for (int s = 0; s < 2; ++s)
    {
        Bitboard pieces = pos.pieces(owners[s], types[s]) & ~used;
        if (pieces) { Square sq = pop_lsb(pieces); used |= sq; p[s + 2] = squareIndex[sq]; }
    }
    if (pos.pieces() != used || p[0] < 0 || p[1] < 0)
    { message("error position material does not match four-piece table"); return; }
    Node node = lookup(p, pos.side_to_move());
    if (node.result == INVALID) { message("error illegal table position"); return; }
    auto name = [](Result r) { return r == WIN ? "win" : r == LOSS ? "loss" : "draw"; };
    message("probe result " + std::string(name(node.result)) + (node.result == DRAW ? "" : " dtm_plies " + std::to_string(node.distance)));
    successors(p, pos.side_to_move(), [&](const Placement& child, int mover, int to) {
        Node target = lookup(child, ~pos.side_to_move());
        message("edge move " + UCI::move(pos, make_move(squares[p[mover]], squares[to]))
              + " result " + name(target.result) + (target.result == DRAW ? "" : " dtm_plies " + std::to_string(target.distance)));
    });
    message("probe complete");
  }
};
