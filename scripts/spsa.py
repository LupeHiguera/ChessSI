#!/usr/bin/env python3
"""SPSA tuning of the search constants of a `make TUNE=1` build, with fastchess playing the games.

    scripts/spsa.py run --engine ./chesssi-tune --book books/UHO_Lichess_4852_v1.epd \\
        --state spsa.json --pairs 20000 --cpus 1-4,8-19 --peak-pause
    scripts/spsa.py show --state spsa.json
    scripts/spsa.py apply --state spsa.json --source src/search.cpp

One worker per listed core. Each worker draws its own +/- perturbation of every parameter, plays one game
pair (both colours of one opening) between the two perturbed engines, and moves the parameters toward the
side that scored more. The schedule is the fishtest one: c_k = c / k^gamma, a_k = a / (A + k)^alpha, with
c_end and r_end = a_end / c_end^2 given per parameter at the last iteration. The state file is rewritten
after every pair, so a stopped run continues from it.
"""
import argparse, json, os, random, re, signal, subprocess, sys, threading, time

ALPHA, GAMMA, A_RATIO = 0.602, 0.101, 0.1


def read_params(engine):
    out = subprocess.run([engine], input="tune\nquit\n", capture_output=True, text=True, timeout=60).stdout
    params = []
    for line in out.splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) == 5 and f[1] == "int":
            params.append({"name": f[0], "default": int(f[2]), "min": int(f[3]), "max": int(f[4])})
    if not params:
        sys.exit(f"{engine} lists no parameters: build it with `make TUNE=1`")
    return params


def parse_cpus(text):
    cpus = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        cpus += range(int(lo), int(hi or lo) + 1)
    return cpus


def new_state(args):
    params = read_params(args.engine)
    for p in params:
        p["c_end"] = max(0.5, (p["max"] - p["min"]) / args.c_div)
        p["r_end"] = args.r_end
        p["theta"] = float(p["default"])
    return {"pairs": args.pairs, "done": 0, "tc": args.tc, "params": params, "score": [0, 0, 0]}


def save(state, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, path)


def in_peak():
    t = time.localtime()
    return t.tm_wday < 5 and 16 <= t.tm_hour < 19


class Run:
    def __init__(self, args, state):
        self.args, self.state = args, state
        self.lock = threading.Lock()
        self.stop = False
        self.started = 0
        self.book_size = sum(1 for _ in open(args.book))

    def held(self):
        return (self.args.peak_pause and in_peak()) or (self.args.pause_file and os.path.exists(self.args.pause_file))

    def perturb(self):
        with self.lock:
            if self.stop or self.state["done"] + self.started >= self.state["pairs"]:
                return None
            self.started += 1
            k = self.state["done"] + self.started
            n = self.state["pairs"]
            plan = []
            for p in self.state["params"]:
                c = p["c_end"] * n ** GAMMA / k ** GAMMA
                a_end = p["r_end"] * p["c_end"] ** 2
                a = a_end * (A_RATIO * n + n) ** ALPHA / (A_RATIO * n + k) ** ALPHA
                delta = random.choice((-1, 1))
                plan.append((p, c, a / c, delta))
            return plan

    def play(self, plan, cpu):
        def options(sign):
            out = []
            for p, c, _, delta in plan:
                v = round(min(p["max"], max(p["min"], p["theta"] + sign * c * delta)))
                out.append(f"option.{p['name']}={v}")
            return out
        cmd = ["taskset", "-c", str(cpu), self.args.fastchess,
               "-engine", f"cmd={self.args.engine}", "name=plus", *options(1),
               "-engine", f"cmd={self.args.engine}", "name=minus", *options(-1),
               "-each", f"tc={self.state['tc']}", f"option.Hash={self.args.hash}", "option.Threads=1",
               "-openings", f"file={self.args.book}", "format=epd", "order=random",
               f"start={random.randrange(self.book_size) + 1}",
               "-rounds", "1", "-games", "2", "-repeat", "-recover",
               "-resign", "movecount=3", "score=400", "twosided=true",
               "-draw", "movenumber=40", "movecount=8", "score=10",
               "-concurrency", "1", "-srand", str(random.randrange(1 << 31))]
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        m = re.search(r"Games: (\d+), Wins: (\d+), Losses: (\d+), Draws: (\d+)", out)
        if not m or int(m.group(1)) != 2:
            return None
        return int(m.group(2)), int(m.group(3)), int(m.group(4))

    def finish(self, plan, result):
        with self.lock:
            self.started -= 1
            if result is None:
                return
            wins, losses, draws = result
            for p, c, r, delta in plan:
                p["theta"] = min(p["max"], max(p["min"], p["theta"] + r * c * (wins - losses) * delta))
            s = self.state
            s["done"] += 1
            s["score"] = [s["score"][0] + wins, s["score"][1] + losses, s["score"][2] + draws]
            save(s, self.args.state)
            if s["done"] % self.args.log_every == 0 or s["done"] == s["pairs"]:
                values = " ".join(f"{p['name']}={p['theta']:.2f}" for p in s["params"])
                print(f"{time.strftime('%F %T')} pairs {s['done']}/{s['pairs']} +{s['score'][0]} -{s['score'][1]} ={s['score'][2]} | {values}", flush=True)

    def worker(self, cpu):
        failures = 0
        while not self.stop:
            if self.held():
                time.sleep(20)
                continue
            plan = self.perturb()
            if plan is None:
                return
            result = self.play(plan, cpu)
            self.finish(plan, result)
            failures = failures + 1 if result is None else 0
            if failures >= 5:
                print(f"core {cpu}: five failed pairs in a row, worker stops", flush=True)
                return


def run(args):
    if os.path.exists(args.state):
        state = json.load(open(args.state))
    else:
        state = new_state(args)
        save(state, args.state)
    r = Run(args, state)
    def on_signal(*_):
        r.stop = True
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    print(f"{time.strftime('%F %T')} start at pair {state['done']}/{state['pairs']}, tc {state['tc']}, cores {args.cpus}", flush=True)
    threads = [threading.Thread(target=r.worker, args=(c,)) for c in parse_cpus(args.cpus)]
    for t in threads:
        t.start()
    for t in threads:
        while t.is_alive():
            t.join(1)
    print(f"{time.strftime('%F %T')} stopped at pair {state['done']}/{state['pairs']}", flush=True)


def show(args):
    state = json.load(open(args.state))
    print(f"pairs {state['done']}/{state['pairs']}, score +{state['score'][0]} -{state['score'][1]} ={state['score'][2]}")
    for p in state["params"]:
        print(f"{p['name']:12} {p['default']:6} -> {round(p['theta']):6}  ({p['theta']:.2f}, range {p['min']}..{p['max']})")


def apply(args):
    state = json.load(open(args.state))
    src = open(args.source).read()
    for p in state["params"]:
        pattern = rf"PARAM\({p['name']}, -?\d+,"
        if len(re.findall(pattern, src)) != 1:
            sys.exit(f"{p['name']}: no single PARAM line in {args.source}")
        src = re.sub(pattern, f"PARAM({p['name']}, {round(p['theta'])},", src)
    open(args.source, "w").write(src)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--engine", required=True)
    r.add_argument("--book", required=True)
    r.add_argument("--state", required=True)
    r.add_argument("--pairs", type=int, default=20000)
    r.add_argument("--cpus", required=True, help="cores to pin one worker each to, such as 1-4,8-19")
    r.add_argument("--tc", default="10+0.1")
    r.add_argument("--hash", type=int, default=16)
    r.add_argument("--fastchess", default="fastchess")
    r.add_argument("--c-div", type=float, default=20, help="c_end = (max - min) / this")
    r.add_argument("--r-end", type=float, default=0.002)
    r.add_argument("--log-every", type=int, default=100)
    r.add_argument("--pause-file", help="workers wait while this file exists")
    r.add_argument("--peak-pause", action="store_true", help="wait from 16:00 to 19:00, Monday to Friday")
    r.set_defaults(func=run)
    for name, func in (("show", show), ("apply", apply)):
        s = sub.add_parser(name)
        s.add_argument("--state", required=True)
        if name == "apply":
            s.add_argument("--source", default="src/search.cpp")
        s.set_defaults(func=func)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
