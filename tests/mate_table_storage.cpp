// Standalone boundary and migration tests for the optional mate-table storage.
#include "../src/mate_table_storage.h"

#include <cassert>
#include <iostream>

using Stockfish::MateTableStorage::Nodes;
using Stockfish::MateTableStorage::Status;

int main() {
    Nodes nodes;
    assert(nodes.allocate(8, 1024));
    assert(nodes.header().version == 1 && nodes.header().dtmBits == 14);
    assert(nodes.header().statusBits == 2 && nodes.header().recordBytes == 2);
    assert(nodes.record_bytes() == 16 && nodes.counter_bytes() == 8 && nodes.bytes() == 24);
    for (size_t i = 0; i < 8; ++i)
        assert(nodes.get(i).status == Status::INVALID && nodes.get(i).distance == 0 && nodes.get(i).remaining == 0);
    assert(nodes.set(0, Status::UNRESOLVED_DRAW, 0, 255));
    assert(nodes.set(1, Status::WIN, Nodes::CompactMax, 5));
    assert(nodes.set(2, Status::LOSS, 0, 0));
    assert(nodes.get(1).distance == 16383 && nodes.header().recordBytes == 2);

    // Crossing the 14-bit boundary must preserve every old record and counter.
    assert(nodes.set(3, Status::LOSS, Nodes::CompactMax + 1, 7));
    assert(nodes.header().dtmBits == 30 && nodes.header().recordBytes == 4);
    assert(nodes.get(0).status == Status::UNRESOLVED_DRAW && nodes.get(0).remaining == 255);
    assert(nodes.get(1).status == Status::WIN && nodes.get(1).distance == 16383 && nodes.get(1).remaining == 5);
    assert(nodes.get(2).status == Status::LOSS && nodes.get(2).distance == 0);
    assert(nodes.get(3).distance == 16384 && nodes.get(3).remaining == 7);
    assert(nodes.get(7).status == Status::INVALID);
    assert(nodes.bytes() == 40 && nodes.peak_bytes() == 56);
    assert(nodes.set(4, Status::WIN, 65535, 1));
    assert(nodes.set(5, Status::LOSS, 65536, 2));
    assert(nodes.set(6, Status::WIN, Nodes::WideMax, 3));
    assert(nodes.get(4).distance == 65535 && nodes.get(5).distance == 65536);
    assert(nodes.get(6).distance == Nodes::WideMax);
    nodes.finish();
    assert(!nodes.generating() && nodes.counter_bytes() == 0 && nodes.bytes() == 32);
    assert(nodes.get(1).distance == 16383 && nodes.get(1).remaining == 0);
    assert(nodes.get(0).status == Status::UNRESOLVED_DRAW);

    // The wide limit is checked before shifting or overwriting the old value.
    assert(!nodes.set(6, Status::LOSS, Nodes::WideMax + 1, 0));
    assert(nodes.get(6).status == Status::WIN && nodes.get(6).distance == Nodes::WideMax);

    // Promotion's memory check includes both arrays during migration.
    Nodes limited;
    assert(limited.allocate(8, 40));
    assert(limited.set(1, Status::WIN, Nodes::CompactMax, 1));
    assert(!limited.set(1, Status::LOSS, Nodes::CompactMax + 1, 0));
    assert(limited.header().dtmBits == 14 && limited.bytes() == 24);
    assert(limited.get(1).status == Status::WIN && limited.get(1).distance == Nodes::CompactMax);
    assert(limited.get(1).remaining == 1);
    assert(limited.allocate(8, 1024));
    assert(limited.good() && limited.header().dtmBits == 14);

    // Counter overflow is rejected without truncation.
    assert(limited.set(0, Status::UNRESOLVED_DRAW, 42, 255));
    assert(!limited.set(0, Status::LOSS, 43, 256));
    assert(limited.get(0).remaining == 255 && limited.get(0).distance == 42);

    Nodes compact;
    assert(compact.allocate(8, 1024));
    assert(compact.set(0, Status::WIN, 99, 2));
    compact.finish();
    assert(compact.bytes() == 16 && compact.peak_bytes() == 24);
    assert(compact.get(0).distance == 99 && compact.get(0).remaining == 0);
    assert(!compact.set(0, Status::WIN, 99, 1)); // Counters cannot reappear after completion.

    std::cout << "PASS: packed statuses, DTM boundaries, wide migration, memory limits and counter release\n";
}
