#ifndef CRC16_H
#define CRC16_H

#include <stdint.h>

/* CRC16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, xorout 0x0000.
   Reference check (Docs/20_Protocol §5.1): crc16_ccitt("123456789", 9) == 0x29B1. */

uint16_t crc16_ccitt(const uint8_t *data, uint16_t len);
uint16_t crc16_ccitt_update(uint16_t crc, const uint8_t *data, uint16_t len);

#endif /* CRC16_H */
