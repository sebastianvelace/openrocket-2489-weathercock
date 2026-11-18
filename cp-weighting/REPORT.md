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

**How big.** Measured over the 16 bundled examples and the TRF #2489 rocket, at Mach 0.1, 0.8 and 1.5:

- Below 20° the reported CP and the force-consistent CP (Cm·L_ref/CN) agree exactly (difference 0).
  This is the null control.
- At high angles the reported CP is up to 3.3–3.4 calibers aft of the force-consistent CP.
- 13 to 14 of the 17 rockets have a band of angles where the reported margin is positive while the
  applied forces are destabilizing.
- It occurs in ordinary flights. With recovery as designed and steady winds of 0–10 m/s, 270 of 770 flight
  branches (35 %) spend time at 20–90° before any TUMBLE or deployment (median 0.29 s, maximum 2.29 s).

**Why it matters beyond the plots.** The natural frequency is computed from the same weights
(`AbstractSimulationStepper.computeCorrectiveMomentCoefficient`: `cna = getCP().getWeight()`,
`0.5ρV²A·cna·(cp − cg)`). The tumble detector uses that frequency to set its filter time constant: two
pitch periods, or 0.05 s when the rocket is statically unstable. A falsely stable rocket gets a filter time
of up to 2 s, which changes when, or whether, TUMBLE fires. TUMBLE switches the simulation to the
tumbling descent model.

**What the trajectory does not see.** The equations of motion use the summed Cm, which respects the stall
cap. Changing the CP weights changes trajectories only through floating-point rounding (section 5.3) or
through a different TUMBLE decision.

**The obvious fix is exact but not sufficient on its own.** Weighting the fin CP by the effective CN/α
above stall, as the body already does, makes the reported CP equal the force-consistent CP at every angle
and Mach tested, and passes the core suite (1762/1762). In 1540 flight branches it changes 19 TUMBLE
outcomes and the timing of 116 others. Judged by a criterion fixed before the data were inspected, the
robust cases split 6 improved, 6 made worse (7 inconclusive). The tumble detector currently depends on the
inconsistent frequency. Correcting the CP and revising the detector's high-angle behavior belong together.
That choice is the maintainers' to make.

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

- **Static** (`CpConsistencyProbeTest`). For α from 1° to 90° at Mach 0.1, 0.8 and 1.5, for each rocket:
  reported CP and weight, CN, Cm, and the force-consistent CP Cm·L_ref/CN. CG comes from `MassCalculator`
  at launch and burnout.
- **Dynamic** (`TumbleSweepProbeTest`). Every simulation in each of the 17 files (55 simulations), steady
  listener wind 0–10 m/s in 1 m/s steps, recovery as designed and disabled, all randomness pinned (seed 0,
  fixed, wind-model seed 0, no turbulence). That is 1210 flights. One row per flight branch: 1540
  branches. Each version ran
  twice, and the repeats were bit-identical.
- **Versions.** Base (`unstable`) and prototype (`cp-weight-prototype.patch`).
- **Controls.**
  - (a) The control-patched build with the switch off reproduces the base sweep bit for bit.
  - (b) Rounding control (`control-weight-eps.patch`). The fin CP weight above stall is multiplied by
    (1 + 10⁻¹³). That does not change the physics: Cm and CN are unchanged, and ω_n changes by one part
    in 10¹³. It only exposes how sensitive the results are to the weight through rounding.
  - (c) A time-step perturbation of 10⁻¹² produced no difference at all. It turned out to be an
    ineffective control and is not used as evidence.
- **Classification criterion (fixed before the large sweep was inspected; `classify.py`).** For a flight
  whose TUMBLE outcome differs, take the version that fires first, at t₀, and the other version, whose 6-DOF
  trajectory continues. The event is *genuine* if, in the continuing trajectory during [t₀, t₀+3 s], the
  nose goes below horizontal while thrusting, or the AoA never stays below 20° for 0.5 s. It is *false*
  otherwise.

## 4. Static results

| Mach | max \|reported − consistent\|, α ≤ 18° | max, all α | rockets with a falsely stable band |
|---:|---:|---:|---:|
| 0.1 | 0 | 3.29 cal | 13 / 17 |
| 0.8 | 0 | 3.29 cal | 13 / 17 |
| 1.5 | 0 | 3.43 cal | 14 / 17 |
| prototype, all three | 0 | 0 | 0 / 17 |

The prototype leaves CN and Cm bit-identical at every angle (difference 0).

Example, the TRF #2489 rocket at 26° and Mach 0.1: reported CP 1.037 m, force-consistent CP 0.993 m.
With the motor full (CG 1.065 m) the margins are −0.43 cal reported against −1.07 cal from the forces.

## 5. Dynamic results

### 5.1 Overview (1540 branches)

| comparison with base | TUMBLE outcome changed | TUMBLE timing changed | no-TUMBLE branches not bit-identical |
|---|---:|---:|---:|
| rounding control (b) | 0 | 3 (max 0.025 s) | 43 (max apogee Δ 0.10 m) |
| prototype | **19** | **116** (109 earlier, median −0.98 s, max 1.90 s) | 42 (max apogee Δ 0.11 m) |

### 5.2 The prototype's effect on TUMBLE is real

The rounding control changes no TUMBLE outcome and shifts three timings by at most 0.025 s. The prototype
changes 19 outcomes and 116 timings. These changes come from the different natural frequency, not from
numerical noise.

### 5.3 The trajectory differences without TUMBLE are rounding

Forty-two branches without any TUMBLE are not bit-identical between base and prototype: apogee up to
0.105 m, landing time up to 0.19 s. Tracing one of them field by field, the first dynamic divergence is in
the last digit of the pitch rate (relative 10⁻¹⁶). `AerodynamicForces` stores CP as the moment x·w and
recovers it as (x·w)/w (`BarrowmanStabilityCalculator:271`), so the fin Cm depends on w in its last bit.
The rounding control reproduces the effect: 43 divergent branches, apogee up to 0.101 m, 31 of the 42 in
common. This is ordinary sensitivity of high-angle flights to round-off, which any harmless change would
show. It is not a physical effect of the weights.

### 5.4 Classification of the 19 changed outcomes

All 19 are main-branch flights. The pre-registered criterion gives 12 for the prototype and 7 for the
base. Some windows are cut short by parachute deployment or ground impact, so the cases are split by
robustness:

| case | n | verdict | robust? |
|---|---:|---|---|
| 3D printable, 10 m/s, recovery on/off | 2 | prototype right: nose below horizontal at 0.71 s with the motor burning; base reports an 18 m "flight" | **yes** (decided by the thrust rule) |
| Pods – airframes, sims 1–4, recovery off | 4 | prototype right: base fires TUMBLE mid-turnover, rocket then settles below 20° | **yes** (full window) |
| Tube fin rocket, 0–2 m/s, recovery on/off | 6 | base right: prototype fires TUMBLE in a normal apogee turnover; AoA returns to ~0° and holds | **yes** |
| 3D printable 1–3 m/s, Clustered ×2, Parallel booster, recovery on | 6 | "prototype right" | **no**: the parachute deploys 0.01–1.06 s after t₀, with AoA still at 65–103° |
| Pods – airframes sim 0, recovery off | 1 | "base right" | **no**: ground impact at 1.77 s; AoA reached 0° but held under 0.5 s |

Robust verdicts: **6 improved, 6 made worse**, 7 inconclusive. An earlier manual reading of the Pods
sim 0 trace called it in the prototype's favor; the pre-registered criterion does not support that, and
this report uses the criterion.

### 5.5 What the two failure classes have in common

In the cases the base gets wrong, the inflated frequency keeps the detector slow when the rocket really is
diverging (3D printable, under thrust), or the detector's filter crosses 60° mid-turnover (Pods). In the
case the prototype gets wrong (Tube fin), the now-consistent margin crosses zero during reverse flow
(α ≈ 100–120°), ω_n becomes undefined, and the detector drops to its 0.05 s time constant mid-turnover. A
linearized pitch frequency has no physical meaning in reverse flow, and the detector uses it there either
way.

## 6. Questions for the maintainers

1. Should the CP weight above stall be the secant CN/α (the resultant-force CP, the body's convention) or
   the local slope (the aerodynamic center)? The reported CP, margin and CNα follow from that choice.
2. Should the tumble detector stop relying on the linearized natural frequency at high or reverse-flow
   angles of attack?
3. The two are coupled. Changing (1) without (2) trades one class of detector errors for another
   (section 5.4).

## 7. Limitations

- The 17 rockets are the bundled examples plus one forum rocket. The flight conditions are synthetic
  (steady wind, recovery switched off).
- "Right" and "wrong" are judged from the 6-DOF trajectory the simulation computes, with a fixed
  criterion. They are not measurements. Seven of the 19 cases cannot be decided by that criterion.
- Only fins and tube fins set an inconsistent weight. Pods and boosters inherit it through their fins.

## Files

| path | content |
|---|---|
| `cp-weight-prototype.patch` | the prototype (`FinSetCalc`, `TubeFinSetCalc`) |
| `control-weight-eps.patch` | the rounding control (environment-gated) |
| `CpConsistencyProbeTest.java`, `TumbleSweepProbeTest.java`, `TumbleEventProbeTest.java` | probes |
| `classify.py` | the pre-registered classifier |
| `results/big/` | static sweeps at three Mach numbers, dynamic sweeps (base, prototype, both controls), classification, traces |
| `results/` (top level) | the first, smaller runs (69 + 92 branches) |
