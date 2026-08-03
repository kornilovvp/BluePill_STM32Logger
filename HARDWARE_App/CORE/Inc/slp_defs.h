#ifndef SLP_DEFS_H
#define SLP_DEFS_H

#include <stdint.h>

/* Simple Logger Protocol v1.0 - constants shared by all boards and host tests.
   Single source of truth: Docs/20_Protocol/01_Protocol_SLP_v1.md.
   This header must stay free of any HAL/CMSIS includes (rule C-05). */

#define SLP_PROTO_MAJOR      1u
#define SLP_PROTO_MINOR      0u

#define SLP_SYNC0            0xAAu
#define SLP_SYNC1            0x55u

#define SLP_TYPE_DATA        0x01u
#define SLP_TYPE_RESP        0x02u
#define SLP_TYPE_STAT        0x03u
#define SLP_TYPE_ERR         0x7Fu

#define SLP_TICK_RATE_HZ     10000u
#define SLP_BLOCK_TICKS      32u

#define SLP_MAX_PAYLOAD      256u
#define SLP_HEADER_LEN       6u   /* sync(2) + type + seq + len(2) */
#define SLP_CRC_LEN          2u
#define SLP_FRAME_OVERHEAD   (SLP_HEADER_LEN + SLP_CRC_LEN)

#define SLP_DATA_PAYLOAD_LEN (4u + (SLP_BLOCK_TICKS * 4u))               /* 132 */
#define SLP_DATA_FRAME_LEN   (SLP_DATA_PAYLOAD_LEN + SLP_FRAME_OVERHEAD) /* 140 */

#define SLP_ADC_MASK         0x0FFFu
#define SLP_DIG_BIT          15u

#endif /* SLP_DEFS_H */
