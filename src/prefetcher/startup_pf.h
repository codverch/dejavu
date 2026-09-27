#ifndef __STARTUP_PF_H__
#define __STARTUP_PF_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Ideal creation-time prefetching of a process's start-up footprint (startup_pf.c). */
void spf_on_inst(uint64_t pc, uint8_t size, uint8_t num_ld, const uint64_t* ld, uint8_t num_st, const uint64_t* st);
void spf_tick(void);
/* spf_mode 3: 1 if an L1-D (inst = 0) or L1-I (inst = 1) miss to addr is made to hit. Only on-path
   misses are counted. */
int spf_ideal_hit(uint64_t addr, int inst, int off_path);

/* In memory.c: install one line in the L2 (level 2) or the LLC (level 3) with no timing. */
int spf_install_line(uint64_t addr, int level);

#ifdef __cplusplus
}
#endif

#endif
