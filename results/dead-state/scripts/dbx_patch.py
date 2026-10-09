#!/usr/bin/env python3
"""Wire libs/dbx.{c,h} into a Scarab tree (79dadf3). Every anchor must match exactly
once (or once inside the named function); otherwise the patch aborts untouched.

Usage: dbx_patch.py <scarab_root>
"""
import sys
from pathlib import Path

MARK = "libs/dbx.h"


def fn_body(s, sig):
    a = s.find(sig)
    if a < 0:
        raise SystemExit(f"signature not found: {sig}")
    b = s.find("\n}\n", a)
    return a, b


def sub(s, old, new, sig=None, fname=""):
    if sig:
        a, b = fn_body(s, sig)
        body = s[a:b]
        if body.count(old) != 1:
            raise SystemExit(f"{fname}: anchor x{body.count(old)} in {sig!r}:\n{old}")
        return s[:a] + body.replace(old, new, 1) + s[b:]
    if s.count(old) != 1:
        raise SystemExit(f"{fname}: anchor x{s.count(old)}:\n{old}")
    return s.replace(old, new, 1)


def main():
    out = {}
    src = Path(sys.argv[1]) / "src"
    h, c, m, p, st = (src / "libs/cache_lib.h", src / "libs/cache_lib.c", src / "memory/memory.c",
                      src / "memory/memory.param.def", src / "statistics.c")
    if MARK in c.read_text():
        print("already patched")
        return

    # ---- cache_lib.h: per-line fields
    s = h.read_text()
    s = sub(s, """  uns8 reference_val; /* for re-reference replacement policy */
  Flag outcome;       /* for replacement policy */
} Cache_Entry;""", """  uns8 reference_val; /* for re-reference replacement policy */
  Flag outcome;       /* for replacement policy */

  /* libs/dbx.c */
  Counter db_reuse; /* touches since fill */
  uns32 dbx_k;      /* touch ordinal of the last touch (target cache) */
  Flag dbx_dead;    /* oracle: dead after its last touch */
  uns64 dbx_next;   /* MIN: pass-1 index of the next touch */
  int dbx_etr;      /* Mockingjay: estimated time remaining */
} Cache_Entry;""", fname="cache_lib.h")
    out[h] = s

    # ---- cache_lib.c
    s = c.read_text()
    s = sub(s, '#include "libs/cache_lib.h"\n', '#include "libs/cache_lib.h"\n#include "libs/dbx.h"\n', fname="cache_lib.c")
    s = sub(s, """        cache->num_demand_access++;
        update_repl_policy(cache, line, set, ii, FALSE);""", """        cache->num_demand_access++;
        update_repl_policy(cache, line, set, ii, FALSE);
        dbx_on_hit(cache, set, ii, line);""",
            sig="void* cache_access_impl(", fname="cache_lib.c")
    ins = "void* cache_insert_replpos(Cache* cache, uns8 proc_id, Addr addr, Addr* line_addr, Addr* repl_line_addr,"
    s = sub(s, """    new_line = find_repl_entry(cache, proc_id, set, &repl_index);
""", """    new_line = find_repl_entry(cache, proc_id, set, &repl_index);
    dbx_on_evict(cache, set, repl_index, new_line);
""", sig=ins, fname="cache_lib.c")
    s = sub(s, """  if (cache->repl_policy == REPL_IDEAL_STORAGE) {
    new_line->last_access_time = cache->assoc;""", """  if (cache->repl_policy != REPL_IDEAL)
    dbx_on_fill(cache, set, repl_index, new_line);
  if (cache->repl_policy == REPL_IDEAL_STORAGE) {
    new_line->last_access_time = cache->assoc;""", sig=ins, fname="cache_lib.c")
    s = sub(s, """    if (line->tag == tag && line->valid) {
      line->tag = 0;
      line->valid = FALSE;""", """    if (line->tag == tag && line->valid) {
      dbx_on_invalidate(cache, set, ii, line);
      line->tag = 0;
      line->valid = FALSE;""", sig="void cache_invalidate(", fname="cache_lib.c")
    s = sub(s, """  if (cache->repl_policy >= REPL_VOID)
    return cache_evict_strategy(cache, proc_id, set, way);
""", """  if (cache->repl_policy >= REPL_VOID)
    return cache_evict_strategy(cache, proc_id, set, way);

  {
    Cache_Entry* dbx_victim = dbx_find_victim(cache, set, way);
    if (dbx_victim)
      return dbx_victim;
  }
""", sig="Cache_Entry* find_repl_entry(Cache* cache", fname="cache_lib.c")
    s = sub(s, """  cache->tag_incl_offset = FALSE;
}""", """  cache->tag_incl_offset = FALSE;

  dbx_register(cache);
}""", fname="cache_lib.c")
    out[c] = s

    # ---- memory.c: request context for the LLC ("L1" in Scarab) + bypass
    s = m.read_text()
    s = sub(s, '#include "ramulator.param.h"\n', '''#include "ramulator.param.h"

#include "libs/dbx.h"

/* dbx: tell the policy layer which request is about to touch the LLC. The PC is the
   requesting instruction's (loads/stores), the fetch address (instruction fetches, whose
   requests carry no op), or the triggering load's (prefetches). */
static inline void dbx_ctx_from_req(Cache* cache, Mem_Req* req) {
  Dbx_Req_Type t;
  Addr pc;
  if (req->type == MRT_WB || req->type == MRT_WB_NODIRTY)
    t = DBX_WRITEBACK;
  else if (mem_req_type_is_prefetch(req->type))
    t = DBX_PREFETCH;
  else
    t = DBX_DEMAND;
  pc = t == DBX_PREFETCH ? req->pref_loadPC : req->loadPC;
  /* instruction-side requests carry no op: their PC is the fetch address */
  if (!pc && (req->type == MRT_IFETCH || req->type == MRT_IPRF || req->type == MRT_UOCPRF ||
              req->type == MRT_FDIPPRFON || req->type == MRT_FDIPPRFOFF || req->type == MRT_FDIPPRFALT))
    pc = req->addr;
  /* a demand that merged into an in-flight prefetch keeps the prefetch's (empty) loadPC */
  if (!pc)
    pc = req->oldest_op_addr;
  dbx_set_ctx(cache, pc, t, (uns)req->type);
}
''', fname="memory.c")
    s = sub(s, """  data = (L1_Data*)cache_access(&L1(req->proc_id)->cache, req->addr, &line_addr,
                                update_l1_lru);  // access L2""", """  dbx_ctx_from_req(&L1(req->proc_id)->cache, req);
  data = (L1_Data*)cache_access(&L1(req->proc_id)->cache, req->addr, &line_addr,
                                update_l1_lru);  // access L2""", fname="memory.c")
    s = sub(s, """  /* Do not insert the line yet, just check which line we
     need to replace.""", """  /* dbx: a bypassed fill is satisfied without allocating in the LLC; the line still
     continues to the MLC/L1 fill stages exactly as a normal fill does. */
  dbx_ctx_from_req(&L1(req->proc_id)->cache, req);
  if (dbx_fill_bypass(&L1(req->proc_id)->cache, req->addr)) {
    req->l1_miss_satisfied = TRUE;
    req->l1_miss_cycle = MAX_CTR;
    if (TRACK_L1_MISS_DEPS || MARK_L1_MISSES)
      mark_ops_as_l1_miss_satisfied(req);
    return SUCCESS;
  }

  /* Do not insert the line yet, just check which line we
     need to replace.""", sig="Flag l1_fill_line(Mem_Req* req)", fname="memory.c")
    out[m] = s

    # ---- params
    s = p.read_text()
    s += """
/* libs/dbx.c: dead-block study. dbx_cache names the one cache the policy applies to
   (e.g. L1_CACHE = the LLC); dbx_policy 0 LRU, 1 Mockingjay, 2 oracle dead-block,
   3 Belady MIN, 4 never-reused oracle. dbx_log_out writes the pass-1 touch log; dbx_table_in reads pass 2. */
DEF_PARAM(dbx_cache, DBX_CACHE, char*, string, NULL, )
DEF_PARAM(dbx_policy, DBX_POLICY, uns, uns, 0, )
DEF_PARAM(dbx_log_out, DBX_LOG_OUT, char*, string, NULL, )
DEF_PARAM(dbx_table_in, DBX_TABLE_IN, char*, string, NULL, )
DEF_PARAM(dbx_stat_out, DBX_STAT_OUT, char*, string, "dbx.stat.out", )
DEF_PARAM(dbx_min_bypass, DBX_MIN_BYPASS, Flag, Flag, TRUE, )
DEF_PARAM(dbx_oracle_bypass, DBX_ORACLE_BYPASS, Flag, Flag, FALSE, )
DEF_PARAM(dbx_mj_rdp_in, DBX_MJ_RDP_IN, char*, string, NULL, )
DEF_PARAM(dbx_mj_rdp_out, DBX_MJ_RDP_OUT, char*, string, NULL, )
"""
    out[p] = s

    # ---- statistics.c: warmup-end reset
    s = st.read_text()
    s = sub(s, "void reset_stats(Flag keep_total) {\n", "void reset_stats(Flag keep_total) {\n  dbx_reset_stats();\n", fname="statistics.c")
    s = sub(s, '#include "statistics.h"\n', '#include "statistics.h"\n\n#include "libs/dbx.h"\n', fname="statistics.c")
    out[st] = s

    # ---- pin/pin_lib/x86_decoder.cc: opcodes Scarab 79dadf3 leaves unmapped (OP_INV ->
    # uop_generator.c:719 assert). Found in these traces: PACKUSDW (SSE4.1; conda python3.14)
    # and SHA256RNDS2/MSG1/MSG2 (SHA-NI; hashlib in python3.12). PACKUSDW maps like its legacy
    # sibling PACKSSDW; SHA-NI like AESENC (the other crypto extension); SHA-1 ops added
    # pre-emptively (git hashes with SHA-1). Units without these opcodes decode identically.
    dx = src / "pin/pin_lib/x86_decoder.cc"
    s = dx.read_text()
    s = sub(s, "  iclass_to_scarab_map[XED_ICLASS_AESENC]   = {OP_PIPELINED_MEDIUM, -1, -1, NONE};\n",
            "  iclass_to_scarab_map[XED_ICLASS_AESENC]   = {OP_PIPELINED_MEDIUM, -1, -1, NONE};\n"
            "  iclass_to_scarab_map[XED_ICLASS_PACKUSDW] = {OP_MOV, -1, -1, NONE};  // dbx: was unmapped\n"
            + "".join(f"  iclass_to_scarab_map[XED_ICLASS_{op}] = {{OP_PIPELINED_MEDIUM, -1, -1, NONE}};  // dbx: was unmapped\n"
                      for op in ["SHA1MSG1", "SHA1MSG2", "SHA1NEXTE", "SHA1RNDS4", "SHA256MSG1", "SHA256MSG2",
                                 "SHA256RNDS2"]), fname="x86_decoder.cc")
    out[dx] = s

    # ---- sim.c: --full_warmup does not call reset_stats(); it dumps *.warmup stats and
    # the periodic column restarts there. Reset dbx accounting at the same point.
    sm = src / "sim.c"
    s = sm.read_text()
    s = sub(s, """    reset_h2p_stats();
    period_last_cycle_count = cycle_count;
  }""", """    reset_h2p_stats();
    dbx_reset_stats();
    period_last_cycle_count = cycle_count;
  }""", fname="sim.c")
    s = sub(s, '#include "sim.h"\n', '#include "sim.h"\n\n#include "libs/dbx.h"\n', fname="sim.c")
    out[sm] = s
    for f, t in out.items():
        f.write_text(t)
    print("patched", src)


main()
