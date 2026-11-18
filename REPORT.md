# OpenRocket issue #2489: why simulated weathercocking stops growing in strong wind

Status: investigation complete, nothing posted upstream. Date: 2026-11-17.
Code: OpenRocket `unstable` at 33bdb6d3 unless stated.

## 1. The problem in one page

**Symptom.** For a long, slender rocket, OpenRocket's simulated upwind distance at apogee (how far the
rocket weathercocks into the wind) stops increasing as the wind gets stronger, then decreases. In
some cases it reverses sign, and the rocket ends up downwind of the pad. RASAero II and RockSim
predict a distance that keeps growing with wind speed. This is the subject of issue #2489, opened from a
TRF comparison made with OpenRocket 23.09.

**What we found.**

1. The 23.09 numbers in the thread are reproduced exactly (within 5 %), including the sign reversal.
   PR #3220 (fin–body interference) fixed most of that. For the thread's rocket, current `unstable`
   is within about 11 % of RASAero up to 15 mph.
2. A downturn remains at high wind: 1116 ft at 25 mph, then 975 ft at 30 mph. In a rocket bundled
   with OpenRocket ("Simulation extensions") the sign still reverses: 332 m *downwind* at 20 mph.
3. **Cause.** The body "crossflow lift" term, `C_N = K · (A_plan/A_ref) · sin²α` with K = 1.1.
   This force acts at the centroid of the body's side profile, ahead of the center of gravity, so it
   *destabilizes*. Just off the launch rail the angle of attack is large (α = atan(wind / rail-exit
   speed) = 26° at 30 mph). At that angle this term moves the center of pressure in front of the center
   of gravity, and the rocket turns into the wind late and weakly.
4. **The coefficient.** K = 1.1 is the crossflow drag coefficient of an *infinitely long* cylinder.
   The method this term comes from (Allen & Perkins, NACA Report 1048; Jorgensen, NASA TN D-6996)
   multiplies it by a finite-length factor η < 1. For this rocket (length/diameter 23.7) the literature
   gives η · C_dn ≈ 0.76–0.94, not 1.1.
5. **The effect of using the reference value.** With the full Jorgensen formulation, the upwind
   distance increases monotonically up to 30 mph across that whole range. Apogees of the 16 bundled
   examples change by ≤ 0.41 % at ≤ 10 mph wind.

**Confidence.** The mechanism is shown three independent ways: one-variable experiments inside
OpenRocket, a change of rail length with no code change, and an independent simulator written from the
physical equations that reproduces OpenRocket within 1–4 %. The 1.1 vs η·C_dn discrepancy is taken from
the primary reports. The physical effect itself, destabilization of a long body at high α, is real
(Galejs). This is therefore not a coding bug. It is a model coefficient that, by its own reference
method, is too large for finite-length rockets. Choosing the fix belongs to the maintainers.

## 2. Setup and conventions

- JDK 17, RK4 stepper, ISA atmosphere, vertical launch. The wind is a steady vector supplied by a
  `preWindModel` listener, with no turbulence, so every run is deterministic. Repeat runs agree within
  0.16 ft.
- Sign. OpenRocket computes airspeed as `rocketVelocity + wind` (`AbstractSimulationStepper.java:86`), so
  with wind vector (W, 0, 0) the +X direction is **upwind**. Checked empirically: under parachute the
  rocket drifts to −X.
- Null control. At 0 wind the upwind distance is −11 ft with spherical geodetics and −0.003 ft with flat
  geodetics. The offset is Coriolis drift from the file's 45° latitude. Mechanism experiments use flat
  geodetics.
- Numerics. RK4 with dt 0.01 s vs 0.001 s, and RK6, differ by ≤ 7 ft (0.7 %) at 30 mph.
- Test rocket. `test01.ork` from TRF thread 186584: fiberglass body 67.3 mm × 1.594 m (l/d 23.7),
  tangent ogive nose, three trapezoidal fins, AeroTech K513FJ, 8 ft rail (rail exit 26.95 m/s),
  max Mach 1.12, apogee ≈ 9530 ft.
- Comparators. The RASAero file uses the same 8 ft rail. The RockSim file stores a 3 ft launch guide.
  RockSim keeps per-simulation launch settings outside the design, so its runs may have used 3 ft. For
  that reason RASAero is the comparison used in this report.

## 3. Reproduction and history

Upwind distance at apogee (ft):

| mph | before #3220 | after #3220 | `unstable` | OR 23.09 (thread) | RASAero II (thread) |
|---:|---:|---:|---:|---:|---:|
| 5 | 322 | 427 | 366 | 327 | 375 |
| 10 | 533 | 790 | 673 | 530 | 698 |
| 15 | 586 | 1066 | 904 | 585 | 1016 |
| 20 | 427 | 1247 | 1055 | 421 | 1324 |
| 25 | −105 | 1307 | 1106 | −118 | 1587 |
| 30 | −1857 | 1142 | 975 | −1930 | 1801 |

The changes after #3220 were located by first-parent bisection, measuring both metrics at every step.
Each traces to an intended, documented fix:

| PR | Effect on this rocket |
|---|---|
| #3220 fin–body interference in CNα | upwind +48 % at 10 mph; sign reversal gone |
| #3319 inertia scaled with overridden subcomponent mass | upwind −9.2 % (the file overrides 1.17 kg of parts to 2.0 kg) |
| #3410 pitch damping about the CG | < 1 % |
| #3431 ogive supersonic wave drag | apogee −2.6 % |
| #3434 jet damping | upwind −1.5 % (only core change in that range) |
| one of #3262 / #3263 (not isolated) | upwind −1.7 % |

No regression was found.

## 4. Mechanism

### 4.1 What OpenRocket computes (static, Mach 0.1)

A probe of `BarrowmanCalculator` returns, for the body, exactly `2 sin α + 1.1 · 28.0 · sin²α`. It matches
a hand calculation to three decimals at every angle from 0° to 40°. For this rocket A_plan/A_ref = 28.0
and the plan-area centroid is at 0.852 m from the nose. The CG is at 1.065 m with the motor full and
0.952 m at burnout, so the crossflow force acts ahead of the CG.

The fin model was checked independently. Barrowman with (1+τ) gives CNα = 7.777, the same value stored in
the RockSim file. With the (1+τ)² factor from #3220 it gives 10.327; OpenRocket uses 10.329.

Center of pressure consistent with the summed normal force and moment, vs α:

| α | 10° | 18° | 22° | 26° | 30° |
|---|---:|---:|---:|---:|---:|
| OpenRocket (K = 1.1) | 1.111 | 1.064 | 1.031 | 0.993 | 0.964 |
| Jorgensen, η = 0.72 | 1.131 | 1.091 | 1.061 | 1.023 | 0.995 |
| without crossflow term | 1.223 | 1.225 | 1.209 | 1.179 | 1.152 |

With the motor full, OpenRocket puts the CP behind the CG only below α ≈ 18°. With Jorgensen's
coefficient the limit is α ≈ 22°.

### 4.2 What happens in flight

The angle of attack just off the rail is 13.7°, 18.0°, 22.1° and 26.0° at 15, 20, 25 and 30 mph. The
analytic value atan(W / V_rail) is 26.4° at 30 mph. Above about 18° the rocket is momentarily statically
unstable (−1.07 cal at 26°), so it starts turning into the wind late. At t = 0.5 s its pitch from
horizontal is still 89.5° at 30 mph, against 88.0° at 20 mph. The angle of attack is above the 20° fin
stall limit for only 0.06 s.

### 4.3 One-variable experiments in OpenRocket

These use a scratch worktree with environment-variable switches. With default values, the patched build
reproduces the original within 0.022 m.

| mph | K = 1.1 | K = 0.94 | K = 0.86 | K = 0.76 | K = 0 | fin stall off | RASAero |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 684 | 705 | 715 | 728 | 816 | 684 | 698 |
| 20 | 1066 | 1162 | 1208 | 1263 | 1623 | 1059 | 1324 |
| 25 | 1116 | 1280 | 1356 | 1447 | 2011 | 1112 | 1587 |
| 30 | 986 | 1253 | 1374 | 1517 | 2346 | 1063 | 1801 |

The crossflow coefficient controls the downturn. The fin stall cap is secondary (+77 ft at 30 mph).

### 4.4 Same mechanism with no code change: rail length (K = 1.1)

| rail | 10 mph | 20 mph | 25 mph | 30 mph |
|---|---:|---:|---:|---:|
| 0.91 m (3 ft) | 704 | 926 | 731 | 220 |
| 2.44 m (8 ft) | 684 | 1066 | 1116 | 986 |
| 6 m | 608 | 1037 | 1173 | 1256 |
| 12 m | 496 | 896 | 1051 | 1174 |

A longer rail means a faster rail exit and a smaller α, and the downturn disappears. A short rail makes
it much worse.

### 4.5 Independent simulator (`indep_sim.py`)

This is a planar model (translation plus pitch, RK4) written from the equations, not from OpenRocket's
code. It has its own ISA atmosphere, rail constraint, Barrowman nose and fin centers of pressure,
crossflow lift, techdoc-type pitch damping and jet damping. Thrust, mass, CG, inertia, the axial-drag
history and the fin CNα(Mach) table are taken from OpenRocket as inputs. None of them is the quantity
under test.

| Upwind ft | 10 mph | 20 mph | 25 mph | 30 mph |
|---|---:|---:|---:|---:|
| OpenRocket, K = 1.1 | 684 | 1066 | 1116 | 986 |
| independent, K = 1.1 | 697 | 1097 | 1154 | 1029 |
| OpenRocket, K = 0.86 | 715 | 1208 | 1356 | 1374 |
| independent, K = 0.86 | 727 | 1234 | 1387 | 1408 |
| OpenRocket, K = 0 | 816 | 1623 | 2011 | 2346 |
| independent, K = 0 | 825 | 1636 | 2022 | 2356 |

The two agree within 1–4.4 % (apogee: 9532 vs 9530 ft), so the downturn follows from the physics of the
model and not from another part of OpenRocket. Pitch damping does not matter here: scaling it by 0 or by
5 changes the result by ≤ 4 ft, because (q/V)² is tiny. The step size has converged: dt 0.002 s vs
0.0005 s differ by 1 %.

## 5. The coefficient in the literature

OpenRocket's technical documentation (section "Effect of body lift") gives `C_N = K A_plan/A_ref sin²α`
with "K ≈ 1.1". It cites Galejs and Hoerner p. 3-11 and applies no finite-length correction. The Galejs
link in the techdoc is dead, so that paper was not read. The same 1.1 also appears in the body pitch
damping term (0.275 = 1.1/4), which section 4.5 shows to be irrelevant here.

- **Allen & Perkins, NACA Report 1048 (1951)**, the origin of the method. They state that for actual
  bodies of finite length "a somewhat smaller value should be used" than the infinite-cylinder
  coefficient. With c_dc = 1.2 at low Mach they use a finite/infinite ratio of **0.755 for a body of
  fineness ratio 21.1** and 0.692 for 13.1, taken from low-speed cylinder data. With this allowance their
  prediction for the fineness-21 body "is in good agreement with experiment" (their tests were at
  M ≈ 2).
- **Jorgensen, NASA TN D-6996 (1973)**, eq. (1):
  `C_N = (A_b/A) sin2α cos(α/2) + η C_dn (A_p/A) sin²α`. Here C_dn ≈ 1.2 for subcritical crossflow
  Reynolds number (fig. 2), and η is from fig. 4: ≈ 0.72 at l/d 24, read to ±0.03. The report says η can
  probably be taken as 1 at supersonic speed.
- **This rocket's regime.** Just off the rail at 30 mph, Re_n = Re·sinα ≈ 6×10⁴, which is subcritical,
  and the crossflow Mach number is about 0.04. The high-α phase is therefore exactly where the subsonic
  η applies.

The plausible range is η·C_dn = 0.76–0.94 (η 0.69–0.78, C_dn 1.1–1.2), against OpenRocket's 1.1.

Results across that range:

| model | 20 mph | 25 mph | 30 mph | monotonic to 30 mph |
|---|---:|---:|---:|---|
| OpenRocket form, K = 1.1 | 1097 | 1154 | 1029 | no |
| OpenRocket form, K = 0.94 | 1190 | 1313 | 1290 | no (slight) |
| OpenRocket form, K = 0.86 | 1234 | 1387 | 1408 | yes |
| OpenRocket form, K = 0.76 | 1288 | 1475 | 1547 | yes |
| full Jorgensen, η = 0.78 | 1213 | 1359 | 1377 | yes |
| full Jorgensen, η = 0.72 | 1252 | 1424 | 1480 | yes |

(Independent simulator. OpenRocket gives the same pattern at K = 0.94 and 0.76.) Changing only K inside
OpenRocket's form leaves a slight downturn at the upper end of the range. Jorgensen's complete expression
is monotonic over the whole range.

## 6. Generality and impact

- **Bundled example.** In "Simulation extensions" (and its twin "Simulation scripting"), with a 14 cm
  body, an L motor and a rail exit at 14.9 m/s, the upwind distance is +159 / +205 / +106 / −332 m at
  5 / 10 / 15 / 20 mph with K = 1.1. With K = 0.86 it is +171 / +258 / +248 / +26 m. That is much better,
  but still not monotonic at this low rail-exit speed.
- **Normal flights.** Over all 16 bundled examples at 0–20 mph, K = 0.86 changes apogee by ≤ 0.41 % at
  ≤ 10 mph and by at most 3.65 % at 20 mph (three-stage low-power rocket). No simulation aborts.

## 7. What is not established

- That any specific value is *correct*. RockSim and RASAero are models, not measurements. There are
  no flight data here.
- That destabilization at high α off the rail is unphysical. It is real (Galejs); the question is its
  size.
- How η should depend on Mach (Jorgensen suggests η → 1 when supersonic), how C_dn should depend on
  crossflow Reynolds and Mach number (it drops to ~0.3 in the critical range), and whether η should use
  the whole body's l/d. OpenRocket applies K per component.
- Whether developed steady crossflow is reached at rail exit. The rocket has moved through the crossflow
  for the whole rail travel, but impulsive-start effects were not quantified.
- The remaining 15–25 % gap to RASAero at 25–30 mph.

## 8. Secondary finding (separate from #2489)

Above the 20° fin stall angle, the *reported* center of pressure and stability margin do not match the
forces applied. `FinSetCalc` (lines 231–232) caps the fin CN but keeps the uncapped CNα as the CP weight,
and `AerodynamicForces.merge` (line 472) averages CP with those weights. At 26°: reported CP 1.037 m,
moment-consistent CP 0.993 m. Trajectories are not affected, because the stepper uses the summed Cm
(`AbstractRKSimulationStepper.java:318`). Only the plotted CP and stability margin are.

## 9. Files

| path | content |
|---|---|
| `trf_table.tsv` | hand-transcribed TRF table (the thread's `test01.ork/.rkt/.CDX1` are not redistributed here; download them from the TRF thread) |
| `results/` | per-commit runs; `bisect/`; `experiments/` (K, stall, rail, convergence); `static/`; `impact/` |
| `inputs/` | OpenRocket outputs used as inputs by the independent simulator |
| `indep_sim.py` | independent simulator |
| `*ProbeTest.java`, `*.sh` | throwaway OpenRocket probes and runners (not for upstream) |
| sources below | NACA Report 1048 and NASA TN D-6996 (public documents, linked rather than copied) |

Sources: Allen, H. J. & Perkins, E. W., NACA Report 1048, 1951 (https://www.pdas.com/refs/rep1048.pdf);
Jorgensen, L. H., NASA TN D-6996, 1973
(https://ntrs.nasa.gov/api/citations/19730006261/downloads/19730006261.pdf).
