#!/usr/bin/env python3
"""
Score the tumble detector of each version against an independent reference trajectory ("oracle").

Written and fixed before the oracle data were inspected.

Oracle: the same flight simulated with the tumble detector disabled and recovery disabled, so the 6-DOF
trajectory is never cut short. Before the real run's deployment it is the same flight up to round-off.

Definitions (primary parameters A=20 deg, D=0.5 s, W=3 s):
  justified(t): in the oracle over [t, t+W], either thrust > 0 while the nose is below horizontal
                (theta < 0), or the AoA never stays below A for D seconds.
  truth onset t*: the earliest oracle time after rod clearance with AoA >= 60 deg and justified(t).
  horizon H:   the detector's active period ends at the real run's first deployment, ground hit, TUMBLE or
               abort; truth is only counted before the version's own H (excluding its own firing).
For each version and each flight branch:
  fired before H and justified(t_fire)       -> TP
  fired and not justified(t_fire)            -> FP
  not fired and truth onset t* < H           -> FN
  not fired and no t* < H                    -> TN
Second, independent criterion ("rotation"): justified(t) if the thrust rule holds or the AoA crosses 90 deg
at least twice within [t, t+W] (repeated rotation rather than a single turnover).

Usage: evaluate.py <real_base.tsv> <real_fix.tsv> <oracle.tsv> <oracle_trace_dir>
"""
import bisect
import csv
import functools
import glob
import itertools
import math
import os
import sys


def load_rows(path):
    return {(r["rocket"], r["sim"], r["wind"], r["rec"], r["branch"]): r for r in csv.DictReader(open(path), delimiter="\t")}


def num(x):
    try:
        return float(x)
    except ValueError:
        return math.nan


def load_trace(path):
    lines = open(path).read().split("\n")
    rows = list(csv.reader([l for l in lines if l and not l.startswith("#")], delimiter="\t"))
    head = rows[0]
    col = {h: i for i, h in enumerate(head)}
    data = [[float(x) for x in r] for r in rows[1:]]
    t = [r[col["Time"]] for r in data]
    aoa = [math.degrees(r[col["Angle_of_attack"]]) if not math.isnan(r[col["Angle_of_attack"]]) else math.nan for r in data]
    theta = [r[col["Vertical_orientation_(zenith)"]] for r in data]
    thrust = [r[col["Thrust"]] for r in data]
    return t, aoa, theta, thrust


def justified(tr, t0, A, D, W, rule):
    t, aoa, theta, thrust = tr
    run = None
    crossings = 0
    prev = None
    any_data = False
    for i in range(bisect.bisect_left(t, t0), len(t)):
        if t[i] > t0 + W:
            break
        any_data = True
        if thrust[i] > 0 and theta[i] < 0:
            return True
        a = aoa[i]
        if rule == "settle":
            if not math.isnan(a) and a < A:
                if run is None:
                    run = t[i]
                if t[i] - run >= D:
                    return False
            else:
                run = None
        else:
            if not math.isnan(a) and prev is not None and (prev - 90) * (a - 90) < 0:
                crossings += 1
            if not math.isnan(a):
                prev = a
    if not any_data:
        return None
    return True if rule == "settle" else crossings >= 2


_onset_cache = {}


def truth_onset(tr, t_start, t_end, A, D, W, rule):
    key = (id(tr), t_start, t_end, A, D, W, rule)
    if key in _onset_cache:
        return _onset_cache[key]
    res = _truth_onset(tr, t_start, t_end, A, D, W, rule)
    _onset_cache[key] = res
    return res


def _truth_onset(tr, t_start, t_end, A, D, W, rule):
    t, aoa, theta, thrust = tr
    for i in range(bisect.bisect_left(t, t_start), len(t)):
        if t[i] >= t_end:
            break
        hit = (thrust[i] > 0 and theta[i] < 0) or (not math.isnan(aoa[i]) and aoa[i] >= 60)
        if hit and justified(tr, t[i], A, D, W, rule):
            return t[i]
    return None


def score(real, oracle, traces, A, D, W, rule):
    cnt = {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "skipped": 0}
    lat = []
    detail = {}
    for k, r in real.items():
        ok = (k[0], k[1], k[2], "0", k[4])
        path = os.path.join(traces, "_".join(k[:3]) + "_0_b" + k[4] + ".tsv")
        if ok not in oracle or not os.path.exists(path):
            cnt["skipped"] += 1
            continue
        tr = traces_cache.setdefault(path, load_trace(path))
        t_fire = num(r["tumble_t"])
        if math.isnan(t_fire) and "TUMBLE" in r["abort"]:
            t_fire = num(r["abort_t"])
        ends = [num(r[c]) for c in ("deploy_t", "land_t", "abort_t", "tumble_t")]
        ends = [e for e in ends if not math.isnan(e)]
        H = min(ends) if ends else math.inf
        rod = num(r["launchrod_t"])
        t_start = rod if not math.isnan(rod) else 0.0
        if not math.isnan(t_fire):
            j = justified(tr, t_fire, A, D, W, rule)
            if j is None:
                cnt["skipped"] += 1
                continue
            c = "TP" if j else "FP"
            if j:
                ts = truth_onset(tr, t_start, t_fire + 1e-9, A, D, W, rule)
                if ts is not None:
                    lat.append(t_fire - ts)
        else:
            ts = truth_onset(tr, t_start, H, A, D, W, rule)
            c = "FN" if ts is not None else "TN"
        cnt[c] += 1
        detail[k] = c
    return cnt, lat, detail


traces_cache = {}


def main():
    rb, rf, ro, td = sys.argv[1:5]
    B, F, O = load_rows(rb), load_rows(rf), load_rows(ro)
    assert B.keys() == F.keys()
    print("PRIMARY (settle rule, A=20 deg, D=0.5 s, W=3 s)")
    res = {}
    for name, real in (("base", B), ("fix", F)):
        cnt, lat, det = score(real, O, td, 20, 0.5, 3, "settle")
        res[name] = det
        prec = cnt["TP"] / max(cnt["TP"] + cnt["FP"], 1)
        rec_ = cnt["TP"] / max(cnt["TP"] + cnt["FN"], 1)
        lat.sort()
        med = lat[len(lat) // 2] if lat else math.nan
        print(f"  {name}: {cnt}  precision {prec:.3f}  recall {rec_:.3f}  median latency {med:.3f} s")
    diff = [k for k in res["base"] if k in res["fix"] and res["base"][k] != res["fix"][k]]
    trans = {}
    for k in diff:
        trans[(res["base"][k], res["fix"][k])] = trans.get((res["base"][k], res["fix"][k]), 0) + 1
    print(f"  branches whose verdict differs: {len(diff)}; transitions base->fix: {trans}")
    print()
    print("SENSITIVITY (settle rule): A, D, W -> base [TP FP FN] | fix [TP FP FN]")
    for A, D, W in itertools.product((15, 20, 30), (0.3, 0.5, 1.0), (2, 3, 5)):
        cb, _, _ = score(B, O, td, A, D, W, "settle")
        cf, _, _ = score(F, O, td, A, D, W, "settle")
        print(f"  {A:>2} {D:.1f} {W}:  base [{cb['TP']:3d} {cb['FP']:3d} {cb['FN']:3d}] | fix [{cf['TP']:3d} {cf['FP']:3d} {cf['FN']:3d}]"
              f"   errors base {cb['FP'] + cb['FN']:3d}  fix {cf['FP'] + cf['FN']:3d}")
    print()
    print("SECOND CRITERION (rotation: >= 2 crossings of 90 deg within W, or the thrust rule)")
    for W in (2, 3, 5):
        cb, _, _ = score(B, O, td, 20, 0.5, W, "rotation")
        cf, _, _ = score(F, O, td, 20, 0.5, W, "rotation")
        print(f"  W={W}: base {cb} | fix {cf}")


if __name__ == "__main__":
    main()
