import json, sys, csv, re
D = "/localdisk/deepanjm/deadblock/sims"
s = json.load(open(f"{D}/final/summary.json"))
for sc, d in s["dead_state_lru"].items():
    print(sc)
    for c, v in d.items():
        print("   %-10s dead capacity-time %.0f-%.0f%%  dead-on-arrival %.0f%%" % (
            c, 100 * v["dead_capacity_time_lo"], 100 * v["dead_capacity_time_hi"], 100 * (v["dead_on_arrival_of_removed"] or 0)))
a = s["aggregate"]["all"]
print("LRU LLC MPKI %.2f" % a["lru"]["llc_mpki"])
for c in ["mj", "oracle_byp", "never_byp", "min"]:
    print("%-11s speedup 95%% CI %+.2f..%+.2f%%  faster/slower units %d/%d  LLC MPKI %.2f" % (
        c, 100 * (a[c]["sp_lo"] - 1), 100 * (a[c]["sp_hi"] - 1), a[c]["units_faster"], a[c]["units_slower"], a[c]["llc_mpki"]))
# Mockingjay warm-predictor sensitivity, same HT weighting
units = list(csv.DictReader(open(f"{D}/units_all.tsv"), delimiter="\t"))
def per(u, c):
    for l in open(f"{D}/runs/{u['task']}/{u['cid']}/{c}/core.stat.0.out"):
        if l.startswith("Periodic:"):
            m = re.search(r"Cycles:\s*(\d+)\s+Instructions:\s*(\d+)", l); return int(m[1]), int(m[2])
tot = {c: [0.0, 0.0] for c in ["lru", "mj", "mj_warm"]}
for u in units:
    f = float(u["weight"]) / float(u["pi"])
    for c in tot:
        cy, ins = per(u, c); tot[c][0] += f * cy; tot[c][1] += f * ins
for c, (cy, ins) in tot.items():
    print("%-8s IPC %.3f  vs LRU %+.2f%%" % (c, ins / cy, 100 * (tot["lru"][0] / cy - 1)))
