/*
  Fairy-Stockfish, a UCI chess playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  Fairy-Stockfish is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#include "tds.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <condition_variable>
#include <deque>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include "evaluate.h"
#include "misc.h"
#include "movegen.h"
#include "position.h"
#include "thread.h"
#include "uci.h"

namespace Stockfish::TDS {

namespace {

struct Node;

struct Parent {
    Node* node;
    Move move;
};

struct Node {
    std::mutex mutex;
    Key key;
    int depth;
    std::vector<Move> path;
    std::vector<Parent> parents;
    std::vector<std::pair<Move, Node*>> children;
    Value value = -VALUE_INFINITE;
    Move best = MOVE_NONE;
    size_t pending = 0;
    bool queued = false;
    bool expanded = false;
    std::atomic_bool complete{false};
};

struct NodeKey {
    Key key;
    int depth;
    bool operator==(const NodeKey& other) const { return key == other.key && depth == other.depth; }
};

struct NodeKeyHash {
    size_t operator()(const NodeKey& k) const {
        return size_t(k.key ^ (k.key >> 32) ^ (Key(k.depth) * 0x9e3779b97f4a7c15ULL));
    }
};

class Search {
public:
    Search(const Position& pos, int d) : variant(pos.variant()), fen(pos.fen()), chess960(pos.is_chess960()), depth(d) {}

    void run() {
        const TimePoint startTime = now();
        StateInfo st;
        Position pos;
        pos.set(variant, fen, chess960, &st, Threads.main());

        auto rootNode = std::make_unique<Node>();
        root = rootNode.get();
        root->key = pos.key();
        root->depth = depth;
        root->queued = true;
        table[shard(root->key)].emplace(NodeKey{root->key, depth}, std::move(rootNode));
        ready.push_back(root);

        const size_t workerCount = std::max<size_t>(1, Threads.size());
        std::vector<std::thread> workers;
        for (size_t i = 0; i < workerCount; ++i)
            workers.emplace_back(&Search::worker, this, i);
        for (auto& worker : workers)
            worker.join();

        if (root->complete && root->best != MOVE_NONE) {
            const TimePoint elapsed = std::max<TimePoint>(1, now() - startTime);
            const uint64_t nps = nodes * 1000 / elapsed;
            auto pv = principal_variation();
            sync_cout << "info depth " << depth << " score cp " << int(root->value)
                      << " nodes " << nodes << " nps " << nps << " time " << elapsed
                      << " tdsworkers " << workerCount << " pv";
            Position out;
            StateInfo outState;
            out.set(variant, fen, chess960, &outState, Threads.main());
            std::vector<StateInfo> states(pv.size());
            for (size_t i = 0; i < pv.size(); ++i) {
                std::cout << " " << UCI::move(out, pv[i]);
                out.do_move(pv[i], states[i]);
            }
            std::cout << sync_endl;
            Position rootPos;
            StateInfo rootState;
            rootPos.set(variant, fen, chess960, &rootState, Threads.main());
            sync_cout << "bestmove " << UCI::move(rootPos, root->best) << sync_endl;
        } else
            sync_cout << "bestmove (none)" << sync_endl;
    }

private:
    void worker(size_t workerId) {
        StateInfo rootState;
        Position pos;
        pos.set(variant, fen, chess960, &rootState, Threads[workerId]);
        std::vector<StateInfo> states(depth);
        std::vector<Move> currentPath;

        while (true) {
            Node* node;
            {
                std::unique_lock<std::mutex> lock(queueMutex);
                cv.wait(lock, [&] { return Threads.stop || root->complete || !ready.empty() || active == 0; });
                if (Threads.stop || root->complete || (ready.empty() && active == 0))
                    return;
                if (ready.empty())
                    continue;
                node = ready.front();
                ready.pop_front();
                ++active;
            }

            // Ready nodes tend to share much of their path. Keep a position per
            // worker and move it to the requested node instead of reparsing the
            // root FEN and replaying the complete path for every node.
            size_t common = 0;
            while (   common < currentPath.size()
                   && common < node->path.size()
                   && currentPath[common] == node->path[common])
                ++common;
            while (currentPath.size() > common) {
                pos.undo_move(currentPath.back());
                currentPath.pop_back();
            }
            while (currentPath.size() < node->path.size()) {
                const size_t ply = currentPath.size();
                pos.do_move(node->path[ply], states[ply]);
                currentPath.push_back(node->path[ply]);
            }

            expand(node, pos);

            {
                std::lock_guard<std::mutex> lock(queueMutex);
                --active;
                cv.notify_all();
            }
        }
    }

    void expand(Node* node, Position& pos) {
        Value terminal;
        const bool gameEnd = pos.is_game_end(terminal, int(node->path.size()));
        if (gameEnd || node->depth == 0) {
            Value value = gameEnd ? terminal : Eval::evaluate(pos);
            ++nodes;
            finish(node, value);
            return;
        }

        std::vector<std::pair<Move, Key>> successors;
        for (Move move : MoveList<LEGAL>(pos)) {
            StateInfo state;
            pos.do_move(move, state);
            successors.emplace_back(move, pos.key());
            pos.undo_move(move);
        }

        ++nodes;
        node->expanded = true;
        if (successors.empty()) {
            finish(node, VALUE_DRAW);
            return;
        }

        std::vector<std::pair<Move, Node*>> children;
        children.reserve(successors.size());
        for (const auto& successor : successors) {
            const NodeKey key{successor.second, node->depth - 1};
            Node* child;
            const size_t index = shard(key.key);
            {
                std::lock_guard<std::mutex> tableLock(tableMutexes[index]);
                auto& bucket = table[index];
                auto it = bucket.find(key);
                if (it == bucket.end()) {
                    auto inserted = std::make_unique<Node>();
                    child = inserted.get();
                    child->key = key.key;
                    child->depth = key.depth;
                    child->path = node->path;
                    child->path.push_back(successor.first);
                    bucket.emplace(key, std::move(inserted));
                } else
                    child = it->second.get();
            }
            children.emplace_back(successor.first, child);
        }

        {
            std::lock_guard<std::mutex> nodeLock(node->mutex);
            node->pending = children.size();
            node->children = children;
        }

        for (const auto& childEdge : children) {
            Node* child = childEdge.second;
            bool complete;
            Value value = VALUE_NONE;
            bool enqueue = false;
            {
                std::lock_guard<std::mutex> childLock(child->mutex);
                complete = child->complete;
                if (complete)
                    value = child->value;
                else {
                    child->parents.push_back({node, childEdge.first});
                    if (!child->queued) {
                        child->queued = true;
                        enqueue = true;
                    }
                }
            }
            if (complete)
                child_finished(node, childEdge.first, value);
            else if (enqueue) {
                std::lock_guard<std::mutex> queueLock(queueMutex);
                ready.push_back(child);
                cv.notify_one();
            }
        }
    }

    void child_finished(Node* parent, Move move, Value childValue) {
        const Value score = -childValue;
        bool complete;
        Value value;
        {
            std::lock_guard<std::mutex> parentLock(parent->mutex);
            if (parent->best == MOVE_NONE || score > parent->value) {
                parent->value = score;
                parent->best = move;
            }
            complete = --parent->pending == 0;
            value = parent->value;
        }
        if (complete)
            finish(parent, value);
    }

    void finish(Node* node, Value value) {
        std::vector<Parent> parents;
        {
            std::lock_guard<std::mutex> nodeLock(node->mutex);
            if (node->complete)
                return;
            node->value = value;
            node->complete = true;
            parents = std::move(node->parents);
        }
        for (const Parent& parent : parents)
            child_finished(parent.node, parent.move, value);
        cv.notify_all();
    }

    std::vector<Move> principal_variation() const {
        std::vector<Move> pv;
        const Node* node = root;
        while (node && node->best != MOVE_NONE) {
            pv.push_back(node->best);
            auto it = std::find_if(node->children.begin(), node->children.end(),
                                   [&](const auto& child) { return child.first == node->best; });
            node = it == node->children.end() ? nullptr : it->second;
        }
        return pv;
    }

    const Variant* variant;
    std::string fen;
    bool chess960;
    int depth;
    Node* root = nullptr;
    static constexpr size_t ShardCount = 64;
    static size_t shard(Key key) { return size_t(key) & (ShardCount - 1); }

    std::mutex queueMutex;
    std::condition_variable cv;
    std::deque<Node*> ready;
    std::array<std::mutex, ShardCount> tableMutexes;
    std::array<std::unordered_map<NodeKey, std::unique_ptr<Node>, NodeKeyHash>, ShardCount> table;
    size_t active = 0;
    std::atomic<uint64_t> nodes{0};
};

std::mutex controllerMutex;
std::thread controller;

} // namespace

void start(const Position& pos, int depth) {
    wait();
    Threads.main()->wait_for_search_finished();
    Threads.stop = false;
    auto search = std::make_unique<Search>(pos, depth);
    std::lock_guard<std::mutex> lock(controllerMutex);
    controller = std::thread([search = std::move(search)] {
        search->run();
    });
}

void wait() {
    std::thread old;
    {
        std::lock_guard<std::mutex> lock(controllerMutex);
        if (controller.joinable())
            old = std::move(controller);
    }
    if (old.joinable())
        old.join();
}

} // namespace Stockfish::TDS
