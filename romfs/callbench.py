# Benchmark the MicroPython -> C++ native call boundary, across call kinds.
#
#   import callbench; callbench.run()
#
# Method: time a tight loop of N identical calls with the Cortex-M33 DWT cycle
# counter (bench.cyc), subtract an identical empty loop, divide by N. The loop
# keeps code hot in the XIP cache and amortises interrupts, so results are
# stable. Min over a few runs rejects outliers.
#
#   Non-allocating tests run with GC disabled (clean dispatch cost).
#   Allocating tests run with GC ENABLED: the per-call figure therefore
#   includes amortised garbage collection - the real cost of repeatedly
#   calling something that returns a fresh object. B/call is the heap used.

import bench
import gc
import machine

FREQ = machine.freq()
US = 1_000_000 / FREQ      # microseconds per CPU cycle
MASK = 0xFFFFFFFF

RUNS = 5
SCALAR_N = 20_000          # calls per timed loop (non-allocating)
# Allocating tests: GC disabled, heap collected before each run. The 8MB PSRAM
# heap easily absorbs the discarded objects from one run, so we measure pure
# construction cost with no GC interference.
ALLOC_N = 2_000
ALLOC_RUNS = 8

bench.cyc_init()
_cyc = bench.cyc

_thing = bench.Thing()
_Thing = bench.Thing


def _make_loop(expr, nvals):
    argsig = "".join(", a%d" % i for i in range(nvals))
    src = (
        "def loop(cyc, n%s):\n"
        "    t0 = cyc()\n"
        "    while n:\n"
        "        %s\n"
        "        n -= 1\n"
        "    return (cyc() - t0) & 0x%x\n"
    ) % (argsig, expr, MASK)
    g = {}
    exec(src, g)
    return g["loop"]


def _empty_loop():
    src = (
        "def loop(cyc, n):\n"
        "    t0 = cyc()\n"
        "    while n:\n"
        "        n -= 1\n"
        "    return (cyc() - t0) & 0x%x\n"
    ) % MASK
    g = {}
    exec(src, g)
    return g["loop"]


def _min_loop(loop, args, gc_off, runs=RUNS):
    best = None
    for _ in range(runs):
        gc.collect()
        if gc_off:
            gc.disable()
        d = loop(*args)
        gc.enable()
        if best is None or d < best:
            best = d
    return best


def _make_call(expr, nvals):
    argsig = ", ".join("a%d" % i for i in range(nvals))
    src = "def call(%s):\n    return %s\n" % (argsig, expr)
    g = {}
    exec(src, g)
    return g["call"]


def _bytes_per_call(callfn, vals, n=200):
    gc.collect()
    gc.disable()
    m0 = gc.mem_alloc()
    for _ in range(n):
        callfn(*vals)
    d = gc.mem_alloc() - m0
    gc.enable()
    gc.collect()
    return d / n


_EMPTY = _empty_loop()


def _bench(expr, vals, alloc):
    nvals = len(vals)
    n = ALLOC_N if alloc else SCALAR_N
    runs = ALLOC_RUNS if alloc else RUNS
    loop = _make_loop(expr, nvals)
    measured = _min_loop(loop, (_cyc, n) + vals, gc_off=True, runs=runs)
    baseline = _min_loop(_EMPTY, (_cyc, n), gc_off=True, runs=runs)
    cyc = (measured - baseline) / n
    nb = _bytes_per_call(_make_call(expr, nvals), vals) if alloc else 0.0
    return cyc, nb


# (label, call-expression, arg values, allocates?)
TESTS = (
    ("== module function ==", None, (), False),
    ("noargs",        "a0()",                 (bench.noargs,), False),
    ("arg1",          "a0(a1)",               (bench.arg1, 1), False),
    ("arg2",          "a0(a1,a2)",            (bench.arg2, 1, 2), False),
    ("arg3",          "a0(a1,a2,a3)",         (bench.arg3, 1, 2, 3), False),
    ("arg4 (var)",    "a0(a1,a2,a3,a4)",      (bench.arg4, 1, 2, 3, 4), False),
    ("arg8 (var)",    "a0(a1,a2,a3,a4,a5,a6,a7,a8)", (bench.arg8, 1, 2, 3, 4, 5, 6, 7, 8), False),

    ("== argument decoding (x3) ==", None, (), False),
    ("take_ptr",      "a0(a1,a2,a3)",         (bench.take_ptr, _thing, _thing, _thing), False),
    ("take_int",      "a0(a1,a2,a3)",         (bench.take_int, 1, 2, 3), False),
    ("take_float",    "a0(a1,a2,a3)",         (bench.take_float, 1.5, 2.5, 3.5), False),

    ("== keyword args ==", None, (), False),
    ("argkw raw",     "a0(bka=a1)",           (bench.argkw, 1), False),
    ("argparse pos",  "a0(a1,a2,a3)",         (bench.argparse, 1, 2, 3), False),
    ("argparse kw",   "a0(bka=a1,bkb=a2,bkc=a3)", (bench.argparse, 1, 2, 3), False),

    ("== method dispatch ==", None, (), False),
    ("m0 (self)",     "a0.m0()",              (_thing,), False),
    ("m1 (self+1)",   "a0.m1(a1)",            (_thing, 1), False),
    ("m3 (self+3)",   "a0.m3(a1,a2,a3)",      (_thing, 1, 2, 3), False),
    ("static s0",     "a0.s0()",              (_Thing,), False),
    ("mkw kw-parse",  "a0.mkw(bka=a1,bkb=a2,bkc=a3)", (_thing, 1, 2, 3), False),

    ("== return construction (no GC) ==", None, (), False),
    ("ret_none",      "a0()",                 (bench.ret_none,), False),
    ("ret_int",       "a0()",                 (bench.ret_int,), False),
    ("ret_float",     "a0()",                 (bench.ret_float,), False),
    ("ret_bool",      "a0()",                 (bench.ret_bool,), False),
    ("ret_tuple2",    "a0()",                 (bench.ret_tuple2,), True),
    ("ret_tuple8",    "a0()",                 (bench.ret_tuple8,), True),
    ("ret_list(16)",  "a0(a1)",               (bench.ret_list, 16), True),
    ("ret_list(64)",  "a0(a1)",               (bench.ret_list, 64), True),
    ("ret_bytes(16)", "a0(a1)",               (bench.ret_bytes, 16), True),
    ("ret_bytes(64)", "a0(a1)",               (bench.ret_bytes, 64), True),

    ("== object creation (no GC) ==", None, (), False),
    ("make_plain",    "a0.make_plain()",      (_thing,), True),
    ("make (finalis)","a0.make()",            (_thing,), True),
    ("Thing() ctor",  "a0()",                 (_Thing,), True),
)


def run():
    a = _cyc()
    for _ in range(1000):
        pass
    if ((_cyc() - a) & MASK) == 0:
        print("WARNING: DWT cycle counter not advancing")

    print("CPU %d MHz  (%.4f us/cycle)" % (FREQ // 1_000_000, US))
    print("loop-difference, min of runs; GC off, heap cleared per run\n")
    print("%-18s %8s %9s %8s" % ("test", "cyc", "us", "B/call"))
    print("-" * 47)
    for label, expr, vals, alloc in TESTS:
        if expr is None:
            print(label)
            continue
        cyc, nb = _bench(expr, vals, alloc)
        print("%-18s %8.0f %9.3f %8.1f" % (label, cyc, cyc * US, nb))


if __name__ == "__main__":
    run()
