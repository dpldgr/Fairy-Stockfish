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
#include <condition_variable>
#include <deque>
#include <memory>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include "evaluate.h"
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
    bool complete = false;
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
        StateInfo st;
        Position pos;
        pos.set(variant, fen, chess960, &st, Threads.main());

        auto rootNode = std::make_unique<Node>();
        root = rootNode.get();
        root->key = pos.key();
        root->depth = depth;
        root->queued = true;
        table.emplace(NodeKey{root->key, depth}, std::move(rootNode));
        ready.push_back(root);

        const size_t workerCount = std::max<size_t>(1, Threads.size());
        std::vector<std::thread> workers;
        for (size_t i = 0; i < workerCount; ++i)
            workers.emplace_back(&Search::worker, this, i);
        for (auto& worker : workers)
            worker.join();

        if (root->complete && root->best != MOVE_NONE) {
            auto pv = principal_variation();
            sync_cout << "info depth " << depth << " score cp " << int(root->value)
                      << " nodes " << nodes << " tdsworkers " << workerCount << " pv";
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
        while (true) {
            Node* node;
            {
                std::unique_lock<std::mutex> lock(mutex);
                cv.wait(lock, [&] { return Threads.stop || root->complete || !ready.empty() || active == 0; });
                if (Threads.stop || root->complete || (ready.empty() && active == 0))
                    return;
                if (ready.empty())
                    continue;
                node = ready.front();
                ready.pop_front();
                ++active;
            }

            expand(node, workerId);

            {
                std::lock_guard<std::mutex> lock(mutex);
                --active;
                cv.notify_all();
            }
        }
    }

    void expand(Node* node, size_t workerId) {
        StateInfo rootState;
        Position pos;
        pos.set(variant, fen, chess960, &rootState, Threads[workerId]);
        std::vector<StateInfo> states(node->path.size());
        for (size_t i = 0; i < node->path.size(); ++i)
            pos.do_move(node->path[i], states[i]);

        Value terminal;
        const bool gameEnd = pos.is_game_end(terminal, int(node->path.size()));
        if (gameEnd || node->depth == 0) {
            Value value = gameEnd ? terminal : Eval::evaluate(pos);
            std::lock_guard<std::mutex> lock(mutex);
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

        std::lock_guard<std::mutex> lock(mutex);
        ++nodes;
        node->expanded = true;
        if (successors.empty()) {
            finish(node, VALUE_DRAW);
            return;
        }

        node->pending = successors.size();
        for (const auto& successor : successors) {
            const NodeKey key{successor.second, node->depth - 1};
            auto it = table.find(key);
            Node* child;
            if (it == table.end()) {
                auto inserted = std::make_unique<Node>();
                child = inserted.get();
                child->key = key.key;
                child->depth = key.depth;
                child->path = node->path;
                child->path.push_back(successor.first);
                table.emplace(key, std::move(inserted));
            } else
                child = it->second.get();

            node->children.emplace_back(successor.first, child);
            if (child->complete)
                child_finished(node, successor.first, child->value);
            else {
                child->parents.push_back({node, successor.first});
                if (!child->queued) {
                    child->queued = true;
                    ready.push_back(child);
                }
            }
        }
        cv.notify_all();
    }

    void child_finished(Node* parent, Move move, Value childValue) {
        const Value score = -childValue;
        if (parent->best == MOVE_NONE || score > parent->value) {
            parent->value = score;
            parent->best = move;
        }
        if (--parent->pending == 0)
            finish(parent, parent->value);
    }

    void finish(Node* node, Value value) {
        if (node->complete)
            return;
        node->value = value;
        node->complete = true;
        const auto parents = std::move(node->parents);
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
    std::mutex mutex;
    std::condition_variable cv;
    std::deque<Node*> ready;
    std::unordered_map<NodeKey, std::unique_ptr<Node>, NodeKeyHash> table;
    size_t active = 0;
    uint64_t nodes = 0;
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
