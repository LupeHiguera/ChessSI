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
make test           # last line must say "35 passed, 0 failed"
./chesssi bench     # last line: "20648203 nodes ... nps"
```

If the bench node count differs from the one in `docs/IDEAS.md`, the build is not the same engine: stop
and find out why before testing anything.

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

## 6. OpenBench (once more than one machine tests)

The engine is ready for it: `make EXE=<name>` builds it, and `chesssi bench` prints `<nodes> nodes <nps>
nps` as its last line. Follow the OpenBench README (https://github.com/AndyGrant/OpenBench) to run the
server on the PC and connect the PC and the MacBook as clients.
