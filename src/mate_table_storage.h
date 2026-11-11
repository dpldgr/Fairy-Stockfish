/*
  Fairy-Stockfish, a UCI chess variant playing engine derived from Stockfish
  Copyright (C) 2026 The Fairy-Stockfish developers

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.
*/

#ifndef MATE_TABLE_STORAGE_H_INCLUDED
#define MATE_TABLE_STORAGE_H_INCLUDED

#include <cassert>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <new>
#include <utility>

namespace Stockfish {
namespace MateTableStorage {

enum class Status : uint8_t { INVALID, UNRESOLVED_DRAW, WIN, LOSS };

struct Header {
  uint8_t version = 1;
  uint8_t dtmBits = 14;
  uint8_t statusBits = 2;
  uint8_t recordBytes = 2;
};
static_assert(sizeof(Header) == 4, "Unexpected mate-table storage header size");

struct Value {
  uint32_t distance;
  uint16_t remaining;
  Status status;
};

// Each record is [DTM:14 | status:2], promoted to [DTM:30 | status:2]
// on overflow. Counters are a separate construction-only byte array.
class Nodes {
public:
  static constexpr uint32_t CompactMax = (uint32_t(1) << 14) - 1;
  static constexpr uint32_t WideMax = (uint32_t(1) << 30) - 1;

  bool allocate(size_t count, uint64_t limit) {
    if (!count || count > std::numeric_limits<size_t>::max() / 7 || count > limit / 3)
        return fail("mate-table compact storage memory budget exceeded");
    std::unique_ptr<uint16_t[]> records(new (std::nothrow) uint16_t[count]());
    std::unique_ptr<uint8_t[]> counters(new (std::nothrow) uint8_t[count]());
    if (!records || !counters) return fail("mate-table compact storage allocation failed");
    compact = std::move(records);
    remaining = std::move(counters);
    wide.reset();
    size = count;
    memoryLimit = limit;
    layout = Header{};
    peakBytes = bytes();
    failure = nullptr;
    return true;
  }

  Value get(size_t i) const {
    assert(i < size);
    uint32_t record = wide ? wide[i] : compact[i];
    return {record >> 2, uint16_t(remaining ? remaining[i] : 0), Status(record & 3)};
  }

  bool set(size_t i, Status status, uint32_t distance, uint16_t successors) {
    if (!good()) return false;
    if (i >= size || uint8_t(status) > 3) return fail("invalid mate-table storage index or status");
    if (successors > 255 || (!remaining && successors)) return fail("mate-table successor count overflow");
    if (distance > WideMax) return fail("mate-table DTM exceeds 30-bit fallback");
    if (!wide && distance > CompactMax && !promote()) return false;
    uint32_t record = (distance << 2) | uint8_t(status);
    if (wide) wide[i] = record;
    else compact[i] = uint16_t(record);
    if (remaining) remaining[i] = uint8_t(successors);
    return true;
  }

  void finish() { remaining.reset(); }
  bool generating() const { return bool(remaining); }
  bool good() const { return failure == nullptr; }
  const char* error() const { return failure; }
  const Header& header() const { return layout; }
  uint64_t bytes() const { return record_bytes() + counter_bytes(); }
  uint64_t record_bytes() const { return uint64_t(size) * layout.recordBytes; }
  uint64_t counter_bytes() const { return remaining ? uint64_t(size) : 0; }
  uint64_t peak_bytes() const { return peakBytes; }

private:
  size_t size = 0;
  uint64_t memoryLimit = 0, peakBytes = 0;
  Header layout;
  const char* failure = nullptr;
  std::unique_ptr<uint16_t[]> compact;
  std::unique_ptr<uint32_t[]> wide;
  std::unique_ptr<uint8_t[]> remaining;

  bool fail(const char* text) { failure = text; return false; }

  bool promote() {
    // Include both arrays during conversion, not just the final wider table.
    uint64_t temporaryBytes = bytes() + uint64_t(size) * sizeof(uint32_t);
    if (temporaryBytes > memoryLimit) return fail("mate-table DTM promotion memory budget exceeded");
    std::unique_ptr<uint32_t[]> records(new (std::nothrow) uint32_t[size]);
    if (!records) return fail("mate-table DTM promotion allocation failed");
    for (size_t i = 0; i < size; ++i) records[i] = compact[i];
    wide = std::move(records);
    compact.reset();
    layout.dtmBits = 30;
    layout.recordBytes = 4;
    if (temporaryBytes > peakBytes) peakBytes = temporaryBytes;
    return true;
  }
};

} // namespace MateTableStorage
} // namespace Stockfish

#endif
