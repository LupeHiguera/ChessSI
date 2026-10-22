# Run from the repository root. Outputs stay under ignored engines/ by default.
CXX ?= g++
CXXFLAGS ?= -std=c++20 -O2 -DNDEBUG -Wall -Wextra
LDFLAGS ?= -pthread
EXE ?= engines/tt-clock-context

PROBE := tests/diagnostics/tt_clock_context.cpp
SUPPORT := src/bitboard.cpp src/position.cpp src/movegen.cpp src/eval.cpp src/tt.cpp

.PHONY: all report
all: $(EXE)

$(EXE): $(PROBE) src/search.cpp $(SUPPORT) $(wildcard src/*.h)
	mkdir -p $(dir $(EXE))
	$(CXX) $(CXXFLAGS) -Isrc $(PROBE) $(SUPPORT) -o $(EXE) $(LDFLAGS)

report: $(EXE)
	./$(EXE)
