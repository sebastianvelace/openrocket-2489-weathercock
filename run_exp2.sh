#!/usr/bin/env bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
SP="${WORK_DIR:?set WORK_DIR to the scratch directory holding wt/ (worktrees) and wc/ (probe inputs and outputs)}"
export TS_ORK=$SP/wc/trf_ork/test01.ork TS_OUT=$SP/wc/ts TS_WINDS_MPH=0,10,20,25,30 TS_FLAT=1 OR_EXP_FIN_STALL_DEG=20
cd $SP/wt/head
run() { # label K rod dt stepper
  export TS_LABEL=$1 OR_EXP_BODY_LIFT_K=$2 TS_ROD=$3 TS_DT=$4 TS_STEPPER=$5
  timeout 1500 ./gradlew :core:test --tests 'info.openrocket.core.simulation.TimeSeriesProbeTest' --rerun -q > $SP/wc/ts_$1.log 2>&1
  echo "$1 gradle exit: $?"
}
run conv_rk4_dt01   1.1 2.4384 0.01  RK4
run conv_rk4_dt001  1.1 2.4384 0.001 RK4
run conv_rk6_dt01   1.1 2.4384 0.01  RK6
run rail_0.914      1.1 0.9144 0.01  RK4
run rail_6          1.1 6.0    0.01  RK4
run rail_12         1.1 12.0   0.01  RK4
run rail_0.914_K086 0.86 0.9144 0.01 RK4
run rail_12_K086    0.86 12.0  0.01  RK4
