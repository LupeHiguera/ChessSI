# OpenBench builds with `make EXE=<name>` (and may pass CXX); keep both working.
EXE      ?= chesssi
CXX      ?= g++
ARCH     ?= native
LDFLAGS  ?= -pthread

# Apple Silicon and other ARM machines take -mcpu; x86 takes -march.
ifneq ($(filter arm64 aarch64,$(shell uname -m 2>/dev/null)),)
    ARCHFLAG := -mcpu=$(ARCH)
else
    ARCHFLAG := -march=$(ARCH)
endif

CXXFLAGS ?= -std=c++20 -O3 $(ARCHFLAG) -DNDEBUG -Wall -Wextra

ifeq ($(OS),Windows_NT)
    LDFLAGS += -static
endif

SRCS := $(wildcard src/*.cpp)
HDRS := $(wildcard src/*.h)

.PHONY: all debug test test-rfp bench clean

all: $(EXE)

$(EXE): $(SRCS) $(HDRS)
	$(CXX) $(CXXFLAGS) $(SRCS) -o $(EXE) $(LDFLAGS)

# Unoptimised build with sanitizers for hunting crashes and undefined behaviour.
debug:
	$(CXX) -std=c++20 -O1 -g -fsanitize=address,undefined -Wall -Wextra $(SRCS) -o $(EXE)-debug $(LDFLAGS)

# Move generator correctness: every count in tests/perft.epd up to depth 5.
test: $(EXE) $(EXE)-rfp-tests
	./$(EXE) perftsuite tests/perft.epd 5
	./$(EXE)-rfp-tests

# Search boundaries for the shallow reverse futility trial.
$(EXE)-rfp-tests: tests/rfp.cpp $(SRCS) $(HDRS)
	$(CXX) $(CXXFLAGS) tests/rfp.cpp $(filter-out src/main.cpp src/uci.cpp src/search.cpp src/datagen.cpp,$(SRCS)) -o $@ $(LDFLAGS)

test-rfp: $(EXE)-rfp-tests
	./$(EXE)-rfp-tests

bench: $(EXE)
	./$(EXE) bench

clean:
	rm -f $(EXE) $(EXE).exe $(EXE)-debug $(EXE)-rfp-tests
