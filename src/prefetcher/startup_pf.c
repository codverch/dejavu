/* Ideal creation-time prefetching.

   A new process spends its first millions of instructions building the same state every time
   it starts (dynamic linking, interpreter start-up), so it touches nearly the same cache lines
   in the same order on every run. This prefetcher is told that order in advance. It runs in two
   passes over one trace:

   record (spf_mode 1): every distinct 64-B line that the first spf_region_instrs instructions
     touch, instruction fetches and data accesses alike, is written to spf_file in the order the
     program first touches it, together with the index of that instruction.

   replay (spf_mode 2): the lines in spf_file are prefetched as the process runs.
     spf_timing 0 (instant): before the first cycle, lines are installed in the destination
       cache soonest-needed first, until each set is full; nothing installed is evicted. No
       bandwidth is charged. This bounds a prefetch issued well before the process starts (while
       the harness waits on the model): capacity limits it, timing does not.
     spf_timing 1 (stream): a line enters the destination's normal prefetch request queue once
       the frontend is within spf_lookahead instructions of the line's first use, at most
       spf_issue_width lines per cycle. A full queue stalls the stream; nothing is overwritten.
       Queueing, MSHRs and memory bandwidth are those of any other prefetch.
     spf_dest: 1 = L1 (data lines through the L1-D queue; instruction lines through the L2 queue,
       the only queue that serves them), 2 = L2, 3 = LLC, 4 = L2 and LLC (instant only: each
       level is filled independently, soonest-needed first). Instant mode supports 2, 3 and 4.
       Streaming into L1 stops the core on our traces: the forward-progress watchdog in
       decoupled_frontend.cc fires at the same instruction for issue widths 1 and 4. The study
       uses 2 and 3.

   Every prefetch is issued as prefetcher id 0, the "ILLEGAL" entry of pref_table. memory.c does no
   per-prefetcher accounting for id 0, so the feedback-directed throttling of golden_cove's stream
   prefetcher (pref_throttlefb_on) sees none of these prefetches and behaves as in the baseline.

   Replaying the record of the same trace is an oracle: it knows the future exactly. Replaying
   another invocation's record, rebased for ASLR outside the simulator, is the realistic case. */

#include "prefetcher/startup_pf.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "globals/assert.h"
#include "globals/global_defs.h"
#include "globals/global_types.h"
#include "globals/global_vars.h"
#include "globals/utils.h"

#include "general.param.h"
#include "memory/memory.param.h"
#include "prefetcher/pref.param.h"

#include "prefetcher/pref_common.h"

extern HWP_Common pref;

typedef struct {
  uint64_t line; /* line address; bit 0 = instruction line, bit 1 = written */
  uint64_t idx;  /* index of the first instruction that touches it */
} Spf_Rec;

static int spf_state = -1; /* -1 not initialised, 0 off, 1 on */
static char* spf_path;
static uint64_t n_inst;

/* record */
static uint64_t *seen_k, seen_mask, seen_n;
static Spf_Rec* recs;
static uint64_t n_recs, cap_recs;

/* replay */
static uint64_t next_rec, sent, late, stalls, installed, not_installed, set_full;
static int installed_done;

static uint64_t mix(uint64_t x) {
  x ^= x >> 33;
  x *= 0xff51afd7ed558ccdULL;
  x ^= x >> 33;
  return x;
}

/* returns the slot of line in the seen-set; *fresh = 1 if it was not there */
static uint64_t* seen_slot(uint64_t line, int* fresh) {
  uint64_t k = line + 1, i = mix(k) & seen_mask;
  while (seen_k[i] && seen_k[i] != k)
    i = (i + 1) & seen_mask;
  *fresh = !seen_k[i];
  if (*fresh) {
    ASSERTM(0, ++seen_n < seen_mask / 10 * 7, "spf: seen-set full\n");
    seen_k[i] = k;
  }
  return &seen_k[i];
}

static void rec_line(uint64_t addr, uint64_t flags) {
  int fresh;
  uint64_t line = addr & ~63ULL;
  seen_slot(line, &fresh);
  if (!fresh)
    return;
  if (n_recs == cap_recs) {
    cap_recs = cap_recs ? 2 * cap_recs : 1 << 16;
    recs = (Spf_Rec*)realloc(recs, cap_recs * sizeof(Spf_Rec));
  }
  recs[n_recs].line = line | flags;
  recs[n_recs].idx = n_inst;
  n_recs++;
}

static void spf_exit(void) {
  if (SPF_MODE == 1) {
    FILE* f = fopen(spf_path, "wb");
    ASSERTM(0, f, "spf: cannot write %s\n", spf_path);
    ASSERTM(0, fwrite(recs, sizeof(Spf_Rec), n_recs, f) == n_recs, "spf: short write\n");
    fclose(f);
    printf("SPF record: lines=%lu instructions=%lu file=%s\n", (unsigned long)n_recs, (unsigned long)n_inst, spf_path);
  } else {
    printf("SPF replay: dest=%u timing=%u lookahead=%u width=%u records=%lu sent=%lu late_skipped=%lu queue_stalls=%lu "
           "installed=%lu already_present=%lu set_full=%lu instructions=%lu\n",
           SPF_DEST, SPF_TIMING, SPF_LOOKAHEAD, SPF_ISSUE_WIDTH, (unsigned long)n_recs, (unsigned long)sent,
           (unsigned long)late, (unsigned long)stalls, (unsigned long)installed, (unsigned long)not_installed,
           (unsigned long)set_full, (unsigned long)n_inst);
  }
  fflush(stdout);
}

static void spf_init(void) {
  spf_state = SPF_MODE ? 1 : 0;
  if (!spf_state)
    return;
  ASSERTM(0, SPF_MODE == 1 || SPF_MODE == 2, "spf: spf_mode must be 0, 1 or 2\n");
  ASSERTM(0, MEMTRACE_REPEAT <= 1, "spf: use with --memtrace_repeat 1\n");
  ASSERTM(0, SPF_FILE && SPF_FILE[0], "spf: spf_file is required\n");
  spf_path = strdup(SPF_FILE); /* parameter strings are freed before exit handlers run */
  if (SPF_MODE == 1) {
    seen_mask = (1ULL << 24) - 1;
    seen_k = (uint64_t*)calloc(seen_mask + 1, sizeof(uint64_t));
  } else {
    ASSERTM(0, SPF_DEST >= 1 && SPF_DEST <= 4, "spf: spf_dest must be 1, 2, 3 or 4\n");
    ASSERTM(0, SPF_TIMING == 1 || SPF_DEST >= 2, "spf: instant replay installs into L2 or LLC only\n");
    ASSERTM(0, SPF_TIMING == 0 || SPF_DEST <= 3, "spf: spf_dest 4 is for instant replay only\n");
    ASSERTM(0, SPF_TIMING == 0 || PREF_FRAMEWORK_ON, "spf: stream replay needs --pref_framework_on 1\n");
    FILE* f = fopen(spf_path, "rb");
    ASSERTM(0, f, "spf: cannot read %s\n", spf_path);
    fseek(f, 0, SEEK_END);
    n_recs = ftell(f) / sizeof(Spf_Rec);
    fseek(f, 0, SEEK_SET);
    recs = (Spf_Rec*)malloc((n_recs + 1) * sizeof(Spf_Rec));
    ASSERTM(0, fread(recs, sizeof(Spf_Rec), n_recs, f) == n_recs, "spf: short read\n");
    fclose(f);
    for (uint64_t i = 1; i < n_recs; i++)
      ASSERTM(0, recs[i].idx >= recs[i - 1].idx, "spf: records out of first-touch order\n");
  }
  atexit(spf_exit);
}

void spf_on_inst(uint64_t pc, uint8_t size, uint8_t num_ld, const uint64_t* ld, uint8_t num_st, const uint64_t* st) {
  if (spf_state < 0)
    spf_init();
  if (!spf_state)
    return;
  if (SPF_MODE == 1 && (!SPF_REGION_INSTRS || n_inst < SPF_REGION_INSTRS)) {
    rec_line(pc, 1);
    if (size && ((pc + size - 1) >> 6) != (pc >> 6))
      rec_line(pc + size - 1, 1);
    for (int i = 0; i < num_ld; i++)
      rec_line(ld[i], 0);
    for (int i = 0; i < num_st; i++)
      rec_line(st[i], 2);
  }
  n_inst++;
}

static int queue_full(HWP_Core* c, int q) {
  if (q == 1)
    return c->dl0req_queue[(c->dl0req_queue_req_pos + 1) % PREF_DL0REQ_QUEUE_SIZE].valid;
  if (q == 2)
    return c->umlc_req_queue[(c->umlc_req_queue_req_pos + 1) % PREF_UMLC_REQ_QUEUE_SIZE].valid;
  return c->ul1req_queue[(c->ul1req_queue_req_pos + 1) % PREF_UL1REQ_QUEUE_SIZE].valid;
}

void spf_tick(void) {
  if (spf_state < 0)
    spf_init();
  if (!spf_state || SPF_MODE != 2)
    return;
  if (SPF_TIMING == 0) {
    if (!installed_done) {
      for (int lvl = 2; lvl <= 3; lvl++) {
        if (SPF_DEST != 4 && SPF_DEST != (uns)lvl)
          continue;
        for (uint64_t i = 0; i < n_recs; i++) {
          int r = spf_install_line(recs[i].line & ~63ULL, lvl);
          if (r > 0)
            installed++;
          else if (r == 0)
            not_installed++;
          else
            set_full++;
        }
      }
      installed_done = 1;
    }
    return;
  }
  HWP_Core* c = pref.cores[0];
  for (uns budget = SPF_ISSUE_WIDTH; budget > 0 && next_rec < n_recs;) {
    Spf_Rec* r = &recs[next_rec];
    if (r->idx < n_inst) { /* its first use has already been fetched: too late to help */
      late++;
      next_rec++;
      continue;
    }
    if (r->idx >= n_inst + SPF_LOOKAHEAD)
      break;
    int q = (SPF_DEST == 1 && (r->line & 1)) ? 2 : (int)SPF_DEST;
    if (queue_full(c, q)) {
      stalls++;
      break;
    }
    Addr li = (r->line & ~63ULL) >> 6;
    if (q == 1)
      pref_addto_dl0req_queue(0, li, 0);
    else if (q == 2)
      pref_addto_umlc_req_queue(0, li, 0);
    else
      pref_addto_ul1req_queue(0, li, 0);
    sent++;
    next_rec++;
    budget--;
  }
}
