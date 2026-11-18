#!/usr/bin/env python3
"""
Base vs prototype detector errors against the oracle, counting a miss (FN) only when the tumble onset t*
precedes the end of the detector's active period H by at least a minimum margin. A tumble that starts a
few milliseconds before a parachute deploys cannot be caught by any detector that requires the angle to
be sustained, so counting it as a miss is an artifact of the definition.

Usage: fair_compare.py <real_base.tsv> <real_fix.tsv> <oracle.tsv> <trace_dir>
"""
import itertools
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evaluate as ref  # noqa: E402
import evaluate_fast as ef  # noqa: E402


def errors(real, oracle, td, A, D, W, min_margin, margins=None):
    _, _, det = ef.score(real, oracle, td, A, D, W, "settle")
    fp = sum(1 for c in det.values() if c == "FP")
    fn = 0
    for k, c in det.items():
        if c != "FN":
            continue
        r = real[k]
        tr = ef.trace(os.path.join(td, "_".join(k[:3]) + "_0_b" + k[4] + ".tsv"))
        ends = [ref.num(r[x]) for x in ("deploy_t", "land_t", "abort_t", "tumble_t")]
        H = min(e for e in ends if not math.isnan(e))
        rod = ref.num(r["launchrod_t"])
        ts = ef.truth_onset(tr, rod if not math.isnan(rod) else 0.0, H, A, D, W, "settle")
        if margins is not None:
            margins.append(H - ts)
        if H - ts >= min_margin:
            fn += 1
    return fp, fn


def main():
    rb, rf, ro, td = sys.argv[1:5]
    B, F, O = ref.load_rows(rb), ref.load_rows(rf), ref.load_rows(ro)
    m = []
    errors(B, O, td, 20, 0.5, 3, 0.0, m)
    m.sort()
    print(f"base misses (primary): margin H - t* min {m[0]:.3f} median {statistics.median(m):.3f} max {m[-1]:.3f} s")
    for thr in (0.1, 0.25, 0.5, 1.0, 2.0):
        print(f"  margin < {thr} s: {sum(x < thr for x in m)} of {len(m)}")
    for mm in (0.0, 0.5, 1.0, 2.0):
        d = []
        for A, D, W in itertools.product((15, 20, 30), (0.3, 0.5, 1.0), (2, 3, 5)):
            d.append(sum(errors(F, O, td, A, D, W, mm)) - sum(errors(B, O, td, A, D, W, mm)))
        print(f"misses counted with margin >= {mm} s: prototype fewer errors in {sum(x < 0 for x in d)}, "
              f"equal {sum(x == 0 for x in d)}, more {sum(x > 0 for x in d)} of 27 (diff {min(d)}..{max(d)})")
    b = errors(B, O, td, 20, 0.5, 3, 0.5)
    f = errors(F, O, td, 20, 0.5, 3, 0.5)
    print(f"primary, margin >= 0.5 s: base FP {b[0]} FN {b[1]} (total {sum(b)}) | prototype FP {f[0]} FN {f[1]} (total {sum(f)})")


if __name__ == "__main__":
    main()
