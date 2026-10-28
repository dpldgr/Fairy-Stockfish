# Shared native/WebAssembly build capabilities. Keep the request for diagnostics.
piece_slots ?= 64
gating ?= yes

# Strip digits without invoking a shell on unchecked input.
piece_slots_nondigits := $(subst 0,,$(subst 1,,$(subst 2,,$(subst 3,,$(subst 4,,$(subst 5,,$(subst 6,,$(subst 7,,$(subst 8,,$(subst 9,,$(piece_slots)))))))))))
ifneq ($(piece_slots_nondigits),)
$(error piece_slots must be an integer between 64 and 512)
endif
ifneq ($(words $(piece_slots)),1)
$(error piece_slots must be an integer between 64 and 512)
endif
effective_piece_slots := $(shell printf '%s\n' '$(piece_slots)' | awk '$$0 >= 64 && $$0 <= 512 {print int(($$0 + 63) / 64) * 64}')
ifeq ($(effective_piece_slots),)
$(error piece_slots must be between 64 and 512)
endif

ifneq ($(gating),yes)
ifneq ($(gating),no)
$(error gating must be yes or no)
endif
endif
CXXFLAGS += -DPIECE_TYPE_CAPACITY=$(effective_piece_slots) -DENABLE_GATING=$(if $(filter yes,$(gating)),1,0)
