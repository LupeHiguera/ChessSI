# Setting up at home

Steps for the 265K PC (and later the MacBook). Do them in order; each ends with something you can check.

## 1. Toolchain

- **Windows (265K):** use WSL2 so the scripts run as-is. In PowerShell: `wsl --install -d Ubuntu`, reboot,
  then in Ubuntu: `sudo apt update && sudo apt install -y build-essential git`.
- **macOS (M2 Max):** `xcode-select --install`.

## 2. Build and check

```
git clone https://github.com/LupeHiguera/ChessSI.git
cd ChessSI
make
make test           # last line must end "0 failed"
./chesssi bench     # last line: "<nodes> nodes <nps> nps"
```

If the bench node count differs from the one in `README.md`, the build is not the same engine: stop and
find out why before testing anything.

## 3. Coding agents

Install Claude Code and Astra on the PC and open them in the repo folder. Claude Code reads `CLAUDE.md`,
which imports `AGENTS.md`. If Astra does not pick up `AGENTS.md` by itself, tell it to read that file
first. Both follow the same loop, so their results go in the same log and can be compared.

## 4. Testing tools

- **fastchess:** download a release binary from https://github.com/Disservin/fastchess/releases and put
  it on your `PATH`, or set `FASTCHESS=/path/to/fastchess`.
- **Opening book:** from https://github.com/official-stockfish/books download
  `UHO_Lichess_4852_v1.epd.zip` and unzip it to `books/UHO_Lichess_4852_v1.epd` (git ignores `books/`).
- **Pipeline check:** `scripts/sprt.sh` with no changes plays the engine against itself. Let it run a few
  hundred games: Elo should hover around 0. Stop it with Ctrl+C.

The 265K has 8 P-cores and 12 E-cores. For tests that must be comparable, set `CONCURRENCY=8` and keep
the machine otherwise idle.

## 5. Play it

Add `chesssi` as a UCI engine in Cute Chess, Arena or En Croissant and play a few games against it.

## 6. A dedicated Linux worker (no GPU needed)

A second machine running an Ubuntu-based Linux (Pop!_OS works) can take the datagen and SPRTs, so they
keep going while the main PC is in use. Networks are still trained on the PC with the GPU.

1. Install the OS, then `sudo apt install openssh-server`. Turn off automatic suspend, and give the
   machine a fixed IP or hostname.
2. Clone the repo and run `scripts/setup-worker.sh`. It installs build tools, fastchess, both opening
   books and the Stash gauntlet pool, then checks perft and the bench.
3. Run jobs under `nohup`, `tmux` or systemd user services so they survive the SSH session:
   `scripts/datagen.sh <gen> "<cores>"`, `scripts/nnue-sprt.sh`, `scripts/run-idea.sh`.
4. Move data with `rsync` over SSH. For example, from the training PC:
   `rsync -a worker:nnue/data/dg5/ ~/nnue/data/dg5/` before training, and copy networks back the same
   way.

The 265K's 8 P-cores and 12 E-cores differ in speed. Keep each SPRT on one core type (`lscpu -e` shows
which is which).

## 7. OpenBench (once more than one machine tests)

The engine is ready for it: `make EXE=<name>` builds it, and `chesssi bench` prints `<nodes> nodes <nps>
nps` as its last line. Follow the OpenBench README (https://github.com/AndyGrant/OpenBench) to run the
server on the PC and connect the PC and the MacBook as clients.
