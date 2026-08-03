#ifndef SHELL_H
#define SHELL_H

#include <stdint.h>

/* SLP v1 ASCII command parser (host -> device direction, protocol §3).
   Platform-independent (rule C-05): byte-in, command-out; the platform decides
   how to react and builds response frames via framer. */

#define SLP_SHELL_LINE_MAX 32u

typedef enum
{
  SLP_CMD_NONE = 0, /* no complete command yet          */
  SLP_CMD_PING,
  SLP_CMD_INFO,     /* "INFO?"                          */
  SLP_CMD_STAT,     /* "STAT?"                          */
  SLP_CMD_START,
  SLP_CMD_STOP,
  SLP_CMD_UNKNOWN   /* complete line, но не распознана  */
} slp_cmd_t;

typedef struct
{
  char    line[SLP_SHELL_LINE_MAX];
  uint8_t len;
} slp_shell_t;

void slp_shell_reset(slp_shell_t *s);

/* Feed one received byte. Returns a command once a full '\n'-terminated line
   is assembled ('\r' is ignored, overlong lines are dropped silently). */
slp_cmd_t slp_shell_feed(slp_shell_t *s, uint8_t byte);

#endif /* SHELL_H */
