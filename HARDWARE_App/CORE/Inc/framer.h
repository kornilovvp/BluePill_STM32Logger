#ifndef FRAMER_H
#define FRAMER_H

#include <stdint.h>
#include "slp_defs.h"

/* SLP v1 frame builder (device -> host direction).
   Platform-independent (rule C-05): no HAL, all data via parameters. */

typedef struct
{
  uint8_t seq; /* global frame counter, wraps 255 -> 0 (protocol §1) */
} slp_framer_t;

void slp_framer_reset(slp_framer_t *f);

/* Pack one tick into the two SLP data words (W0: A1/D1, W1: A2/D2), §2. */
static inline void slp_pack_tick(uint16_t a1, uint16_t a2, uint8_t d1, uint8_t d2,
                                 uint16_t *w0, uint16_t *w1)
{
  *w0 = (uint16_t)((a1 & SLP_ADC_MASK) | ((uint16_t)(d1 & 1u) << SLP_DIG_BIT));
  *w1 = (uint16_t)((a2 & SLP_ADC_MASK) | ((uint16_t)(d2 & 1u) << SLP_DIG_BIT));
}

/* Build a generic SLP frame around a ready payload (RESP/STAT/ERR/tests).
   dst capacity must be >= len + SLP_FRAME_OVERHEAD. Returns full frame length. */
uint16_t slp_build_frame(slp_framer_t *f, uint8_t *dst, uint8_t type,
                         const uint8_t *payload, uint16_t len);

/* Build a DATA frame straight from sampler buffers (no intermediate copy).
   adc:  SLP_BLOCK_TICKS*2 halfwords, interleaved [a1, a2] per tick;
   gpio: SLP_BLOCK_TICKS halfwords of raw port IDR snapshots;
   d1_bit/d2_bit: positions of D1/D2 inside the IDR word (board-specific!).
   dst capacity must be >= SLP_DATA_FRAME_LEN. Returns SLP_DATA_FRAME_LEN. */
uint16_t slp_build_data_frame(slp_framer_t *f, uint8_t *dst, uint32_t first_tick,
                              const uint16_t *adc, const uint16_t *gpio,
                              uint8_t d1_bit, uint8_t d2_bit);

#endif /* FRAMER_H */
