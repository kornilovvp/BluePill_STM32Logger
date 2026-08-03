#include "shell.h"

#include <string.h>

void slp_shell_reset(slp_shell_t *s)
{
  s->len = 0u;
}

slp_cmd_t slp_shell_feed(slp_shell_t *s, uint8_t byte)
{
  if (byte == (uint8_t)'\r')
  {
    return SLP_CMD_NONE;
  }

  if (byte != (uint8_t)'\n')
  {
    if (s->len < (SLP_SHELL_LINE_MAX - 1u))
    {
      s->line[s->len++] = (char)byte;
    }
    else
    {
      s->len = 0u; /* overflow: drop the whole line */
    }
    return SLP_CMD_NONE;
  }

  /* full line assembled */
  s->line[s->len] = '\0';
  {
    uint8_t had = s->len;
    s->len = 0u;

    if (had == 0u)
    {
      return SLP_CMD_NONE; /* empty line - ignore */
    }
  }

  if (strcmp(s->line, "PING") == 0)  { return SLP_CMD_PING;  }
  if (strcmp(s->line, "INFO?") == 0) { return SLP_CMD_INFO;  }
  if (strcmp(s->line, "STAT?") == 0) { return SLP_CMD_STAT;  }
  if (strcmp(s->line, "START") == 0) { return SLP_CMD_START; }
  if (strcmp(s->line, "STOP") == 0)  { return SLP_CMD_STOP;  }

  return SLP_CMD_UNKNOWN;
}
