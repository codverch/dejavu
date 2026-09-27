#!/bin/bash
# Progress of the start-up prefetching study as a green battery, for the Claude Code status line.
#
#   progress.sh            print the cached battery (instant); refresh the cache in the background if
#                          it is older than 60 s
#   progress.sh --refresh  recompute now (queries the pod) and print
#
# Weights (percent of the study): W0 benchmark 10, W1 creation analysis 10, W2 prediction 10,
# W3 baseline simulations 25, W4 ideal-prefetch simulations 30, W5 report 10, branches pushed 5.
# W3 and W4 count finished simulations on the pod; the others count as done when their README exists.
R=/h/deepanjm/dejavu-wt/ideal-prefetching/results/startup-prefetch
POD=/localdisk/deepanjm/isca-traces/startup-prefetch
CACHE=/tmp/startup_prefetch_progress.txt
W3_TOTAL=613
W4_TOTAL=765

compute() {
  local w3 w4 pct=0 note=""
  read -r w3 w4 < <(timeout 20 kubectl exec -n deepanjm deepanjm-a100 -c work -- bash -c \
    "ls $POD/w3/runs/*/result.json.gz 2>/dev/null | wc -l; ls $POD/w4/runs/*/result.json.gz 2>/dev/null | wc -l" 2>/dev/null | paste -sd' ')
  w3=${w3:-0}; w4=${w4:-0}
  [ -f "$R/w0_benchmark/README.md" ] && pct=$((pct + 10))
  [ -f "$R/w1_creation/README.md" ] && pct=$((pct + 10))
  [ -f "$R/w2_prediction/README.md" ] && pct=$((pct + 10))
  if [ -f "$R/w3_baseline/results.csv" ]; then pct=$((pct + 25)); else pct=$((pct + 25 * (w3 > W3_TOTAL ? W3_TOTAL : w3) / W3_TOTAL)); fi
  if [ -f "$R/w4_ideal_prefetch/results.csv" ]; then pct=$((pct + 30)); else pct=$((pct + 30 * (w4 > W4_TOTAL ? W4_TOTAL : w4) / W4_TOTAL)); fi
  [ -f "$R/w5_report/REPORT.md" ] && pct=$((pct + 10))
  git -C /h/deepanjm/dejavu-wt/ideal-prefetching ls-remote --exit-code origin ideal-prefetching >/dev/null 2>&1 && pct=$((pct + 5))
  if [ ! -f "$R/w3_baseline/results.csv" ]; then note="W3 sims $w3/$W3_TOTAL"
  elif [ ! -f "$R/w4_ideal_prefetch/results.csv" ]; then note="W4 sims $w4/$W4_TOTAL"
  elif [ ! -f "$R/w5_report/REPORT.md" ]; then note="writing report"
  else note="push"; fi
  local n=$((pct / 10)) bar=""
  for i in $(seq 1 10); do [ "$i" -le "$n" ] && bar="${bar}█" || bar="${bar}░"; done
  printf '\033[32m🔋 [%s] %d%%\033[0m %s\n' "$bar" "$pct" "$note" > "$CACHE.tmp" && mv "$CACHE.tmp" "$CACHE"
}

if [ "${1:-}" = "--refresh" ] || [ ! -f "$CACHE" ]; then
  compute
elif [ $(( $(date +%s) - $(stat -c %Y "$CACHE") )) -gt 60 ]; then
  ( compute & ) >/dev/null 2>&1
fi
cat "$CACHE"
