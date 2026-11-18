#!/usr/bin/env python3
"""
Fast, behavior-identical implementation of evaluate.py (same definitions; see that file's docstring).

The settle rule is answered from precomputed runs of consecutive samples with AoA < A, and the thrust rule
from precomputed sample indices with thrust > 0 and theta < 0. Chronological precedence is the same as in
evaluate.justified: at a given sample the thrust rule is checked before the settle rule.
`--check N` compares this implementation with evaluate.justified on N random (trace, time, parameter) cases.

Usage: evaluate_fast.py <real_base.tsv> <real_fix.tsv> <oracle.tsv> <trace_dir> [--check N]
"""
import bisect
import glob
import itertools
import math
import multiprocessing as mp
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ref  # noqa: E402

TRACES = {}


class Trace:
    def __init__(self, path):
        self.t, self.aoa, self.theta, self.thrust = ref.load_trace(path)
        self.raw = (self.t, self.aoa, self.theta, self.thrust)
        self.hits = [i for i in range(len(self.t)) if self.thrust[i] > 0 and self.theta[i] < 0]
        self.big = [i for i in range(len(self.t)) if (self.thrust[i] > 0 and self.theta[i] < 0)
                    or (not math.isnan(self.aoa[i]) and self.aoa[i] >= 60)]
        self.runs = {}

    def runs_for(self, A):
        if A not in self.runs:
            runs, s = [], None
            for i, a in enumerate(self.aoa):
                if not math.isnan(a) and a < A:
                    if s is None:
                        s = i
                else:
                    if s is not None:
                        runs.append((s, i - 1))
                        s = None
            if s is not None:
                runs.append((s, len(self.aoa) - 1))
            self.runs[A] = (runs, [r[1] for r in runs])
        return self.runs[A]

    def justified(self, t0, A, D, W):
        t = self.t
        i0 = bisect.bisect_left(t, t0)
        i1 = bisect.bisect_right(t, t0 + W) - 1
        if i0 > i1:
            return None
        k = bisect.bisect_left(self.hits, i0)
        hit = self.hits[k] if k < len(self.hits) and self.hits[k] <= i1 else None
        runs, ends = self.runs_for(A)
        comp = None
        r = bisect.bisect_left(ends, i0)          # first run ending at or after i0
        while r < len(runs):
            s, e = runs[r]
            if s > i1:
                break
            s = max(s, i0)
            e = min(e, i1)
            j = bisect.bisect_left(t, t[s] + D, s, e + 1)
            # evaluate.justified completes at the first sample j with t[j] - t[s] >= D
            while j <= e and t[j] - t[s] < D:
                j += 1
            if j <= e:
                comp = j
                break
            r += 1
        if hit is not None and (comp is None or hit <= comp):
            return True
        if comp is not None:
            return False
        return True


def trace(path):
    if path not in TRACES:
        TRACES[path] = Trace(path)
    return TRACES[path]


def truth_onset(tr, t_start, t_end, A, D, W, rule):
    i0 = bisect.bisect_left(tr.t, t_start)
    k = bisect.bisect_left(tr.big, i0)
    while k < len(tr.big):
        i = tr.big[k]
        if tr.t[i] >= t_end:
            return None
        j = tr.justified(tr.t[i], A, D, W) if rule == "settle" else ref.justified(tr.raw, tr.t[i], A, D, W, rule)
        if j:
            return tr.t[i]
        k += 1
    return None


def score(real, oracle, td, A, D, W, rule):
    cnt = {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "skipped": 0}
    lat, detail = [], {}
    for k, r in real.items():
        path = os.path.join(td, "_".join(k[:3]) + "_0_b" + k[4] + ".tsv")
        if (k[0], k[1], k[2], "0", k[4]) not in oracle or not os.path.exists(path):
            cnt["skipped"] += 1
            continue
        tr = trace(path)
        t_fire = ref.num(r["tumble_t"])
        if math.isnan(t_fire) and "TUMBLE" in r["abort"]:
            t_fire = ref.num(r["abort_t"])
        ends = [ref.num(r[c]) for c in ("deploy_t", "land_t", "abort_t", "tumble_t")]
        ends = [e for e in ends if not math.isnan(e)]
        H = min(ends) if ends else math.inf
        rod = ref.num(r["launchrod_t"])
        t_start = rod if not math.isnan(rod) else 0.0
        if not math.isnan(t_fire):
            j = tr.justified(t_fire, A, D, W) if rule == "settle" else ref.justified(tr.raw, t_fire, A, D, W, rule)
            if j is None:
                cnt["skipped"] += 1
                continue
            c = "TP" if j else "FP"
            if j:
                ts = truth_onset(tr, t_start, t_fire + 1e-9, A, D, W, rule)
                if ts is not None:
                    lat.append(t_fire - ts)
        else:
            c = "FN" if truth_onset(tr, t_start, H, A, D, W, rule) is not None else "TN"
        cnt[c] += 1
        detail[k] = c
    return cnt, lat, detail


ARGS = {}


def grid_job(params):
    A, D, W = params
    cb, _, _ = score(ARGS["B"], ARGS["O"], ARGS["td"], A, D, W, "settle")
    cf, _, _ = score(ARGS["F"], ARGS["O"], ARGS["td"], A, D, W, "settle")
    return params, cb, cf


def check(td, n):
    rnd = random.Random(1)
    files = sorted(glob.glob(os.path.join(td, "*.tsv")))
    bad = 0
    for _ in range(n):
        tr = trace(rnd.choice(files))
        if not tr.t:
            continue
        t0 = rnd.uniform(tr.t[0], tr.t[-1])
        A, D, W = rnd.choice((15, 20, 30)), rnd.choice((0.3, 0.5, 1.0)), rnd.choice((2, 3, 5))
        a = tr.justified(t0, A, D, W)
        b = ref.justified(tr.raw, t0, A, D, W, "settle")
        if a != b:
            bad += 1
            print("MISMATCH", t0, A, D, W, a, b)
    print(f"equivalence check: {n} random cases, {bad} mismatches")
    return bad == 0


def main():
    rb, rf, ro, td = sys.argv[1:5]
    if "--check" in sys.argv:
        ok = check(td, int(sys.argv[sys.argv.index("--check") + 1]))
        sys.exit(0 if ok else 1)
    B, F, O = ref.load_rows(rb), ref.load_rows(rf), ref.load_rows(ro)
    assert B.keys() == F.keys()
    ARGS.update(B=B, F=F, O=O, td=td)
    print("PRIMARY (settle rule, A=20 deg, D=0.5 s, W=3 s)", flush=True)
    res = {}
    for name, real in (("base", B), ("fix", F)):
        cnt, lat, det = score(real, O, td, 20, 0.5, 3, "settle")
        res[name] = det
        prec = cnt["TP"] / max(cnt["TP"] + cnt["FP"], 1)
        rec_ = cnt["TP"] / max(cnt["TP"] + cnt["FN"], 1)
        lat.sort()
        med = lat[len(lat) // 2] if lat else math.nan
        print(f"  {name}: {cnt}  precision {prec:.3f}  recall {rec_:.3f}  median latency {med:.3f} s (n={len(lat)})", flush=True)
    diff = [k for k in res["base"] if res["base"][k] != res["fix"].get(k)]
    trans = {}
    for k in diff:
        trans[(res["base"][k], res["fix"][k])] = trans.get((res["base"][k], res["fix"][k]), 0) + 1
    print(f"  branches whose verdict differs: {len(diff)}; transitions base->fix: {trans}", flush=True)
    with open(os.path.join(os.path.dirname(ro), "verdicts_primary.tsv"), "w") as f:
        f.write("rocket\tsim\twind\trec\tbranch\tbase\tfix\n")
        for k in sorted(res["base"]):
            f.write("\t".join(k) + f"\t{res['base'][k]}\t{res['fix'].get(k, '-')}\n")
    print("\nSENSITIVITY (settle rule): A D W -> base [TP FP FN] | fix [TP FP FN] | errors", flush=True)
    grid = list(itertools.product((15, 20, 30), (0.3, 0.5, 1.0), (2, 3, 5)))
    with mp.get_context("fork").Pool(min(12, len(grid))) as pool:
        for (A, D, W), cb, cf in sorted(pool.map(grid_job, grid)):
            print(f"  {A:>2} {D:.1f} {W}:  base [{cb['TP']:3d} {cb['FP']:3d} {cb['FN']:3d}] | fix [{cf['TP']:3d} {cf['FP']:3d} {cf['FN']:3d}]"
                  f" | base {cb['FP'] + cb['FN']:3d}  fix {cf['FP'] + cf['FN']:3d}", flush=True)
    print("\nSECOND CRITERION (rotation: >= 2 crossings of 90 deg within W, or the thrust rule)", flush=True)
    for W in (2, 3, 5):
        cb, _, _ = score(B, O, td, 20, 0.5, W, "rotation")
        cf, _, _ = score(F, O, td, 20, 0.5, W, "rotation")
        print(f"  W={W}: base {cb} | fix {cf}", flush=True)


if __name__ == "__main__":
    main()
