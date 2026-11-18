#!/usr/bin/env bash
# git bisect run helper. Usage: bisect_step.sh <metric> <threshold> <old_is_above:1|0>
#   metric: upwind10 (x at apogee, 10 mph, m) | apogee0 (apogee at 0 wind, m)
# Exit 0 = old, 1 = new, 125 = skip (build/test failure).
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
SP="${WORK_DIR:?set WORK_DIR to the scratch directory holding wt/ (worktrees) and wc/ (probe inputs and outputs)}"
WT="$SP/wt/bisect"
metric=$1; thr=$2; old_above=$3
sha=$(git -C "$WT" rev-parse --short HEAD)
cp "$SP/wc/WeathercockProbeTest.java" "$WT/core/src/test/java/info/openrocket/core/simulation/"
export WC_ORK_DIR=$SP/wc/trf_ork WC_OUT_DIR=$SP/wc/out_bisect WC_WINDS_MPH=0,10 WC_LABEL="bisect_${sha}"
log="$SP/wc/out_bisect/${WC_LABEL}.log"
mkdir -p "$SP/wc/out_bisect"
( cd "$WT" && timeout 1500 ./gradlew :core:test --tests 'info.openrocket.core.simulation.WeathercockProbeTest' --rerun -q ) > "$log" 2>&1
status=$?
rm -f "$WT/core/src/test/java/info/openrocket/core/simulation/WeathercockProbeTest.java"
tsv="$SP/wc/out_bisect/${WC_LABEL}.tsv"
if [ $status -ne 0 ] || [ ! -f "$tsv" ]; then echo "$sha SKIP (gradle $status)" >> "$SP/wc/out_bisect/steps.txt"; exit 125; fi
apo0=$(awk -F'\t' 'NR==2{print $4}' "$tsv")
up10=$(awk -F'\t' 'NR==3{print $5}' "$tsv")
if [ "$metric" = apogee0 ]; then v=$apo0; else v=$up10; fi
above=$(awk -v a="$v" -v t="$thr" 'BEGIN{print (a>t)?1:0}')
if [ "$above" = "$old_above" ]; then verdict=old; rc=0; else verdict=new; rc=1; fi
echo "$sha metric=$metric value=$v apogee0=$apo0 upwind10=$up10 -> $verdict" >> "$SP/wc/out_bisect/steps.txt"
exit $rc
