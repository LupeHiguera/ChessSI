.PHONY: all
all:
	taskset -c 19 g++ -std=c++20 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -Wall -Wextra check.cpp src/bitboard.cpp src/eval.cpp src/movegen.cpp src/position.cpp src/tt.cpp -o check -pthread
