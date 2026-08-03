/* Host-side golden-vector test for CORE (Docs/20_Protocol/01_Protocol_SLP_v1.md §5).
 *
 * Build:  gcc -std=c99 -Wall -Wextra -I ../Inc ../Src/crc16.c ../Src/framer.c test_core.c -o test_core
 * Run:    ./test_core        (exit code 0 = all pass)
 *
 * The same sources are compiled unmodified into the firmware - passing here
 * means the device produces byte-identical frames.
 */
#include <stdio.h>
#include <string.h>
#include "crc16.h"
#include "framer.h"

static int failures = 0;

static void check(const char *name, int cond)
{
  printf("%-44s %s\n", name, cond ? "PASS" : "FAIL");
  if (!cond)
  {
    failures++;
  }
}

int main(void)
{
  /* --- §5.1: CRC16-CCITT-FALSE reference value ------------------------------ */
  check("crc16(\"123456789\") == 0x29B1",
        crc16_ccitt((const uint8_t *)"123456789", 9u) == 0x29B1u);

  /* --- §5.2: short DATA test frame (2 ticks, LEN=0x0C) ---------------------- */
  static const uint8_t expected[20] = {
    0xAA, 0x55, 0x01, 0x00, 0x0C, 0x00,             /* sync, type, seq, len   */
    0x00, 0x00, 0x00, 0x00,                         /* first_tick = 0         */
    0x23, 0x81, 0x56, 0x04,                         /* tick0: A1=291 D1=1, A2=1110 D2=0 */
    0xFF, 0x07, 0xFF, 0x8F,                         /* tick1: A1=2047 D1=0, A2=4095 D2=1 */
    0xBD, 0xAD                                      /* CRC16 = 0xADBD, LE     */
  };
  uint8_t payload[12];
  uint8_t frame[32];
  uint16_t w0;
  uint16_t w1;
  uint16_t n;
  slp_framer_t fr;

  slp_framer_reset(&fr);

  payload[0] = 0u; payload[1] = 0u; payload[2] = 0u; payload[3] = 0u;

  slp_pack_tick(0x123u, 0x456u, 1u, 0u, &w0, &w1);
  check("pack_tick(0x123,D1=1) -> W0 == 0x8123", w0 == 0x8123u);
  check("pack_tick(0x456,D2=0) -> W1 == 0x0456", w1 == 0x0456u);
  payload[4] = (uint8_t)(w0 & 0xFFu); payload[5] = (uint8_t)(w0 >> 8);
  payload[6] = (uint8_t)(w1 & 0xFFu); payload[7] = (uint8_t)(w1 >> 8);

  slp_pack_tick(0x7FFu, 0xFFFu, 0u, 1u, &w0, &w1);
  payload[8]  = (uint8_t)(w0 & 0xFFu); payload[9]  = (uint8_t)(w0 >> 8);
  payload[10] = (uint8_t)(w1 & 0xFFu); payload[11] = (uint8_t)(w1 >> 8);

  n = slp_build_frame(&fr, frame, SLP_TYPE_DATA, payload, 12u);
  check("test frame length == 20", n == 20u);
  check("test frame == golden vector (byte-exact)", memcmp(frame, expected, 20u) == 0);
  check("framer seq incremented to 1", fr.seq == 1u);

  /* --- sanity: full-size DATA frame length constant ------------------------- */
  check("SLP_DATA_FRAME_LEN == 140", SLP_DATA_FRAME_LEN == 140u);

  printf("%s\n", failures ? "*** FAILURES ***" : "ALL PASS");
  return failures ? 1 : 0;
}
