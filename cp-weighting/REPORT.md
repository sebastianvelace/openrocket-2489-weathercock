# OpenRocket: the reported CP is inconsistent with the applied forces above the fin stall angle

Status: investigation complete, nothing posted upstream. Date: 2026-11-17.
Code: OpenRocket `unstable` at 33bdb6d3.

## 1. The problem in one page

**What is wrong.** Above 20° angle of attack, OpenRocket's reported center of pressure does not match the
forces it applies. This also affects the stability margin and CNα derived from it, and the natural
frequency and damping ratio derived from those. The cause is a weighting mismatch in the fin calculations:

```java
// FinSetCalc.java:231-232 (TubeFinSetCalc.java:180-181 is identical)
forces.setCN(cna * MathUtil.min(conditions.getAOA(), STALL_ANGLE));   // normal force capped at 20°
forces.setCP(new Coordinate(x, 0, 0, cna));                            // CP weight not capped
```

The rocket's CP is the weighted average of the component CPs, using these weights
(`AerodynamicForces.merge`). Body components weight their CP by CN/α. Above the stall angle, fins keep
their uncapped pre-stall CNα as the weight, although their normal force, and therefore their moment, stays
flat. The reported CP is therefore too far aft, and the rocket is reported as more stable than its own
forces make it.

**Evidence that it is a bug.**

- A minimal JUnit test (`CPForceConsistencyTest`, Estes Alpha III from `TestRockets`) asserts reported
  CP = Cm·L_ref/CN. It passes at 5°, 10° and 15° and fails at 25°, 40°, 60° and 80°.
- Over the 16 bundled examples and the TRF #2489 rocket, at Mach 0.1, 0.8 and 1.5, the reported CP and the
  force-consistent CP agree exactly below 20° (difference 0). Above that they diverge, by up to 3.4
  calibers, and 13–14 of the 17 rockets have a band of angles where the reported margin is positive while
  the forces are destabilizing.
- It occurs in ordinary flights. With recovery as designed and steady winds of 0–10 m/s, 35 % of flight
  branches spend time at 20–90° before any TUMBLE or deployment (median 0.29 s, maximum 2.29 s).

**The CP fix is exact.** Weighting the fin CP by the effective CN/α above stall, as the body already does,
makes the reported CP equal the force-consistent CP at every angle and Mach tested, leaves CN and Cm
unchanged, passes the core suite (1762/1762), and makes the JUnit test pass at every angle.

**But on its own it makes the tumble detector slightly worse.** The natural frequency is computed from the
same weights (`computeCorrectiveMomentCoefficient`: `cna = getCP().getWeight()`), and the tumble detector
sets its filter time from that frequency. Against an independent reference trajectory (section 5.5),
counting only misses a detector could have caught, the detector makes 44 errors with the current code and
49 with the fix (primary criterion). The fix is worse in 19 to 25 of 27 parameter variants. The detector's
behavior at high and reverse-flow angles relies, in effect, on the inconsistent frequency. Correcting the
CP needs a matching change to the detector, and both are decisions for the maintainers.

## 2. Where the weights come from (history)

- Up to OpenRocket 23.09, `AerodynamicForces` stored CNα separately (`setCNa`). The fins set it to `cna`
  and used `cna` as the CP weight: the small-angle aerodynamic-center definition.
- #2753 (2025-03, fixing a NaN CP when nose and tail cone CNα cancel) removed the separate field. Since
  then "CNα" is the CP weight. #3010 (2026-01) exposes it as the flight data type "normal force
  coefficient derivative". `AbstractSimulationStepper` reads the weight as CNα, with
  `// TODO: replace with getCNa() when available`.
- The body has always weighted its CP by `CNα·sinc(α) + K·sin²α/α`. That is the secant CN/α, not the
  derivative: the derivative of K·sin²α would be 2K·sinα·cosα.

So above the fin stall angle the reported CP is neither the resultant-force CP, which would need the fins'
secant CN/α, nor the model's aerodynamic center, which would need slopes: zero for a stalled fin, and a
different body term. It mixes the two definitions.

## 3. Method

- **Unit test.** `CPForceConsistencyTest`, parameterized over AoA, on `TestRockets.makeEstesAlphaIII()`.
- **Static** (`CpConsistencyProbeTest`). For α from 1° to 90° at Mach 0.1, 0.8 and 1.5, for each of 17
  rockets: reported CP and weight, CN, Cm, and the force-consistent CP Cm·L_ref/CN.
- **Dynamic** (`TumbleSweepProbeTest`). Every simulation in the 17 files (55 simulations), steady
  listener wind 0–10 m/s in 1 m/s steps, recovery as designed and disabled, all randomness pinned. That is
  1210 flights and 1540 flight branches. Base and prototype were each run three times, all bit-identical.
- **Controls.**
  - (a) Builds carrying the control or oracle patches, with the switch off, reproduce the base sweep bit
    for bit.
  - (b) Rounding control (`control-weight-eps.patch`): the fin CP weight above stall is multiplied by
    (1 + 10⁻¹³). This leaves Cm and CN unchanged and changes ω_n by one part in 10¹³.
  - (c) A time-step perturbation of 10⁻¹² produced no difference at all. It was ineffective and is not used
    as evidence.
- **Oracle** (`oracle-switch.patch`). Every flight was re-run with the tumble detector disabled and
  recovery disabled, so that the 6-DOF trajectory is never cut short. This gives a reference trajectory
  that is independent of both versions' detector decisions. In the oracle runs: 0 TUMBLE events, 0 aborts,
  and all 1540 branches present.
- **Evaluation** (`evaluate.py`; definitions fixed before the oracle data were inspected).
  - *justified(t)*: in the oracle over [t, t+W], the nose goes below horizontal while thrusting, or the AoA
    never stays below A for D seconds.
  - *truth onset t\**: the earliest oracle time after rod clearance with AoA ≥ 60° and justified(t).
  - Each version's decision per branch is scored TP, FP, FN or TN, counting truth only before the end of
    that version's active detector period H (deployment, ground hit, TUMBLE or abort).
  - Primary parameters: A = 20°, D = 0.5 s, W = 3 s. Sensitivity grid: A ∈ {15, 20, 30}°,
    D ∈ {0.3, 0.5, 1.0} s, W ∈ {2, 3, 5} s.
  - Second, independent criterion: the AoA crosses 90° at least twice within W (rotation), or the thrust
    rule holds.
  - `evaluate_fast.py` is a faster implementation of the same definitions. It agreed with `evaluate.py` in
    20 000 random cases and 14 949 cases targeted at rule edges, with no mismatches.
- An earlier pairwise criterion (`classify.py`, section 5.4) judged each changed flight with the other
  version's trajectory. It is kept for reference. Its weakness, windows truncated by parachutes, is what the
  oracle removes.

## 4. Static results

| Mach | max \|reported − consistent\|, α ≤ 18° | max, all α | rockets with a falsely stable band |
|---:|---:|---:|---:|
| 0.1 | 0 | 3.29 cal | 13 / 17 |
| 0.8 | 0 | 3.29 cal | 13 / 17 |
| 1.5 | 0 | 3.43 cal | 14 / 17 |
| prototype, all three | 0 | 0 | 0 / 17 |

| CPForceConsistencyTest (Estes Alpha III, Mach 0.3) | 5° | 10° | 15° | 25° | 40° | 60° | 80° |
|---|---|---|---|---|---|---|---|
| current code | pass | pass | pass | **fail** | **fail** | **fail** | **fail** |
| prototype | pass | pass | pass | pass | pass | pass | pass |

Example, the TRF #2489 rocket at 26° and Mach 0.1: reported CP 1.037 m, force-consistent CP 0.993 m.
With the motor full (CG 1.065 m) the margins are −0.43 cal reported against −1.07 cal from the forces.

## 5. Dynamic results

### 5.1 Overview (1540 branches)

| comparison with base | TUMBLE outcome changed | TUMBLE timing changed | no-TUMBLE branches not bit-identical |
|---|---:|---:|---:|
| rounding control (b) | 0 | 3 (max 0.025 s) | 43 (max apogee Δ 0.10 m) |
| prototype | 19 | 116 (109 earlier, median −0.98 s, max 1.90 s) | 42 (max apogee Δ 0.11 m) |

### 5.2 The prototype's effect on TUMBLE is real, not numerical noise

The rounding control changes no outcome and shifts three timings by at most 0.025 s. The prototype changes
19 outcomes and 116 timings.

### 5.3 Trajectory differences without TUMBLE are round-off

Forty-two branches without TUMBLE differ between base and prototype: apogee up to 0.105 m, landing up to
0.19 s. The first dynamic divergence is in the last digit of the pitch rate (relative 10⁻¹⁶).
`AerodynamicForces` stores CP as x·w and recovers it as (x·w)/w (`BarrowmanStabilityCalculator:271`), so
the fin Cm depends on w in its last bit. The rounding control reproduces the effect: 43 branches, apogee up
to 0.101 m, 31 of the 42 in common. Any harmless change shows this ordinary sensitivity of high-angle
flights to round-off.

### 5.4 Pairwise classification of the 19 changed outcomes (superseded by 5.5)

Using the other version's trajectory as the reference, the robust cases split 6 improved (3D printable at
10 m/s, a tumble under thrust the base misses; four Pods flights flagged mid-turnover), 6 made worse (the
Tube fin rocket's normal apogee turnover becomes a false TUMBLE), and 7 inconclusive (a parachute opens
inside the window). Details in `results/big/classification.txt`.

### 5.5 Evaluation against the oracle

Primary criterion, all 1540 branches:

| version | TP | FP | FN | TN | precision | recall | median latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| base | 377 | 10 | 102 | 1051 | 0.974 | 0.787 | 0.061 s |
| prototype | 381 | 13 | 101 | 1045 | 0.967 | 0.790 | 0.057 s |

Taken at face value the two are almost equal. But most of the misses are an artifact of the definition.
For 56 of the base's 102 misses the oracle tumble starts less than 0.1 s before a parachute deploys or the
flight otherwise ends, and for 68 less than 0.5 s before. No detector that requires the angle to be
sustained can catch those. Counting a miss only if the detector had a minimum margin:

| misses counted if margin ≥ | prototype fewer errors | equal | prototype more errors | (of 27 variants) |
|---|---:|---:|---:|---|
| 0 s (all) | 21 | 2 | 4 | |
| 0.5 s | 10 | 6 | 11 | |
| 1.0 s | 2 | 6 | **19** | |
| 2.0 s | 1 | 1 | **25** | |

Primary criterion with margin ≥ 0.5 s: **base 44 errors (10 FP, 34 FN), prototype 49 (13 FP, 36 FN).**
The rotation criterion agrees in sign: the prototype makes 3 more errors at W = 2, 3 and 5 s.

**Conclusion.** Once misses no detector could catch are discounted, the CP fix makes the tumble detector
slightly worse, by about 5 errors in 45 (10 %), consistently across parameters. The fix is right for the
CP. It is not right, on its own, for the quantity the detector consumes.

### 5.6 Why the coupling arises

In the flights where the fix helps (3D printable under thrust), the inflated frequency had kept the
detector slow while the rocket diverged. In the flights where it hurts (Tube fin), the consistent margin
crosses zero during reverse flow (α ≈ 100–120°), ω_n becomes undefined, and the detector drops to its
0.05 s time constant in the middle of a normal turnover. A linearized pitch frequency has no physical
meaning in reverse flow, and the detector uses it there either way.

## 6. A separate observation about the detector (not about the CP)

With the primary criterion and a margin of at least 0.5 s, both versions miss about 34 oracle tumbles and
flag about 10 turnovers that settle. Some misses had 10–40 s of margin (Airstart timing, the ARC payload
branch, Chute release). The two definitions of "tumbling" disagree widely, though: the rotation criterion
gives about 150 false positives where the settle criterion gives 10. So these counts depend on what one
calls a tumble, and they are not claimed as detector defects here. They are a reason to define, with the
maintainers, what the TUMBLE event is meant to capture before tuning anything.

## 7. Questions for the maintainers

1. Should the CP weight above stall be the secant CN/α (the resultant-force CP, the body's convention) or
   the local slope (the aerodynamic center)? The reported CP, margin and CNα follow from that choice.
2. Should the tumble detector stop relying on the linearized natural frequency at high or reverse-flow
   angles? Section 5.5 shows the CP fix alone worsens the detector slightly.
3. What should TUMBLE mean operationally: sustained high AoA, or repeated rotation? Section 6 shows the
   choice changes detector scores by an order of magnitude.

## 8. Limitations

- The 17 rockets are the bundled examples plus one forum rocket. The conditions are synthetic: steady
  wind, recovery switched off for the oracle.
- The oracle is the simulation's own 6-DOF model without the detector, not a measurement. Before
  deployment it is the same flight. After deployment it is a counterfactual flight without a parachute,
  used only to judge the aerodynamic state at decision times.
- "Tumbling" has no single accepted definition. Two criteria and 27 parameter variants were used, and the
  base-versus-prototype comparison is reported only where it holds across them.
- Only fins and tube fins set an inconsistent weight. Pods and boosters inherit it through their fins.

## Files

| path | content |
|---|---|
| `CPForceConsistencyTest.java` | minimal JUnit demonstration (regression test candidate) |
| `cp-weight-prototype.patch` | the prototype (`FinSetCalc`, `TubeFinSetCalc`) |
| `control-weight-eps.patch`, `oracle-switch.patch` | rounding control and oracle switch (environment-gated, scratch only) |
| `CpConsistencyProbeTest.java`, `TumbleSweepProbeTest.java`, `TumbleEventProbeTest.java` | probes |
| `evaluate.py`, `evaluate_fast.py`, `fair_compare.py`, `classify.py` | evaluation scripts |
| `results/oracle/` | real and oracle sweep summaries, evaluation output, per-branch verdicts, fair comparison |
| `results/big/` | static sweeps, dynamic sweeps (base, prototype, controls), pairwise classification, traces |
| `results/` (top level) | the first, smaller runs |

The oracle traces (315 MB) are not stored. They are regenerated deterministically by running
`TumbleSweepProbeTest` with `OR_ORACLE=1 SW_REC_ONLY=0 SW_DUMP_ALL=1` on a build with `oracle-switch.patch`.
