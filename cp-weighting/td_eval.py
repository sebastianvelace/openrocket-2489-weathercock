#!/usr/bin/env python3
"""
Offline replica of OpenRocket's TumbleDetector, and evaluation of candidate detectors against the oracle.

Why offline is valid: the detector influences a simulation only through the TUMBLE event it emits. Until
that moment the real run and the oracle run (detector disabled, recovery disabled) are the same flight, so
replaying a detector over the oracle trajectory gives the time at which it would fire in the real run,
provided that time precedes the real run's deployment or ground hit. The replica is validated by
reproducing the real runs' TUMBLE times exactly (mode `validate`) before any candidate is scored.

Candidates (defined before evaluation; no constant is tuned -- all keep 60 deg, 2 periods, 0.05-2 s):
  C0  current: tau from the natural frequency at the current AoA (TYPE_NATURAL_FREQUENCY)
  C1  reverse-flow hold: while AoA > 90 deg, keep the last tau computed with AoA <= 90 deg
  C2  small-angle frequency: tau from the pitch natural frequency evaluated at AoA ~ 0 (omega0), i.e. from
      the aerodynamic model inside its validity envelope; NaN (unstable at small angles) -> 0.05 s
  C3  constant tau = 0.5 s (baseline: no airframe scaling)

Usage:
  td_eval.py validate <real.tsv> <oracle.tsv> <trace_dir>
  td_eval.py score    <real_base.tsv> <real_fix.tsv> <oracle_base.tsv> <traces_base> <traces_fix>
"""
import collections
import csv
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ref  # noqa: E402
import evaluate_fast as ef  # noqa: E402

THRESH = math.radians(60)
MIN_Q = 1.0
DWELL = 2.0
TMIN, TMAX = 0.05, 2.0


def tau_from_omega(w):
    if math.isnan(w) or w <= 0:
        return TMIN
    return min(max(DWELL * 2 * math.pi / w, TMIN), TMAX)


def load_branch(trace_dir, key4, branch, own):
    """Trace columns plus omega0 aligned by (branch name, time); inherited rows take the parent's omega0."""
    path = os.path.join(trace_dir, "_".join(key4) + f"_b{branch}.tsv")
    lines = open(path).read().split("\n")
    rows = list(csv.reader([l for l in lines if l and not l.startswith("#")], delimiter="\t"))
    col = {h: i for i, h in enumerate(rows[0])}
    data = rows[1:]
    om = collections.defaultdict(dict)
    opath = os.path.join(trace_dir, "_".join(key4) + "_omega0.tsv")
    for l in open(opath):
        n, t, w, q = l.rstrip("\n").split("\t")
        om[n][t] = float(w)
    out = []
    for r in data:
        ts = r[col["Time"]]
        w0 = om.get(own, {}).get(ts)
        if w0 is None:
            for n, d in om.items():
                if ts in d:
                    w0 = d[ts]
                    break
        g = lambda name: float(r[col[name]])
        v = g("Mach_number") * g("Speed_of_sound")
        out.append((g("Time"), g("Angle_of_attack"), g("Natural_frequency"), 0.5 * g("Air_density") * v * v,
                    math.nan if w0 is None else w0))
    return out


def replay(rows, rod_t, mode, rod_inclusive=False):
    """
    Mirror BasicEventSimulationEngine: after each step the detector reads the last stored row (the state at
    the start of that step, time t_n) but is stamped with the simulation time after the step (t_{n+1}), and
    the launch-guide flag becomes true only in the iteration after the LAUNCHROD event (time t_rod).
    """
    filt, last, last_tau_fwd = 0.0, math.nan, None
    for n in range(len(rows) - 1):
        _, aoa, wn, q, w0 = rows[n]
        t = rows[n + 1][0]
        dt = 0.0 if math.isnan(last) else t - last
        last = t
        cleared = (t >= rod_t) if rod_inclusive else (t > rod_t)
        if dt <= 0 or not cleared or math.isnan(aoa) or math.isnan(q) or q < MIN_Q:
            if filt > THRESH:
                return t
            continue
        if mode == "C0":
            tau = tau_from_omega(wn)
        elif mode == "C1":
            if aoa <= math.pi / 2 or last_tau_fwd is None:
                tau = tau_from_omega(wn)
                if aoa <= math.pi / 2:
                    last_tau_fwd = tau
            else:
                tau = last_tau_fwd
        elif mode == "C2":
            tau = tau_from_omega(w0)
        elif mode == "C3":
            tau = 0.5
        filt += (1 - math.exp(-dt / tau)) * (aoa - filt)
        if filt > THRESH:
            return t
    return None


def names_from(oracle_tsv):
    return {(r["rocket"], r["sim"], r["wind"], r["branch"]): r["branch_name"]
            for r in csv.DictReader(open(oracle_tsv), delimiter="\t")}


def real_fire(r):
    t = ref.num(r["tumble_t"])
    if math.isnan(t) and "TUMBLE" in r["abort"]:
        t = ref.num(r["abort_t"])
    return t


def horizon(r, oracle_row):
    ends = [ref.num(r["deploy_t"]), ref.num(r["land_t"])]
    ends = [e for e in ends if not math.isnan(e)]
    if not ends:
        ends = [ref.num(oracle_row["land_t"])]
    return min(e for e in ends if not math.isnan(e)) if ends else math.inf


def predictions(real, oracle, td, names, mode, rod_inclusive=False):
    pred = {}
    for k, r in real.items():
        key4 = (k[0], k[1], k[2], "0")
        rows = load_cached(td, key4, k[4], names)
        rod = ref.num(r["launchrod_t"])
        if math.isnan(rod):
            # a separated stage has no LAUNCHROD event of its own; it inherits the main branch's state
            rod = ref.num(real[(k[0], k[1], k[2], k[3], "0")]["launchrod_t"])
        t = replay(rows, rod if not math.isnan(rod) else 0.0, mode, rod_inclusive)
        H = horizon(r, oracle[(k[0], k[1], k[2], "0", k[4])])
        pred[k] = t if (t is not None and t < H + 1e-12) else None
    return pred


_cache = {}


def load_cached(td, key4, b, names):
    kk = (td, key4, b)
    if kk not in _cache:
        _cache[kk] = load_branch(td, key4, b, names.get((key4[0], key4[1], key4[2], b)))
    return _cache[kk]


def validate(real_tsv, oracle_tsv, td):
    real = ref.load_rows(real_tsv)
    oracle = ref.load_rows(oracle_tsv)
    names = names_from(oracle_tsv)
    for incl in (False, True):
        pred = predictions(real, oracle, td, names, "C0", incl)
        ok = bad = 0
        bads = []
        for k, r in real.items():
            rf = real_fire(r)
            p = pred[k]
            same = (math.isnan(rf) and p is None) or (p is not None and not math.isnan(rf) and abs(p - rf) < 5.000001e-7)  # summary times are printed with 6 decimals
            if same:
                ok += 1
            else:
                bad += 1
                bads.append((k, rf, p))
        print(f"replica C0 (rod {'>=' if incl else '>'}): {ok} branches reproduced exactly, {bad} differ")
        for b in bads[:10]:
            print("   ", b)


def score_pred(pred, real, oracle_rows, td_truth, A, D, W, min_margin):
    """FP/FN/TP/TN of a set of predicted firing times, against the base oracle (truth)."""
    c = collections.Counter()
    for k, r in real.items():
        tr = ef.trace(os.path.join(td_truth, "_".join(k[:3]) + "_0_b" + k[4] + ".tsv"))
        H = horizon(r, oracle_rows[(k[0], k[1], k[2], "0", k[4])])
        rod = ref.num(r["launchrod_t"])
        t0 = rod if not math.isnan(rod) else 0.0
        p = pred[k]
        if p is not None:
            j = tr.justified(p, A, D, W)
            c["TP" if j else "FP"] += 1
        else:
            ts = ef.truth_onset(tr, t0, H, A, D, W, "settle")
            if ts is not None and H - ts >= min_margin:
                c["FN"] += 1
            else:
                c["TN"] += 1
    return c


def score(rb, rf, ob, tdb, tdf):
    RB, RF, OB = ref.load_rows(rb), ref.load_rows(rf), ref.load_rows(ob)
    # The replica reproduces the real detector exactly on main branches only (validated); separated stages
    # are excluded from the candidate comparison.
    RB = {k: v for k, v in RB.items() if k[4] == "0"}
    RF = {k: v for k, v in RF.items() if k[4] == "0"}
    print(f"main-branch flights scored: {len(RB)}")
    names = names_from(ob)
    preds = {}
    for cp, real, td in (("base", RB, tdb), ("fix", RF, tdf)):
        for m in ("C0", "C1", "C2", "C3"):
            preds[(cp, m)] = predictions(real, OB, td, names, m)
    print("PRIMARY (A=20, D=0.5, W=3; misses counted if margin >= 0.5 s)")
    for (cp, m), pred in sorted(preds.items()):
        real = RB if cp == "base" else RF
        c = score_pred(pred, real, OB, tdb, 20, 0.5, 3, 0.5)
        print(f"  CP {cp:4s} {m}: TP {c['TP']:3d} FP {c['FP']:3d} FN {c['FN']:3d} TN {c['TN']:4d}  errors {c['FP'] + c['FN']:3d}")
    print("\nGRID (27 variants) x margin: errors per detector, summed over the grid, and wins vs current (C0, base CP)")
    grid = list(itertools.product((15, 20, 30), (0.3, 0.5, 1.0), (2, 3, 5)))
    for mm in (0.5, 1.0, 2.0):
        ref_err = {}
        tot = {}
        per = collections.defaultdict(list)
        for g in grid:
            for (cp, m), pred in preds.items():
                real = RB if cp == "base" else RF
                c = score_pred(pred, real, OB, tdb, *g, mm)
                per[(cp, m)].append(c["FP"] + c["FN"])
        base = per[("base", "C0")]
        print(f"  margin >= {mm} s:")
        for (cp, m), errs in sorted(per.items()):
            w = sum(e < b for e, b in zip(errs, base))
            l = sum(e > b for e, b in zip(errs, base))
            print(f"    CP {cp:4s} {m}: total errors {sum(errs):4d}  (min {min(errs)}, max {max(errs)})  better than C0/base in {w}/27, worse in {l}/27")
    print("\nPER-ROCKET errors (primary, margin >= 0.5 s)")
    rockets = sorted({k[0] for k in RB})
    hdr = [f"{cp}/{m}" for cp in ("base", "fix") for m in ("C0", "C1", "C2", "C3")]
    print("  " + f"{'rocket':36s}" + "".join(f"{h:>9s}" for h in hdr))
    for rk in rockets:
        line = f"  {rk[:35]:36s}"
        for cp in ("base", "fix"):
            real = RB if cp == "base" else RF
            for m in ("C0", "C1", "C2", "C3"):
                sub = {k: v for k, v in real.items() if k[0] == rk}
                pr = {k: preds[(cp, m)][k] for k in sub}
                c = score_pred(pr, sub, OB, tdb, 20, 0.5, 3, 0.5)
                line += f"{c['FP'] + c['FN']:9d}"
        print(line)
    return preds


if __name__ == "__main__":
    if sys.argv[1] == "validate":
        validate(*sys.argv[2:5])
    else:
        score(*sys.argv[2:7])
