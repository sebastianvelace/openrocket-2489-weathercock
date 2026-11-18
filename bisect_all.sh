#!/usr/bin/env bash
# Two first-parent bisects, sequential (memory-limited machine).
SP="${WORK_DIR:?set WORK_DIR to the scratch directory holding wt/ (worktrees) and wc/ (probe inputs and outputs)}"
WT="$SP/wt/bisect"
STEP="$SP/wc/bisect_step.sh"
OUT="$SP/wc/out_bisect"
mkdir -p "$OUT"

# Window 1: upwind at 10 mph drops 240.8 m -> 214.0 m between 21b329d8 and c933edac~1.
echo "=== window1" >> "$OUT/steps.txt"
git -C "$WT" bisect start --first-parent --term-old=old --term-new=new
git -C "$WT" bisect new c933edac~1
git -C "$WT" bisect old 21b329d8
git -C "$WT" bisect run "$STEP" upwind10 227.4 1 > "$OUT/window1.txt" 2>&1
git -C "$WT" bisect log > "$OUT/window1_log.txt" 2>&1
git -C "$WT" bisect reset

# Window 2: apogee at 0 wind drops 2981.3 m -> 2904.7 m between c933edac and 33bdb6d3.
echo "=== window2" >> "$OUT/steps.txt"
git -C "$WT" bisect start --first-parent --term-old=old --term-new=new
git -C "$WT" bisect new 33bdb6d3
git -C "$WT" bisect old c933edac
git -C "$WT" bisect run "$STEP" apogee0 2943.0 1 > "$OUT/window2.txt" 2>&1
git -C "$WT" bisect log > "$OUT/window2_log.txt" 2>&1
git -C "$WT" bisect reset
echo "=== done" >> "$OUT/steps.txt"
