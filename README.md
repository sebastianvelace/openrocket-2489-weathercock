# OpenRocket #2489: weathercocking in strong wind

Investigation of [openrocket/openrocket#2489](https://github.com/openrocket/openrocket/issues/2489):
OpenRocket's simulated upwind distance stops growing, and can reverse sign, as wind speed increases.

The full write-up is in **[REPORT.md](REPORT.md)**. Its first section summarizes the problem, the cause
and the evidence.

## Contents

| path | what it is |
|---|---|
| `REPORT.md` | the investigation |
| `trf_table.tsv` | results table from the TRF thread, hand-transcribed |
| `results/` | raw outputs: per-commit runs, bisect logs, experiments, static aerodynamics, bundled-example impact |
| `indep_sim.py` | independent planar simulator (Python 3, standard library only) |
| `inputs/` | OpenRocket outputs used as inputs by `indep_sim.py` |
| `WeathercockProbeTest.java`, `TimeSeriesProbeTest.java`, `StaticAeroProbeTest.java` | throwaway JUnit probes, dropped into `core/src/test/java/info/openrocket/core/simulation/` of an OpenRocket checkout |
| `run_trf.sh`, `run_exp2.sh`, `bisect_*.sh` | runners used for the sweeps and the bisection |

## Reproducing

- Independent simulator: `python3 indep_sim.py`
- OpenRocket runs:
  1. Check out the commit under test (or create a `git worktree` for it).
  2. Copy the probes into the test sources.
  3. Set `WORK_DIR` for the runners, or the probe environment variables documented at the top of each
     probe (`WC_*`, `TS_*`, `SA_*`).
  4. Run `./gradlew :core:test --tests <probe>` with JDK 17.
- The coefficient experiments (`OR_EXP_BODY_LIFT_K`, `OR_EXP_FIN_STALL_DEG`) need
  `experiment-toggles.patch`, which makes the body lift constant in `SymmetricComponentCalc` and the fin
  stall angle in `FinSetCalc` read those variables. It is for experiments only.
- A second, related finding (the reported CP above the fin stall angle) is in
  [cp-weighting/REPORT.md](cp-weighting/REPORT.md).
- The rocket is `test01.ork`, attached to the first post of the TRF thread
  "Weathercock simulations all over the place" (thread 186584). It is not redistributed here.

## Sources

- H. J. Allen, E. W. Perkins, *A Study of Effects of Viscosity on Flow over Slender Inclined Bodies of
  Revolution*, NACA Report 1048, 1951. https://www.pdas.com/refs/rep1048.pdf
- L. H. Jorgensen, *Prediction of Static Aerodynamic Characteristics for Space-Shuttle-Like and Other
  Bodies at Angles of Attack from 0° to 180°*, NASA TN D-6996, 1973.
  https://ntrs.nasa.gov/api/citations/19730006261/downloads/19730006261.pdf
