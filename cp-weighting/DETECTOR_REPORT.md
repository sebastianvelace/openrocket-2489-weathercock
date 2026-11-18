# OpenRocket's tumble detector and the CP fix: decoupling them

Status: investigation complete, nothing posted upstream. Date: 2026-11-17.
Code: OpenRocket `unstable` at 33bdb6d3. The detector is `TumbleDetector` (#3190).
Companion to [REPORT.md](REPORT.md), which documents the CP weighting bug.

## 1. The problem in one page

**What we found.** `TumbleDetector` low-pass filters the angle of attack with a time constant of two
pitch periods, taken from `TYPE_NATURAL_FREQUENCY`. Its javadoc says no aerodynamic coefficient enters
the decision, because the CP is unreliable above the stall angle. But the natural frequency is computed
from that same CP and its weights, evaluated at the current angle of attack, which is above stall exactly
when the detector matters. So the detector depends, indirectly, on the quantity its design excludes. This
is why correcting the CP weights (REPORT.md) changes the detector, and on balance makes it slightly worse.

**What fixes the coupling.** Take the pitch natural frequency at a near-zero angle of attack (candidate
C2). That is the airframe's own small-angle pitch dynamics, where the aerodynamic model is valid, at the
current Mach number, CG, inertia and dynamic pressure. Measured against an independent reference
trajectory on 1210 flights:

| detector | current CP | corrected CP |
|---|---:|---:|
| current (C0) | 31 errors | 36 errors |
| small-angle frequency (C2) | 31 errors | **31 errors** |

(Primary criterion; misses counted only if the detector had at least 0.5 s to catch them.)

- With C2 the detector gives identical results with either CP, because at small angles the two CP
  versions coincide.
- C2 keeps the current detector's accuracy: the same 31 errors on the primary criterion, and 985 against
  981 errors summed over 27 threshold variants.
- Implemented in Java behind a switch, C2 reproduces the offline evaluation on 1206 of 1210 flights. With
  the CP fix it passes the full core suite (1762/1762).

**What it does not do.** None of the candidates, all defined before measuring and with no tuned
constants, improves the detector's accuracy. In particular, the tumble under thrust in "3D printable nose
cone and fins" at 10 m/s, missed today, is still missed with C2. C2 makes the CP fix safe for the detector.
It does not make the detector better.

## 2. Intent of the detector (from #3190)

The PR states: "What distinguishes a tumbling rocket from a gust is not the size of the angle of attack at
one instant but whether the rocket recovers. A statically stable rocket returns to alignment within about a
pitch period; a tumbling rocket does not." The evaluation therefore uses a "recovers or not" reference
criterion (settle rule) as primary, with a rotation-based criterion as a secondary check.

## 3. Method

- **Reference trajectory (oracle).** Every flight is re-run with the tumble detector disabled and
  recovery disabled (`oracle-switch.patch`), for both CP versions: 1210 flights, 1540 branches, 0 TUMBLE
  events, 0 aborts. A recorder listener logs the small-angle pitch natural frequency ω₀ and the dynamic
  pressure at every step. Its presence leaves the oracle bit-identical to a run without it.
- **Offline replica of the detector** (`td_eval.py`). This is valid because the detector affects a flight
  only through the TUMBLE event it emits, and until then the real and oracle flights are the same.
  The replica mirrors the engine's ordering: the detector reads the row stored at the start of a step,
  stamped with the time after the step, and the launch-guide flag turns on one iteration after LAUNCHROD.
  - Validation: it reproduces the real detector's TUMBLE times exactly on **1210/1210 main branches**,
    for both CP versions (to the 6-decimal precision of the logs).
  - Separated stages (boosters, payloads) reproduce on 276–277 of 330 branches, so they are excluded from
    the comparison.
- **Candidates**, defined before measuring. None tunes a constant; all keep 60°, 2 periods and 0.05–2 s.
  - C0: current. τ from the natural frequency at the current angle of attack.
  - C1: while AoA > 90° (reverse flow), keep the last τ computed in forward flow.
  - C2: τ from the small-angle pitch natural frequency ω₀. If the airframe is unstable at small angles,
    τ = 0.05 s.
  - C3: constant τ = 0.5 s, a baseline with no airframe scaling.
- **Scoring.** Same definitions as REPORT.md section 3: justified firing, truth onset, TP/FP/FN/TN, misses
  counted only with a minimum catchable margin, a 27-variant sensitivity grid and per-rocket breakdowns.
- **Java verification.** C2 was implemented in `BasicEventSimulationEngine` behind an environment switch
  (`detector-c2-experiment.patch`). It ran twice over the full sweep with the corrected CP, and the two
  runs were bit-identical. The switch's effect was confirmed (132 branches differ from the run without
  C2), its TUMBLE times were compared with the replica's predictions, and the full core suite was run.

## 4. Results

### 4.1 Where the current detector errs (current CP, primary criterion, catchable margin ≥ 0.5 s)

All errors are in coast or descent; none occurs under thrust in this criterion. On main branches there are
9 false positives and 22 misses. They concentrate in a few rockets: Pods – airframes (9), Chute release
(5), A simple model rocket (4), and 3D printable, Deployable payload and Airstart timing (3 each). The
false positives are mid-turnover firings of rockets that then settle. Many misses are slow apogee
turnovers at very low dynamic pressure, which a fixed 3 s reference window may call tumbling. These counts
depend on the reference definition (REPORT.md section 6).

### 4.2 Candidates (1210 main-branch flights)

Primary criterion, catchable margin ≥ 0.5 s:

| CP | detector | TP | FP | FN | errors |
|---|---|---:|---:|---:|---:|
| current | C0 | 215 | 9 | 22 | 31 |
| current | C1 | 215 | 9 | 22 | 31 |
| current | C2 | 215 | 9 | 22 | 31 |
| current | C3 | 233 | 31 | 3 | 34 |
| corrected | C0 | 219 | 12 | 24 | 36 |
| corrected | C1 | 219 | 12 | 24 | 36 |
| corrected | **C2** | 215 | 9 | 22 | **31** |
| corrected | C3 | 233 | 31 | 3 | 34 |

Errors summed over the 27-variant grid (worse / better than current C0 with current CP, per variant):

| margin | C0 current | C0 corrected | C2 (either CP) | C3 |
|---|---:|---:|---:|---:|
| ≥ 0.5 s | 981 | 987 (11 / 11) | 985 (4 / 0) | 984 (14 / 13) |
| ≥ 1.0 s | 686 | 746 (18 / 2) | 690 (4 / 0) | 950 (20 / 7) |
| ≥ 2.0 s | 601 | 688 (25 / 1) | 605 (4 / 0) | 923 (21 / 6) |

- **C2 is invariant to the CP choice** (identical rows), and stays within 4 errors in total of the current
  detector across all 27 variants.
- **The corrected CP with the current detector is consistently worse** at stricter margins, as found in
  REPORT.md.
- **C1 does not help.** Holding τ through reverse flow leaves the CP coupling in forward flow intact.
- **C3** trades misses for false positives and gets much worse at stricter margins. Scaling the wait to
  the airframe's dynamics is worth keeping.

### 4.3 Java implementation

| check | result |
|---|---|
| C2 sweep, run twice | bit-identical |
| C2 switch effective | 132 branches differ from the corrected-CP run without C2 |
| Java C2 vs replica C2, main branches | 1206 / 1210 exact; 4 differ by 3–13 ms, all Deployable payload without recovery, near its stage separation |
| full core suite, corrected CP + C2 | 1762 / 1762 pass |

## 5. Interpretation

The natural frequency at the current angle of attack mixes two different things. One is the airframe's
pitch dynamics, which set how long a stable rocket takes to recover; the other is the post-stall aerodynamic
model, which the detector's own design treats as unreliable. C2 keeps the first and drops the second. It
does not change the detector's accuracy, because the current detector's decisions turn out to depend little
on the post-stall part (C0 and C2 give the same primary score with the current CP). But it removes the
detector's sensitivity to how the CP is weighted above stall, so the CP bug can be fixed on its own merits.

## 6. Limitations

- Evaluated on main branches only. The replica does not reproduce separated stages exactly (276–277 / 330).
- C2 adds an aerodynamic evaluation per step when the detector runs. Its run-time cost was not measured.
- The reference trajectory is the simulation's own model without the detector. "Tumbling" is judged by
  fixed criteria, and absolute error counts depend on them (REPORT.md section 6).
- The 17 rockets and steady-wind conditions are synthetic. No candidate was tuned, so there is nothing to
  overfit, but the sample is still the sample.

## 7. Suggested direction (for discussion with the maintainers)

Fix the CP weighting (REPORT.md) and, in the same change or first, have the detector take its time constant
from the small-angle pitch natural frequency. Together they leave the detector's measured behavior
unchanged and make the reported CP, margin and CNα consistent with the applied forces. Improving the
detector's accuracy, for example on tumbles under thrust, is a separate question. It needs an agreed
definition of what TUMBLE should capture.

## Files

| path | content |
|---|---|
| `td_eval.py` | offline replica, candidates and scoring |
| `detector-c2-experiment.patch` | engine changes used here (oracle switch and the C2 switch; experiment only) |
| `results/detector/candidates.txt` | full candidate output (primary, grid, per rocket) |
| `results/detector/replica_validation.txt` | replica vs real detector, and replica vs Java C2 |
| `results/detector/real_fix_c2.tsv` | Java C2 sweep with the corrected CP |
| `results/detector/oracle_*_with_names.tsv`, `replica_c2_fix.json` | oracle summaries and replica predictions |

The oracle traces with ω₀ (≈ 440 MB per CP version) are not stored. They are regenerated deterministically
with `TumbleSweepProbeTest` (`OR_ORACLE=1 SW_REC_ONLY=0 SW_DUMP_ALL=1`) on a build with
`oracle-switch.patch`.
