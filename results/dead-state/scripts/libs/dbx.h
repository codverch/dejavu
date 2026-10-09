/***************************************************************************************
 * File         : libs/dbx.h
 * Description  : Dead-block study layer for cache_lib: dead-state accounting for every
 *                cache, and alternative replacement policies for ONE target cache:
 *                  DBX_POLICY 0  stock replacement (TRUE_LRU); optional touch log (pass 1)
 *                  DBX_POLICY 1  Mockingjay (Shah, Jain, Lin, HPCA 2022), ported from the
 *                                authors' CRC2 code (github.com/ishanashah/Mockingjay)
 *                  DBX_POLICY 2  oracle dead-block eviction: replays a pass-1 LRU log;
 *                                a block is marked dead after the touch that was its last
 *                                before eviction in pass 1, and dead blocks are evicted
 *                                first (LRU among them), else LRU
 *                  DBX_POLICY 3  Belady MIN from the same log (furthest next touch),
 *                                with bypass of fills whose next touch is furthest
 *                  DBX_POLICY 4  oracle with policy-independent labels: dead = never
 *                                touched again in the trace
 *                --dbx_oracle_bypass: policies 2/4 also bypass dead-on-arrival fills. With
 *                pass-1 LRU labels, policy 2 without bypass reproduces LRU exactly: the LRU
 *                victim is by definition dead in pass 1, so dead-first picks it every time.
 *                Pass-1/pass-2 records are keyed by (line address, per-line touch
 *                ordinal) so timing differences between passes cannot misalign them.
 ***************************************************************************************/

#ifndef __DBX_H__
#define __DBX_H__

#include "globals/global_types.h"

#ifdef __cplusplus
extern "C" {
#endif

struct Cache_struct;
struct Cache_Entry_struct;

typedef enum Dbx_Req_Type_enum {
  DBX_DEMAND = 0,
  DBX_PREFETCH = 1,
  DBX_WRITEBACK = 2,
} Dbx_Req_Type;

/* memory.c: describe the request about to access / fill the target cache */
void dbx_set_ctx(struct Cache_struct* cache, Addr pc, Dbx_Req_Type type, uns sub);
/* memory.c fill path: TRUE if the policy bypasses this fill (the touch is accounted) */
Flag dbx_fill_bypass(struct Cache_struct* cache, Addr addr);

/* cache_lib.c hooks */
void dbx_register(struct Cache_struct* cache);
void dbx_on_hit(struct Cache_struct* cache, uns set, uns way, struct Cache_Entry_struct* line);
void dbx_on_evict(struct Cache_struct* cache, uns set, uns way, struct Cache_Entry_struct* line);
void dbx_on_fill(struct Cache_struct* cache, uns set, uns way, struct Cache_Entry_struct* line);
void dbx_on_invalidate(struct Cache_struct* cache, uns set, uns way, struct Cache_Entry_struct* line);
/* returns NULL when the stock policy should choose */
struct Cache_Entry_struct* dbx_find_victim(struct Cache_struct* cache, uns set, uns* way);

/* statistics.c: stats were reset at the end of warmup */
void dbx_reset_stats(void);

#ifdef __cplusplus
}
#endif

#endif /* __DBX_H__ */
