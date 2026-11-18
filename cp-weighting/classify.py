#!/usr/bin/env python3
"""
Compare the base and prototype sweeps and classify every flight whose TUMBLE outcome differs.

Pre-registered criterion (fixed before the large sweep was inspected):
  For a flight whose TUMBLE/abort outcome differs between versions, take the version that fires first
  (TUMBLE or SIM_ABORT, whichever is earlier) at t_fire, and the other version, whose 6-DOF trajectory
  continues past t_fire, and look at that other version in the window [t_fire, t_fire + 3 s]:
    * GENUINE   if, while thrust > 0 in that window, the nose goes below horizontal (theta < 0), or if
                AoA never stays below 20 deg for 0.5 s within the window;
    * FALSE     if AoA stays below 20 deg for at least 0.5 s within the window.
  The first-firing version is "right" if the event is GENUINE, "wrong" if FALSE; the other version is
  the opposite.

Usage:
  classify.py keys  <base.tsv> <fix.tsv>               -> prints dump keys for changed flights
  classify.py judge <base.tsv> <fix.tsv> <dump_base_dir> <dump_fix_dir>
  classify.py stats <base.tsv> <fix.tsv>                -> summary statistics
"""
import csv
import math
import os
import sys


def load(path):
    rows = list(csv.DictReader(open(path), delimiter="\t"))
    return {(r["rocket"], r["sim"], r["wind"], r["rec"], r["branch"]): r for r in rows}


def fired(r):
    return (r["tumble_t"] != "NaN") or ("TUMBLE" in r["abort"])


def fire_time(r):
    if r["tumble_t"] != "NaN":
        return float(r["tumble_t"])
    return math.nan


def changed_flights(B, F):
    out = []
    for k in sorted(B):
        b, f = B[k], F[k]
        if fired(b) != fired(f) or b["abort"] != f["abort"]:
            out.append(k)
    return out


def load_trace(path):
    lines = open(path).read().split("\n")
    events = [l[2:].split() for l in lines if l.startswith("#")]
    rows = list(csv.reader([l for l in lines if l and not l.startswith("#")], delimiter="\t"))
    head = rows[0]
    data = [[float(x) for x in r] for r in rows[1:]]
    col = {h: i for i, h in enumerate(head)}
    return events, data, col


def judge_window(data, col, t0):
    it, ia, ith, ithr = col["Time"], col["Angle_of_attack"], col["Vertical_orientation_(zenith)"], col["Thrust"]
    win = [r for r in data if t0 <= r[it] <= t0 + 3.0]
    if not win:
        return "NO_DATA"
    for r in win:
        if r[ithr] > 0 and r[ith] < 0:
            return "GENUINE"
    run_start = None
    for r in win:
        a = math.degrees(r[ia]) if not math.isnan(r[ia]) else 999
        if a < 20:
            if run_start is None:
                run_start = r[it]
            if r[it] - run_start >= 0.5:
                return "FALSE"
        else:
            run_start = None
    return "GENUINE"


def main():
    mode = sys.argv[1]
    B, F = load(sys.argv[2]), load(sys.argv[3])
    assert B.keys() == F.keys(), "sweeps do not cover the same branches"
    ch = changed_flights(B, F)
    if mode == "keys":
        keys = sorted({"|".join(k[:4]) for k in ch})
        print(";".join(keys))
        return
    if mode == "stats":
        n = len(B)
        same = [k for k in B if not (fired(B[k]) != fired(F[k]) or B[k]["abort"] != F[k]["abort"])]
        both = [k for k in same if fired(B[k])]
        shifted = [k for k in both if abs(fire_time(B[k]) - fire_time(F[k])) > 1e-9]
        ident = [k for k in same if not fired(B[k]) and all(B[k][c] == F[k][c] for c in ("apogee_m", "land_t", "burnout_t"))]
        nofire = [k for k in same if not fired(B[k])]
        print(f"branches: {n}")
        print(f"TUMBLE/abort outcome changed: {len(ch)}")
        print(f"both fire: {len(both)}, of which timing shifted: {len(shifted)}")
        if shifted:
            d = sorted(fire_time(F[k]) - fire_time(B[k]) for k in shifted)
            print(f"  shift fix-base: min {d[0]:+.3f} s, median {d[len(d) // 2]:+.3f} s, max {d[-1]:+.3f} s, "
                  f"earlier {sum(1 for x in d if x < 0)}, later {sum(1 for x in d if x > 0)}")
        print(f"neither fires: {len(nofire)}, of which apogee/landing/burnout bit-identical: {len(ident)}")
        tb = [float(B[k]["t_aoa_20_90"]) for k in B if B[k]["rec"] == "1" and not math.isnan(float(B[k]["t_aoa_20_90"]))]
        if tb:
            nz = [x for x in tb if x > 0]
            print(f"recovery as designed: branches with any time at 20-90 deg AoA before tumble/deploy: "
                  f"{len(nz)}/{len(tb)}; max {max(tb):.2f} s; median of nonzero {sorted(nz)[len(nz) // 2] if nz else 0:.3f} s")
        return
    if mode == "judge":
        db, df = sys.argv[4], sys.argv[5]
        score = {"fix_right": 0, "base_right": 0, "undetermined": 0}

        def fire_from_events(ev):
            ts = [float(e[1]) for e in ev if e[0] == "TUMBLE"]
            ts += [float(e[1]) for e in ev if e[0] == "SIM_ABORT"]
            return min(ts) if ts else math.inf

        for k in ch:
            if k[4] != "0":
                print(f"{'|'.join(k)}: branch {k[4]} not dumped (only branch 0 traces) -> undetermined")
                score["undetermined"] += 1
                continue
            name = "_".join(k[:4]) + ".tsv"
            ev_b, data_b, col_b = load_trace(os.path.join(db, name))
            ev_f, data_f, col_f = load_trace(os.path.join(df, name))
            tb, tf = fire_from_events(ev_b), fire_from_events(ev_f)
            if tb == tf:
                print(f"{'|'.join(k)}: same fire time, different outcome -> undetermined")
                score["undetermined"] += 1
                continue
            if tb < tf:   # base fires first: judge with the fix's continuation
                verdict = judge_window(data_f, col_f, tb)
                right = "base_right" if verdict == "GENUINE" else "fix_right"
                who = f"base fires first at {tb:.3f} (fix at {tf:.3f})"
            else:
                verdict = judge_window(data_b, col_b, tf)
                right = "fix_right" if verdict == "GENUINE" else "base_right"
                who = f"fix fires first at {tf:.3f} (base at {tb:.3f})"
            score[right] += 1
            print(f"{'|'.join(k)}: {who}; event {verdict} -> {right}")
        print(score)

if __name__ == "__main__":
    main()
