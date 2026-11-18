#!/usr/bin/env bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
SP="${WORK_DIR:?set WORK_DIR to the scratch directory holding wt/ (worktrees) and wc/ (probe inputs and outputs)}"
export WC_ORK_DIR=$SP/wc/trf_ork WC_OUT_DIR=$SP/wc/out_trf WC_WINDS_MPH=0,5,10,15,20,25,30
for wt in "$@"; do
  for run in 1 2; do
    export WC_LABEL="${wt}_run${run}"
    log="$SP/wt/trf_${WC_LABEL}.log"
    ( cd "$SP/wt/$wt" && timeout 1200 ./gradlew :core:test --tests 'info.openrocket.core.simulation.WeathercockProbeTest' --rerun -q ) > "$log" 2>&1
    echo "gradle exit: $?" >> "$log"
    echo "$WC_LABEL $(tail -1 "$log")"
  done
done
