# OpenRocket: the reported CP is inconsistent with the applied forces above the fin stall angle

Status: investigation complete, nothing posted upstream. Date: 2026-11-17.
Code: OpenRocket `unstable` at 33bdb6d3.

## 1. The problem in one page

**What is wrong.** Above 20° angle of attack, OpenRocket's reported center of pressure does not match the
forces it applies. This affects the reported CP, the stability margin, CNα, and the natural frequency and
damping ratio derived from them. The cause is a weighting mismatch in the fin calculations:

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

**How big.** Measured over the 16 bundled examples and the TRF #2489 rocket:

- Below 20° the reported CP and the CP implied by the summed forces (Cm·L_ref/CN) agree exactly
  (difference 0.000000 cal). This is the null control.
- At 90° the reported CP is 1.1 to 3.3 calibers aft of the force-consistent CP.
- In 12 of the 17 rockets there is a band of angles, starting between 22° and 56°, where the reported
  margin is positive (stable) while the applied forces are destabilizing.

**Why it matters beyond the plots.** The natural frequency is computed from the same weights
(`AbstractSimulationStepper.computeCorrectiveMomentCoefficient`: `cna = getCP().getWeight()`,
`0.5ρV²A·cna·(cp − cg)`). The tumble detector uses that frequency to set its filter time constant: two
pitch periods, or 0.05 s when the rocket is statically unstable. A falsely stable rocket therefore gets a
filter time of up to 2 s instead of 0.05 s, which changes when, or whether, TUMBLE fires. TUMBLE in turn
switches the simulation to the tumbling descent model.

**What the trajectory does not see.** The equations of motion use the summed Cm, which respects the stall
cap. Trajectories are identical until a TUMBLE event differs.

**A consistent fix is a two-line change** in each fin calculation: weight the CP by the effective CN/α
above stall, which is the convention the body already uses. With it the reported CP equals the
force-consistent CP at every angle for all 17 rockets (maximum difference 0), CN and Cm are unchanged
(difference 0), and the full core suite passes (1762/1762). But it changes the tumble detector's behavior,
in both directions (section 5). That makes it a design decision for the maintainers, not a drop-in fix.

## 2. Where the weights come from (history)

- Up to OpenRocket 23.09, `AerodynamicForces` stored CNα separately (`setCNa`). The fins set it to `cna`
  and also used `cna` as the CP weight. This is the small-angle "aerodynamic center" definition.
- #2753 (2025-03, fixing a NaN CP when nose and tail cone CNα cancel) removed the separate field. Since
  then "CNα" is the CP weight. #3010 (2026-01) exposes it as the flight data type "normal force
  coefficient derivative". `AbstractSimulationStepper` carries `// TODO: replace with getCNa() when
  available` where it reads the weight as CNα.
- The body has always weighted its CP by `CNα·sinc(α) + K·sin²α/α`. That is the secant CN/α, not the
  derivative: the derivative of K·sin²α would be 2K·sinα·cosα.

So above the fin stall angle the reported CP is neither the resultant-force CP, which would need the
fins' secant CN/α, nor the aerodynamic center of the model, which would need the fins' slope (zero, since
their CN is flat). It mixes the two definitions.

## 3. Method

- **Static probe** (`CpConsistencyProbeTest`). At Mach 0.3 and α from 1° to 90°, for each rocket it
  records the reported CP (`getCP()`), the CP weight, CN, Cm, and the force-consistent CP
  Cm·L_ref/CN. Launch and burnout CG come from `MassCalculator`.
- **Dynamic probe** (`TumbleEventProbeTest`). It runs the first simulation of each rocket with all
  randomness pinned (seed 0, fixed, wind-model seed 0, no turbulence) and a steady listener wind. For
  every flight branch it records the TUMBLE time, apogee, landing and aborts. It ran on normal flights
  (winds 0/5/10 m/s, 69 branches) and with recovery disabled (winds 0/3/6/9 m/s, 92 branches), which
  forces unassisted apogee turnovers. Each configuration ran twice, and the repeats were bit-identical.
- **Prototype**: `cp-weight-prototype.patch`.

## 4. Static results

| | value |
|---|---|
| max \|reported − consistent\| CP, α ≤ 18°, all rockets | 0.000000 cal |
| max \|reported − consistent\| CP at 90° | 1.1 – 3.3 cal (rocket dependent) |
| rockets with a falsely stable band (launch or burnout CG) | 12 / 17 |
| with the prototype: max \|reported − consistent\| CP, 1–90° | 0 |
| with the prototype: max \|ΔCN\| + \|ΔCm\| | 0 |

Example, the TRF #2489 rocket at 26°: reported CP 1.037 m, force-consistent CP 0.993 m. With the motor
full (CG 1.065 m) the margins are −0.43 cal reported against −1.07 cal from the forces.

## 5. Dynamic results (tumble detection)

| set | branches | TUMBLE timing changed | classification changed |
|---|---:|---:|---:|
| normal flights | 69 | 0 | 2 |
| recovery disabled | 92 | 13 (10 earlier, 3 later; largest shift 1.63 s) | 2 |

The flights whose classification changed (the Tube fin case appears in both sets):

1. **3D printable nose cone and fins, 10 m/s wind. The prototype is right.** The trajectories are identical
   in both runs until 0.575 s. At α = 31° the current code reports +0.25 cal (stable, ω_n = 4.5 rad/s);
   the prototype reports −0.41 cal (unstable). With the motor still burning (burnout at 0.73 s) the
   rocket pitches past horizontal: θ = −0.6° at 0.62 s and −74° at 0.71 s. The current code does not flag
   it, keeps simulating a rocket cartwheeling under thrust, and returns a "flight" with an 18 m apogee and
   TUMBLE at 2.65 s. The prototype aborts with `TUMBLE_UNDER_THRUST` at 0.61 s.
2. **Pods – airframes and winglets, recovery disabled, no wind. The prototype is right.** The current code
   fires TUMBLE at 4.36 s, in the middle of the apogee turnover (α ≈ 100°). Without it, the rocket keeps
   flying in 6-DOF and settles nose-down (θ ≈ −83°), with α oscillating down from 67° to under 6°.
3. **Tube fin rocket, no wind (both sets). The prototype is wrong.** The rocket falls tail-first at apogee
   (α ≈ 179°) and turns over normally: in the current code α reaches 4.6° by 7.46 s. With the prototype,
   the margin crosses zero during the turnover (α between 117° and 100°), ω_n becomes NaN, the detector
   drops to its 0.05 s time constant, and TUMBLE fires at 6.97 s. This is a false positive.

**Interpretation.** Once the CP is made consistent, the tumble detector's filter time is driven by a
linearized natural frequency at angles (> 90°, reverse flow) where linearization has no physical meaning.
The current code hides this because its inflated weights keep ω_n finite through most turnovers. That
also hides genuine instability at 30–60° under thrust (case 1). Fixing the CP alone corrects two
classifications and breaks one in this sample. The detector needs a rule for the high-angle and
reverse-flow regime that does not rest on ω_n there.

## 6. Questions for the maintainers

1. Should the CP weight above stall be the secant CN/α (the resultant-force CP, as the body already uses)
   or the local slope (the aerodynamic center, zero for a stalled fin)? The reported CP, margin and CNα
   follow from that choice.
2. Should the natural frequency used by the tumble detector come from the same weights, or should the
   detector stop using ω_n above some angle of attack, for example in reverse flow?
3. The two are coupled: changing (1) without (2) trades one class of detector errors for another
   (section 5).

## 7. Limitations

- The dynamic sample is 161 branches from 17 rockets. It shows both kinds of change but cannot rank them
  by frequency in real use.
- "Right" and "wrong" in section 5 are judged from the 6-DOF trajectory the simulation computes. They are
  not measurements.
- Only the fin and tube-fin weights were examined. Pods, boosters and other components inherit their fins'
  behavior.

## Files

| path | content |
|---|---|
| `cp-weight-prototype.patch` | the two-line prototype in `FinSetCalc` and `TubeFinSetCalc` |
| `CpConsistencyProbeTest.java`, `TumbleEventProbeTest.java` | probes (JUnit, dropped into core's test sources) |
| `results/cp_static_*.tsv` | static sweep, current code and prototype |
| `results/tumble_*.tsv` | per-branch events, normal flights and recovery disabled, current code and prototype |
| `results/traces/` | time series of the three reclassified flights |
