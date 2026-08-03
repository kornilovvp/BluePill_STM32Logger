#include "framer.h"
#include "crc16.h"

void slp_framer_reset(slp_framer_t *f)
{
  f->seq = 0u;
}

static void write_header(slp_framer_t *f, uint8_t *dst, uint8_t type, uint16_t len)
{
  dst[0] = SLP_SYNC0;
  dst[1] = SLP_SYNC1;
  dst[2] = type;
  dst[3] = f->seq++;
  dst[4] = (uint8_t)(len & 0xFFu);
  dst[5] = (uint8_t)(len >> 8);
}

/* CRC over TYPE..PAYLOAD (protocol §1), appended little-endian. */
static uint16_t finish_frame(uint8_t *dst, uint16_t payload_len)
{
  uint16_t crc = crc16_ccitt(&dst[2], (uint16_t)(4u + payload_len));
  uint16_t pos = (uint16_t)(SLP_HEADER_LEN + payload_len);

  dst[pos]      = (uint8_t)(crc & 0xFFu);
  dst[pos + 1u] = (uint8_t)(crc >> 8);
  return (uint16_t)(pos + SLP_CRC_LEN);
}

uint16_t slp_build_frame(slp_framer_t *f, uint8_t *dst, uint8_t type,
                         const uint8_t *payload, uint16_t len)
{
  write_header(f, dst, type, len);
  for (uint16_t i = 0u; i < len; i++)
  {
    dst[SLP_HEADER_LEN + i] = payload[i];
  }
  return finish_frame(dst, len);
}

uint16_t slp_build_data_frame(slp_framer_t *f, uint8_t *dst, uint32_t first_tick,
                              const uint16_t *adc, const uint16_t *gpio,
                              uint8_t d1_bit, uint8_t d2_bit)
{
  uint8_t *p = &dst[SLP_HEADER_LEN];

  write_header(f, dst, SLP_TYPE_DATA, SLP_DATA_PAYLOAD_LEN);

  *p++ = (uint8_t)(first_tick & 0xFFu);
  *p++ = (uint8_t)((first_tick >> 8) & 0xFFu);
  *p++ = (uint8_t)((first_tick >> 16) & 0xFFu);
  *p++ = (uint8_t)((first_tick >> 24) & 0xFFu);

  for (uint16_t i = 0u; i < SLP_BLOCK_TICKS; i++)
  {
    uint16_t w0;
    uint16_t w1;
    uint8_t d1 = (uint8_t)((gpio[i] >> d1_bit) & 1u);
    uint8_t d2 = (uint8_t)((gpio[i] >> d2_bit) & 1u);

    slp_pack_tick(adc[2u * i], adc[(2u * i) + 1u], d1, d2, &w0, &w1);
    *p++ = (uint8_t)(w0 & 0xFFu);
    *p++ = (uint8_t)(w0 >> 8);
    *p++ = (uint8_t)(w1 & 0xFFu);
    *p++ = (uint8_t)(w1 >> 8);
  }
  return finish_frame(dst, SLP_DATA_PAYLOAD_LEN);
}
