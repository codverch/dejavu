/***************************************************************************************
 * File         : libs/dbx.c
 * Description  : Dead-block study layer for cache_lib. See libs/dbx.h.
 *
 * Dead-state accounting (every cache): a block is live from its fill to its last
 * touch (a lookup that updates replacement state) and dead from then until it leaves
 * the cache (Lai et al. ISCA'01, Liu et al. MICRO'08, Khan et al. MICRO'10 all define
 * deadness against the eviction the simulated cache actually made). Time is sim_time,
 * the base TRUE_LRU already stamps into last_access_time.
 *
 * Policies apply to the one cache named by --dbx_cache; that cache must be configured
 * TRUE_LRU so last_access_time is maintained for the LRU fallbacks.
 ***************************************************************************************/

#include "libs/dbx.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "globals/assert.h"
#include "globals/global_defs.h"
#include "globals/global_types.h"
#include "globals/global_vars.h"
#include "globals/utils.h"

#include "memory/memory.param.h"

#include "libs/cache_lib.h"

#define DBX_MAX_CACHES 64
#define DBX_INF_NEXT (~0ULL)

typedef enum {
  DBX_POL_LRU = 0,
  DBX_POL_MOCKINGJAY = 1,
  DBX_POL_ORACLE = 2,    /* dead = last touch before eviction in the pass-1 LRU run */
  DBX_POL_MIN = 3,
  DBX_POL_NEVER = 4,     /* dead = never touched again in the trace (policy-independent) */
} Dbx_Policy;
typedef enum { DBX_EV_HIT = 0, DBX_EV_FILL = 1, DBX_EV_BYPASS = 2, DBX_EV_EVICT = 3, DBX_EV_INVAL = 4 } Dbx_Event;

/* pass-1 log record and pass-2 table record (written/read with fwrite/fread) */
typedef struct {
  uns64 blk; /* line address >> line-size bits */
  uns32 k;   /* touch ordinal of this block (0-based); for evict/inval: its last touch */
  uns32 ev;  /* Dbx_Event */
} Dbx_Log_Rec;

typedef struct {
  uns64 blk;
  uns32 k;
  uns32 dead; /* 1: this touch was the block's last before it left the cache in pass 1 */
  uns64 next; /* pass-1 global touch index of this block's next touch, or DBX_INF_NEXT */
} Dbx_Tab_Rec;

/**************************************************************************************/
/* per-cache dead-state accounting */

typedef struct {
  Cache* cache;
  Counter fills, hits, evictions, invalidations, zero_reuse;
  Counter resident_time, live_time, dead_time;
  Counter hist[8];
  uns8* set_used;
} Dbx_Acct;

static Dbx_Acct dbx_acct[DBX_MAX_CACHES];
static uns dbx_num_acct = 0;
static Flag dbx_atexit_done = FALSE;

static Dbx_Acct* acct_of(Cache* cache) {
  uns ii;
  for (ii = 0; ii < dbx_num_acct; ii++)
    if (dbx_acct[ii].cache == cache)
      return &dbx_acct[ii];
  return NULL;
}

static void hist_add(Counter* hist, Counter reuse) {
  uns b = reuse <= 3 ? (uns)reuse : reuse < 8 ? 4 : reuse < 16 ? 5 : reuse < 64 ? 6 : 7;
  hist[b]++;
}

static void split_time(Cache_Entry* line, Counter* resident, Counter* live) {
  Counter r = sim_time > line->insertion_time ? sim_time - line->insertion_time : 0;
  Counter l = line->last_access_time > line->insertion_time ? line->last_access_time - line->insertion_time : 0;
  *resident = r;
  *live = l > r ? r : l;
}

static void acct_removal(Dbx_Acct* a, Cache_Entry* line, Flag evict) {
  Counter r, l;
  if (!a || !line->valid)
    return;
  split_time(line, &r, &l);
  if (evict)
    a->evictions++;
  else
    a->invalidations++;
  a->resident_time += r;
  a->live_time += l;
  a->dead_time += r - l;
  if (line->db_reuse == 0)
    a->zero_reuse++;
  hist_add(a->hist, line->db_reuse);
}

/**************************************************************************************/
/* target-cache state */

static Cache* tgt = NULL;
static Dbx_Policy pol = DBX_POL_LRU;
static Addr ctx_pc = 0;
static Dbx_Req_Type ctx_type = DBX_DEMAND;
static Flag ctx_valid = FALSE;
static uns ctx_sub = 0;
static char* stat_path = NULL;
#define DBX_NSUB 32
static Counter st_sub_touch[DBX_NSUB], st_sub_pc0[DBX_NSUB];
static FILE* log_f = NULL;
static Counter touch_seq = 0;
static Counter st_touch[3], st_touch_pc0[3], st_hit_touch, st_fill_touch, st_bypass, st_ctx_missing;
static Counter st_lookup, st_unmatched, st_victim_dead, st_victim_lru;

static uns64 mix64(uns64 x) {
  x ^= x >> 33;
  x *= 0xff51afd7ed558ccdULL;
  x ^= x >> 33;
  x *= 0xc4ceb9fe1a85ec53ULL;
  x ^= x >> 33;
  return x;
}

/* block -> number of touches so far (open addressing; key stored +1, 0 = empty) */
static uns64* cnt_keys = NULL;
static uns32* cnt_vals = NULL;
static uns64 cnt_cap = 0, cnt_n = 0;

static void cnt_grow(void) {
  uns64 old_cap = cnt_cap, ii;
  uns64* ok = cnt_keys;
  uns32* ov = cnt_vals;
  cnt_cap = old_cap ? old_cap * 2 : (1ULL << 20);
  cnt_keys = (uns64*)calloc(cnt_cap, sizeof(uns64));
  cnt_vals = (uns32*)calloc(cnt_cap, sizeof(uns32));
  ASSERTM(0, cnt_keys && cnt_vals, "dbx: out of memory\n");
  for (ii = 0; ii < old_cap; ii++) {
    if (ok[ii]) {
      uns64 h = mix64(ok[ii]) & (cnt_cap - 1);
      while (cnt_keys[h])
        h = (h + 1) & (cnt_cap - 1);
      cnt_keys[h] = ok[ii];
      cnt_vals[h] = ov[ii];
    }
  }
  free(ok);
  free(ov);
}

static uns32* cnt_slot(uns64 blk) {
  uns64 key = blk + 1, h;
  if (2 * (cnt_n + 1) > cnt_cap)
    cnt_grow();
  h = mix64(key) & (cnt_cap - 1);
  while (cnt_keys[h] && cnt_keys[h] != key)
    h = (h + 1) & (cnt_cap - 1);
  if (!cnt_keys[h]) {
    cnt_keys[h] = key;
    cnt_vals[h] = 0;
    cnt_n++;
  }
  return &cnt_vals[h];
}

/* pass-2 table: (blk,k) -> record */
static Dbx_Tab_Rec* tab = NULL;
static uns64 tab_n = 0;
static uns64* tab_idx = NULL; /* index+1 into tab, 0 = empty */
static uns64 tab_cap = 0;

static uns64 tab_hash(uns64 blk, uns32 k) { return mix64(blk * 0x9e3779b97f4a7c15ULL ^ ((uns64)k << 1 | 1)); }

static void tab_load(const char* path) {
  FILE* f = fopen(path, "rb");
  uns64 ii;
  long sz;
  ASSERTM(0, f, "dbx: cannot open table %s\n", path);
  fseek(f, 0, SEEK_END);
  sz = ftell(f);
  fseek(f, 0, SEEK_SET);
  ASSERTM(0, sz % sizeof(Dbx_Tab_Rec) == 0, "dbx: table %s has a partial record\n", path);
  tab_n = sz / sizeof(Dbx_Tab_Rec);
  tab = (Dbx_Tab_Rec*)malloc(tab_n ? tab_n * sizeof(Dbx_Tab_Rec) : 1);
  ASSERTM(0, tab && fread(tab, sizeof(Dbx_Tab_Rec), tab_n, f) == tab_n, "dbx: short read on %s\n", path);
  fclose(f);
  tab_cap = 1;
  while (tab_cap < 2 * tab_n + 2)
    tab_cap <<= 1;
  tab_idx = (uns64*)calloc(tab_cap, sizeof(uns64));
  ASSERTM(0, tab_idx, "dbx: out of memory\n");
  for (ii = 0; ii < tab_n; ii++) {
    uns64 h = tab_hash(tab[ii].blk, tab[ii].k) & (tab_cap - 1);
    while (tab_idx[h])
      h = (h + 1) & (tab_cap - 1);
    tab_idx[h] = ii + 1;
  }
}

static Dbx_Tab_Rec* tab_find(uns64 blk, uns32 k) {
  uns64 h = tab_hash(blk, k) & (tab_cap - 1);
  st_lookup++;
  while (tab_idx[h]) {
    Dbx_Tab_Rec* r = &tab[tab_idx[h] - 1];
    if (r->blk == blk && r->k == k)
      return r;
    h = (h + 1) & (tab_cap - 1);
  }
  st_unmatched++;
  return NULL;
}

static void log_rec(uns64 blk, uns32 k, Dbx_Event ev) {
  Dbx_Log_Rec r;
  if (!log_f)
    return;
  r.blk = blk;
  r.k = k;
  r.ev = ev;
  fwrite(&r, sizeof(r), 1, log_f);
}

/**************************************************************************************/
/* Mockingjay. Faithful port of mockingjay.llc_repl (NUM_CPUS == 1 paths); constants
   derive from the target geometry exactly as the original derives them from
   LLC_SET/LLC_WAY. The RDP is keyed by an 11-bit signature, so the original's
   unordered_map is an array with a presence bit. */

static int MJ_LOG2_SET, MJ_LOG2_SIZE, MJ_LOG2_SAMPLED_SETS, MJ_WAYS;
static int MJ_INF_RD, MJ_INF_ETR, MJ_MAX_RD, MJ_SC_TAG_BITS, MJ_SIG_BITS;
#define MJ_HISTORY 8
#define MJ_GRANULARITY 8
#define MJ_SC_WAYS 5
#define MJ_LOG2_SC_SETS 4
#define MJ_TIMESTAMP_BITS 8
#define MJ_TEMP_DIFFERENCE (1.0 / 16.0)
#define MJ_FLEXMIN_PENALTY 2.0 /* 2 - log2(NUM_CPUS)/4 with NUM_CPUS == 1 */
#define MJ_LOG2_BLOCK 6

typedef struct {
  Flag valid;
  uns64 tag;
  uns64 signature;
  int timestamp;
} MJ_Sampled_Line;

static int* mj_etr_clock;
static char* mj_rdp_out = NULL; /* --dbx_mj_rdp_out, copied: string params are freed before exit */
static int* mj_cur_ts;
static int* mj_rdp;
static Flag* mj_rdp_has;
static MJ_Sampled_Line* mj_sc; /* [1 << (MJ_LOG2_SC_SETS + MJ_LOG2_SET)][MJ_SC_WAYS] */

static int iabs(int x) { return x < 0 ? -x : x; }

static Flag mj_is_sampled_set(int set) {
  int mask_length = MJ_LOG2_SET - MJ_LOG2_SAMPLED_SETS;
  int mask = (1 << mask_length) - 1;
  return (set & mask) == ((set >> (MJ_LOG2_SET - mask_length)) & mask);
}

static uns64 mj_crc_hash(uns64 block_address) {
  static const unsigned long long crc_polynomial = 3988292384ULL;
  unsigned long long v = block_address;
  uns ii;
  for (ii = 0; ii < 3; ii++)
    v = ((v & 1) == 1) ? ((v >> 1) ^ crc_polynomial) : (v >> 1);
  return v;
}

static uns64 mj_pc_signature(uns64 pc, Flag hit, Flag prefetch) {
  pc = pc << 1;
  if (hit)
    pc = pc | 1;
  pc = pc << 1;
  if (prefetch)
    pc = pc | 1;
  pc = mj_crc_hash(pc);
  pc = (pc << (64 - MJ_SIG_BITS)) >> (64 - MJ_SIG_BITS);
  return pc;
}

static uns32 mj_sc_index(uns64 full_addr) {
  int keep = MJ_LOG2_SC_SETS + MJ_LOG2_SET;
  full_addr = full_addr >> MJ_LOG2_BLOCK;
  full_addr = (full_addr << (64 - keep)) >> (64 - keep);
  return (uns32)full_addr;
}

static uns64 mj_sc_tag(uns64 x) {
  x >>= MJ_LOG2_SET + MJ_LOG2_BLOCK + MJ_LOG2_SC_SETS;
  x = (x << (64 - MJ_SC_TAG_BITS)) >> (64 - MJ_SC_TAG_BITS);
  return x;
}

static MJ_Sampled_Line* mj_sc_set(uns32 idx) { return &mj_sc[(uns64)idx * MJ_SC_WAYS]; }

static int mj_search_sc(uns64 tag, uns32 idx) {
  MJ_Sampled_Line* s = mj_sc_set(idx);
  int way;
  for (way = 0; way < MJ_SC_WAYS; way++)
    if (s[way].valid && s[way].tag == tag)
      return way;
  return -1;
}

static void mj_detrain(uns32 idx, int way) {
  MJ_Sampled_Line* t = &mj_sc_set(idx)[way];
  if (!t->valid)
    return;
  if (mj_rdp_has[t->signature])
    mj_rdp[t->signature] = MIN2(mj_rdp[t->signature] + 1, MJ_INF_RD);
  else {
    mj_rdp_has[t->signature] = TRUE;
    mj_rdp[t->signature] = MJ_INF_RD;
  }
  t->valid = FALSE;
}

static int mj_temporal_difference(int init, int sample) {
  if (sample > init) {
    int diff = sample - init;
    diff = diff * MJ_TEMP_DIFFERENCE; /* truncates, as in the original */
    diff = MIN2(1, diff);
    return MIN2(init + diff, MJ_INF_RD);
  } else if (sample < init) {
    int diff = init - sample;
    diff = diff * MJ_TEMP_DIFFERENCE;
    diff = MIN2(1, diff);
    return MAX2(init - diff, 0);
  }
  return init;
}

static int mj_increment_timestamp(int input) {
  input++;
  return input % (1 << MJ_TIMESTAMP_BITS);
}

static int mj_time_elapsed(int global, int local) {
  if (global >= local)
    return global - local;
  global = global + (1 << MJ_TIMESTAMP_BITS);
  return global - local;
}

static void mj_init(Cache* c) {
  uns ii, jj;
  ASSERTM(0, (c->num_sets & (c->num_sets - 1)) == 0, "dbx: Mockingjay needs a power-of-two set count (%s: %u)\n",
          c->name, c->num_sets);
  ASSERTM(0, (c->assoc & (c->assoc - 1)) == 0, "dbx: Mockingjay needs power-of-two ways\n");
  ASSERTM(0, c->line_size == (1 << MJ_LOG2_BLOCK), "dbx: Mockingjay port assumes 64 B lines\n");
  MJ_WAYS = c->assoc;
  MJ_LOG2_SET = LOG2(c->num_sets);
  MJ_LOG2_SIZE = MJ_LOG2_SET + LOG2(c->assoc) + MJ_LOG2_BLOCK;
  MJ_LOG2_SAMPLED_SETS = MJ_LOG2_SIZE - 16;
  MJ_INF_RD = MJ_WAYS * MJ_HISTORY - 1;
  MJ_INF_ETR = (MJ_WAYS * MJ_HISTORY / MJ_GRANULARITY) - 1;
  MJ_MAX_RD = MJ_INF_RD - 22;
  MJ_SC_TAG_BITS = 31 - MJ_LOG2_SIZE;
  MJ_SIG_BITS = MJ_LOG2_SIZE - 10;
  mj_etr_clock = (int*)calloc(c->num_sets, sizeof(int));
  mj_cur_ts = (int*)calloc(c->num_sets, sizeof(int));
  mj_rdp = (int*)calloc(1u << MJ_SIG_BITS, sizeof(int));
  mj_rdp_has = (Flag*)calloc(1u << MJ_SIG_BITS, sizeof(Flag));
  mj_sc = (MJ_Sampled_Line*)calloc((1ULL << (MJ_LOG2_SC_SETS + MJ_LOG2_SET)) * MJ_SC_WAYS, sizeof(MJ_Sampled_Line));
  ASSERTM(0, mj_etr_clock && mj_cur_ts && mj_rdp && mj_rdp_has && mj_sc, "dbx: out of memory\n");
  if (DBX_MJ_RDP_OUT)
    mj_rdp_out = strdup(DBX_MJ_RDP_OUT);
  if (DBX_MJ_RDP_IN) {
    /* sensitivity: start from a trained reuse-distance predictor (text: signature value) */
    FILE* f = fopen(DBX_MJ_RDP_IN, "r");
    unsigned sig;
    int val;
    ASSERTM(0, f, "dbx: cannot open %s\n", DBX_MJ_RDP_IN);
    while (fscanf(f, "%u %d", &sig, &val) == 2) {
      ASSERTM(0, sig < (1u << MJ_SIG_BITS), "dbx: bad signature in %s\n", DBX_MJ_RDP_IN);
      mj_rdp_has[sig] = TRUE;
      mj_rdp[sig] = val;
    }
    fclose(f);
  }
  for (ii = 0; ii < c->num_sets; ii++) {
    mj_etr_clock[ii] = MJ_GRANULARITY;
    mj_cur_ts[ii] = 0;
    for (jj = 0; jj < c->assoc; jj++)
      c->entries[ii][jj].dbx_etr = 0;
  }
}

/* llc_update_replacement_state; way == MJ_WAYS means the fill was bypassed */
static void mj_update(Cache* c, uns set, uns way, uns64 full_addr, uns64 pc, Dbx_Req_Type type, Flag hit) {
  int w;
  if (type == DBX_WRITEBACK) {
    if (!hit && way < (uns)MJ_WAYS)
      c->entries[set][way].dbx_etr = -MJ_INF_ETR;
    return;
  }

  pc = mj_pc_signature(pc, hit, type == DBX_PREFETCH);

  if (mj_is_sampled_set(set)) {
    uns32 sc_index = mj_sc_index(full_addr);
    uns64 sc_tag = mj_sc_tag(full_addr);
    MJ_Sampled_Line* s = mj_sc_set(sc_index);
    int sc_way = mj_search_sc(sc_tag, sc_index);
    int lru_way = -1, lru_rd = -1;

    if (sc_way > -1) {
      uns64 last_signature = s[sc_way].signature;
      int last_timestamp = s[sc_way].timestamp;
      int sample = mj_time_elapsed(mj_cur_ts[set], last_timestamp);
      if (sample <= MJ_INF_RD) {
        if (type == DBX_PREFETCH)
          sample = sample * MJ_FLEXMIN_PENALTY;
        if (mj_rdp_has[last_signature])
          mj_rdp[last_signature] = mj_temporal_difference(mj_rdp[last_signature], sample);
        else {
          mj_rdp_has[last_signature] = TRUE;
          mj_rdp[last_signature] = sample;
        }
        s[sc_way].valid = FALSE;
      }
    }

    for (w = 0; w < MJ_SC_WAYS; w++) {
      int sample;
      if (!s[w].valid) {
        lru_way = w;
        lru_rd = MJ_INF_RD + 1;
        continue;
      }
      sample = mj_time_elapsed(mj_cur_ts[set], s[w].timestamp);
      if (sample > MJ_INF_RD) {
        lru_way = w;
        lru_rd = MJ_INF_RD + 1;
        mj_detrain(sc_index, w);
      } else if (sample > lru_rd) {
        lru_way = w;
        lru_rd = sample;
      }
    }
    mj_detrain(sc_index, lru_way);

    for (w = 0; w < MJ_SC_WAYS; w++) {
      if (!s[w].valid) {
        s[w].valid = TRUE;
        s[w].signature = pc;
        s[w].tag = sc_tag;
        s[w].timestamp = mj_cur_ts[set];
        break;
      }
    }
    mj_cur_ts[set] = mj_increment_timestamp(mj_cur_ts[set]);
  }

  if (mj_etr_clock[set] == MJ_GRANULARITY) {
    for (w = 0; w < MJ_WAYS; w++) {
      if ((uns)w != way && iabs(c->entries[set][w].dbx_etr) < MJ_INF_ETR)
        c->entries[set][w].dbx_etr--;
    }
    mj_etr_clock[set] = 0;
  }
  mj_etr_clock[set]++;

  if (way < (uns)MJ_WAYS) {
    Cache_Entry* e = &c->entries[set][way];
    if (!mj_rdp_has[pc])
      e->dbx_etr = 0; /* NUM_CPUS == 1 */
    else if (mj_rdp[pc] > MJ_MAX_RD)
      e->dbx_etr = MJ_INF_ETR;
    else
      e->dbx_etr = mj_rdp[pc] / MJ_GRANULARITY;
  }
}

/* llc_find_victim without the bypass decision (see dbx_fill_bypass) */
static uns mj_victim(Cache* c, uns set, int* max_etr_out) {
  int max_etr = 0;
  uns victim_way = 0, way;
  for (way = 0; way < c->assoc; way++) {
    int e = c->entries[set][way].dbx_etr;
    if (iabs(e) > max_etr || (iabs(e) == max_etr && e < 0)) {
      max_etr = iabs(e);
      victim_way = way;
    }
  }
  if (max_etr_out)
    *max_etr_out = max_etr;
  return victim_way;
}

/**************************************************************************************/
/* touches of the target cache */

static uns64 blk_of(Cache* c, Addr line_addr) { return (uns64)(line_addr >> c->shift_bits); }

static Dbx_Req_Type take_ctx(Addr* pc) {
  Dbx_Req_Type t;
  if (!ctx_valid) {
    st_ctx_missing++;
    *pc = 0;
    return DBX_DEMAND;
  }
  t = ctx_type;
  *pc = ctx_pc;
  ctx_valid = FALSE;
  return t;
}

/* ordinal bookkeeping + log + pass-2 lookup for one touch of block blk */
static uns32 touch(uns64 blk, Dbx_Event ev, Dbx_Req_Type t, Addr pc, Dbx_Tab_Rec** rec) {
  uns32* slot = cnt_slot(blk);
  uns32 k = (*slot)++;
  log_rec(blk, k, ev);
  touch_seq++;
  st_touch[t]++;
  if (!pc)
    st_touch_pc0[t]++;
  if (ctx_sub < DBX_NSUB) {
    st_sub_touch[ctx_sub]++;
    if (!pc)
      st_sub_pc0[ctx_sub]++;
  }
  *rec = tab_idx ? tab_find(blk, k) : NULL;
  return k;
}

static void apply_rec(Cache_Entry* line, uns32 k, Dbx_Tab_Rec* rec) {
  line->dbx_k = k;
  line->dbx_dead = rec ? (pol == DBX_POL_NEVER ? rec->next == DBX_INF_NEXT : (Flag)rec->dead) : FALSE;
  line->dbx_next = rec ? rec->next : DBX_INF_NEXT;
}

/**************************************************************************************/
/* output */

static void dbx_dump(void) {
  const char* path = stat_path ? stat_path : "dbx.stat.out";
  FILE* f;
  uns ci, ii, jj;
  if (log_f) {
    fclose(log_f);
    log_f = NULL;
  }
  if (mj_rdp_out && mj_rdp) {
    FILE* rf = fopen(mj_rdp_out, "w");
    if (rf) {
      for (ii = 0; ii < (1u << MJ_SIG_BITS); ii++)
        if (mj_rdp_has[ii])
          fprintf(rf, "%u %d\n", ii, mj_rdp[ii]);
      fclose(rf);
    }
  }
  f = fopen(path, "w");
  if (!f)
    return;
  fprintf(f, "# dbx dead-block accounting; *_time in sim_time units\n");
  fprintf(f,
          "cache,num_sets,assoc,sets_used,fills,hits,evictions,invalidations,zero_reuse_removals,"
          "resident_time,live_time,dead_time,end_resident_blocks,end_zero_reuse_blocks,end_resident_time,"
          "end_live_time,reuse_0,reuse_1,reuse_2,reuse_3,reuse_4_7,reuse_8_15,reuse_16_63,reuse_64plus\n");
  for (ci = 0; ci < dbx_num_acct; ci++) {
    Dbx_Acct* a = &dbx_acct[ci];
    Cache* c = a->cache;
    Counter eb = 0, ez = 0, ert = 0, elt = 0, used = 0;
    for (ii = 0; ii < c->num_sets; ii++) {
      used += a->set_used[ii] ? 1 : 0;
      for (jj = 0; jj < c->assoc; jj++) {
        Cache_Entry* line = &c->entries[ii][jj];
        Counter r, l;
        if (!line->valid)
          continue;
        eb++;
        if (line->db_reuse == 0)
          ez++;
        split_time(line, &r, &l);
        ert += r;
        elt += l;
      }
    }
    fprintf(f, "%s,%u,%u,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu", c->name, c->num_sets,
            c->assoc, (unsigned long long)used, (unsigned long long)a->fills, (unsigned long long)a->hits,
            (unsigned long long)a->evictions, (unsigned long long)a->invalidations,
            (unsigned long long)a->zero_reuse, (unsigned long long)a->resident_time,
            (unsigned long long)a->live_time, (unsigned long long)a->dead_time, (unsigned long long)eb,
            (unsigned long long)ez, (unsigned long long)ert, (unsigned long long)elt);
    for (ii = 0; ii < 8; ii++)
      fprintf(f, ",%llu", (unsigned long long)a->hist[ii]);
    fprintf(f, "\n");
  }
  if (tgt) {
    fprintf(f, "# policy on %s\n", tgt->name);
    fprintf(f, "policy=%u\n", (uns)pol);
    fprintf(f, "touches=%llu\n", (unsigned long long)touch_seq);
    fprintf(f, "hit_touches=%llu\nfill_touches=%llu\nbypasses=%llu\n", (unsigned long long)st_hit_touch,
            (unsigned long long)st_fill_touch, (unsigned long long)st_bypass);
    fprintf(f, "touch_demand=%llu\ntouch_prefetch=%llu\ntouch_writeback=%llu\n", (unsigned long long)st_touch[0],
            (unsigned long long)st_touch[1], (unsigned long long)st_touch[2]);
    fprintf(f, "touch_pc0_demand=%llu\ntouch_pc0_prefetch=%llu\n", (unsigned long long)st_touch_pc0[0],
            (unsigned long long)st_touch_pc0[1]);
    fprintf(f, "ctx_missing=%llu\n", (unsigned long long)st_ctx_missing);
    for (ci = 0; ci < DBX_NSUB; ci++)
      if (st_sub_touch[ci])
        fprintf(f, "touch_reqtype_%u=%llu pc0=%llu\n", ci, (unsigned long long)st_sub_touch[ci],
                (unsigned long long)st_sub_pc0[ci]);
    fprintf(f, "table_records=%llu\nlookups=%llu\nunmatched=%llu\n", (unsigned long long)tab_n,
            (unsigned long long)st_lookup, (unsigned long long)st_unmatched);
    fprintf(f, "evict_marked_dead=%llu\nevict_not_marked_dead=%llu\n", (unsigned long long)st_victim_dead,
            (unsigned long long)st_victim_lru);
  }
  fclose(f);
}

/**************************************************************************************/
/* public */

void dbx_register(Cache* cache) {
  Dbx_Acct* a;
  uns ii, jj;
  if (!cache->entries || dbx_num_acct >= DBX_MAX_CACHES || acct_of(cache))
    return;
  a = &dbx_acct[dbx_num_acct++];
  memset(a, 0, sizeof(*a));
  a->cache = cache;
  a->set_used = (uns8*)calloc(cache->num_sets, 1);
  for (ii = 0; ii < cache->num_sets; ii++)
    for (jj = 0; jj < cache->assoc; jj++) {
      Cache_Entry* e = &cache->entries[ii][jj];
      e->db_reuse = 0;
      e->insertion_time = 0;
      e->dbx_k = 0;
      e->dbx_dead = FALSE;
      e->dbx_next = DBX_INF_NEXT;
      e->dbx_etr = 0;
    }
  if (!dbx_atexit_done) {
    stat_path = strdup(DBX_STAT_OUT ? DBX_STAT_OUT : "dbx.stat.out");
    atexit(dbx_dump);
    dbx_atexit_done = TRUE;
  }
  if (DBX_CACHE && !strcmp(cache->name, DBX_CACHE)) {
    ASSERTM(0, !tgt, "dbx: two caches named %s\n", DBX_CACHE);
    ASSERTM(0, cache->repl_policy == REPL_TRUE_LRU, "dbx: %s must be configured TRUE_LRU\n", cache->name);
    tgt = cache;
    pol = (Dbx_Policy)DBX_POLICY;
    ASSERTM(0, pol <= DBX_POL_NEVER, "dbx: unknown dbx_policy %u\n", DBX_POLICY);
    if (pol == DBX_POL_MOCKINGJAY)
      mj_init(cache);
    if (pol == DBX_POL_ORACLE || pol == DBX_POL_MIN || pol == DBX_POL_NEVER) {
      ASSERTM(0, DBX_TABLE_IN, "dbx: policy %u needs --dbx_table_in\n", DBX_POLICY);
      tab_load(DBX_TABLE_IN);
    }
    if (DBX_LOG_OUT) {
      log_f = fopen(DBX_LOG_OUT, "wb");
      ASSERTM(0, log_f, "dbx: cannot open log %s\n", DBX_LOG_OUT);
      setvbuf(log_f, NULL, _IOFBF, 1 << 22);
    }
  }
}

void dbx_set_ctx(Cache* cache, Addr pc, Dbx_Req_Type type, uns sub) {
  if (cache != tgt)
    return;
  ctx_sub = sub;
  ctx_pc = pc;
  ctx_type = type;
  ctx_valid = TRUE;
}

void dbx_on_hit(Cache* cache, uns set, uns way, Cache_Entry* line) {
  Dbx_Acct* a = acct_of(cache);
  line->db_reuse++;
  if (a)
    a->hits++;
  if (cache == tgt) {
    Addr pc;
    Dbx_Req_Type t = take_ctx(&pc);
    Dbx_Tab_Rec* rec;
    uns32 k = touch(blk_of(cache, line->base), DBX_EV_HIT, t, pc, &rec);
    st_hit_touch++;
    apply_rec(line, k, rec);
    if (pol == DBX_POL_MOCKINGJAY)
      mj_update(cache, set, way, line->base, pc, t, TRUE);
  }
}

void dbx_on_evict(Cache* cache, uns set, uns way, Cache_Entry* line) {
  if (!line->valid)
    return;
  acct_removal(acct_of(cache), line, TRUE);
  if (cache == tgt) {
    log_rec(blk_of(cache, line->base), line->dbx_k, DBX_EV_EVICT);
    if (line->dbx_dead)
      st_victim_dead++;
    else
      st_victim_lru++;
  }
}

void dbx_on_invalidate(Cache* cache, uns set, uns way, Cache_Entry* line) {
  if (!line->valid)
    return;
  acct_removal(acct_of(cache), line, FALSE);
  if (cache == tgt)
    log_rec(blk_of(cache, line->base), line->dbx_k, DBX_EV_INVAL);
}

void dbx_on_fill(Cache* cache, uns set, uns way, Cache_Entry* line) {
  Dbx_Acct* a = acct_of(cache);
  if (a) {
    a->fills++;
    a->set_used[set] = 1;
  }
  line->insertion_time = sim_time;
  line->db_reuse = 0;
  if (cache == tgt) {
    Addr pc;
    Dbx_Req_Type t = take_ctx(&pc);
    Dbx_Tab_Rec* rec;
    uns32 k = touch(blk_of(cache, line->base), DBX_EV_FILL, t, pc, &rec);
    st_fill_touch++;
    apply_rec(line, k, rec);
    if (pol == DBX_POL_MOCKINGJAY)
      mj_update(cache, set, way, line->base, pc, t, FALSE);
  }
}

Flag dbx_fill_bypass(Cache* cache, Addr addr) {
  Addr tag, line_addr;
  uns set, way;
  uns64 blk;
  if (cache != tgt || !ctx_valid || ctx_type == DBX_WRITEBACK)
    return FALSE; /* writebacks are never bypassed (dirty data has nowhere else to go) */
  if (pol != DBX_POL_MOCKINGJAY && !(pol == DBX_POL_MIN && DBX_MIN_BYPASS) &&
      !((pol == DBX_POL_ORACLE || pol == DBX_POL_NEVER) && DBX_ORACLE_BYPASS))
    return FALSE;
  set = ext_cache_index(cache, addr, &tag, &line_addr);
  for (way = 0; way < cache->assoc; way++)
    if (!cache->entries[set][way].valid)
      return FALSE; /* find_victim returns an invalid way before considering bypass */
  blk = blk_of(cache, line_addr);

  if (pol == DBX_POL_MOCKINGJAY) {
    int max_etr;
    uns64 sig = mj_pc_signature(ctx_pc, FALSE, ctx_type == DBX_PREFETCH);
    mj_victim(cache, set, &max_etr);
    if (!(mj_rdp_has[sig] && (mj_rdp[sig] > MJ_MAX_RD || mj_rdp[sig] / MJ_GRANULARITY > max_etr)))
      return FALSE;
  } else if (pol == DBX_POL_ORACLE || pol == DBX_POL_NEVER) {
    /* perfect dead-on-arrival prediction: the fill itself is the block's last touch */
    uns32* slot = cnt_slot(blk);
    Counter l0 = st_lookup, u0 = st_unmatched;
    Dbx_Tab_Rec* in = tab_find(blk, *slot);
    Flag doa = in && (pol == DBX_POL_NEVER ? in->next == DBX_INF_NEXT : in->dead);
    st_lookup = l0;
    st_unmatched = u0;
    if (!doa)
      return FALSE;
  } else {
    /* MIN with bypass: skip the fill if its next touch is further than every resident's */
    uns32* slot = cnt_slot(blk);
    Counter l0 = st_lookup, u0 = st_unmatched; /* a probe, not a touch: keep stats clean */
    Dbx_Tab_Rec* in = tab_find(blk, *slot);
    uns64 in_next = in ? in->next : DBX_INF_NEXT, max_next = 0;
    st_lookup = l0;
    st_unmatched = u0;
    for (way = 0; way < cache->assoc; way++)
      max_next = MAX2(max_next, cache->entries[set][way].dbx_next);
    /* ties (both never touched again) bypass: same misses as evicting the resident one,
       without the insertion */
    if (in_next < max_next)
      return FALSE;
  }

  /* bypassed: this is still a touch, and Mockingjay still trains/ages (way = WAYS) */
  {
    Addr pc;
    Dbx_Req_Type t = take_ctx(&pc);
    Dbx_Tab_Rec* rec;
    touch(blk, DBX_EV_BYPASS, t, pc, &rec);
    st_bypass++;
    if (pol == DBX_POL_MOCKINGJAY)
      mj_update(cache, set, cache->assoc, line_addr, pc, t, FALSE);
  }
  return TRUE;
}

Cache_Entry* dbx_find_victim(Cache* cache, uns set, uns* way) {
  uns ii, best = 0;
  Flag found = FALSE;
  Counter best_t = MAX_CTR;
  if (cache != tgt || pol == DBX_POL_LRU)
    return NULL;
  for (ii = 0; ii < cache->assoc; ii++) {
    if (!cache->entries[set][ii].valid) {
      *way = ii;
      return &cache->entries[set][ii];
    }
  }
  switch (pol) {
    case DBX_POL_MOCKINGJAY:
      best = mj_victim(cache, set, NULL);
      break;
    case DBX_POL_ORACLE:
    case DBX_POL_NEVER:
      for (ii = 0; ii < cache->assoc; ii++) {
        Cache_Entry* e = &cache->entries[set][ii];
        if (e->dbx_dead && e->last_access_time < best_t) {
          best_t = e->last_access_time;
          best = ii;
          found = TRUE;
        }
      }
      if (!found) {
        best_t = MAX_CTR;
        for (ii = 0; ii < cache->assoc; ii++) {
          Cache_Entry* e = &cache->entries[set][ii];
          if (e->last_access_time < best_t) {
            best_t = e->last_access_time;
            best = ii;
          }
        }
      }
      break;
    case DBX_POL_MIN: {
      uns64 far = 0;
      for (ii = 0; ii < cache->assoc; ii++) {
        Cache_Entry* e = &cache->entries[set][ii];
        if (!found || e->dbx_next > far || (e->dbx_next == far && e->last_access_time < best_t)) {
          far = e->dbx_next;
          best_t = e->last_access_time;
          best = ii;
          found = TRUE;
        }
      }
    } break;
    default:
      return NULL;
  }
  *way = best;
  return &cache->entries[set][best];
}

void dbx_reset_stats(void) {
  uns ci, ii, jj;
  for (ci = 0; ci < dbx_num_acct; ci++) {
    Dbx_Acct* a = &dbx_acct[ci];
    Cache* c = a->cache;
    a->fills = a->hits = a->evictions = a->invalidations = a->zero_reuse = 0;
    a->resident_time = a->live_time = a->dead_time = 0;
    memset(a->hist, 0, sizeof(a->hist));
    memset(a->set_used, 0, c->num_sets);
    for (ii = 0; ii < c->num_sets; ii++)
      for (jj = 0; jj < c->assoc; jj++) {
        Cache_Entry* e = &c->entries[ii][jj];
        if (!e->valid)
          continue;
        /* residency is measured from the reset: warmup-era time and hits do not count */
        e->insertion_time = sim_time;
        e->db_reuse = 0;
        a->set_used[ii] = 1;
      }
  }
}
