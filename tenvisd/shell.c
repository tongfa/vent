
#include "shell.h"

#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

#define SHELL_DATA_BUF_LEN (100)

unsigned int dbg_flags = 0xFFFF;
//unsigned int dbg_flags = 0x1;

unsigned int shellDebugFlags(void) {
  return dbg_flags;
}

void shellCmd_d(unsigned int int1) {
  dbg_flags = int1;
  printf("dbg_flags <- %d\n", int1);
}

extern void printq();
void shellCmd_q(void) {
  printq();
}

struct shell_data {
  char buf[SHELL_DATA_BUF_LEN]; // circular buffer
  unsigned char bufWritePos;
  unsigned char bufGetcPos;
  char cmd;
  bool skipToEol;
};

struct shell_data shellData = { {0}, 0, 0, 0, 0};

unsigned char shellGetc(struct shell_data* sd) {
  unsigned char c = sd->buf[sd->bufGetcPos++];
  sd->bufGetcPos %= SHELL_DATA_BUF_LEN;
  return c;
}

unsigned char shellPeekc(struct shell_data* sd) {
  return sd->buf[sd->bufGetcPos];
}

int shellGetEol(struct shell_data* sd) {
  unsigned char c = shellPeekc(sd);
  if (c == '\n') {
    shellGetc(sd);
    return 0;
  }
  return -1;
}

#define IS_WHITESPACE(c) (c == ' ' || c == '\t')
int shellGetWhitespace(struct shell_data* sd) {
  unsigned char c = shellPeekc(sd);
  if (! IS_WHITESPACE(c) ) return -1;
  while ( IS_WHITESPACE(c) ) {
    shellGetc(sd);
    c = shellPeekc(sd);
  }
  return 0;
}

#define IS_DIGIT(c) ( c >= 0x30 && c <= 0x39 )

int shellGetInteger(struct shell_data* sd, int* result) {
  unsigned char c = shellPeekc(sd);
  *result = 0;
  if (! IS_DIGIT(c) ) return -1;
  *result += c - 0x30;
  shellGetc(sd);
  c = shellPeekc(sd);
  while ( IS_DIGIT(c) ) {
    *result *= 10;
    *result += c - 0x30;
    shellGetc(sd);
    c = shellPeekc(sd);
  }
  return 0;
}

int shellGetUnsignedInteger(struct shell_data* sd, unsigned int* result) {
  return shellGetInteger(sd, (int*) result);
}


int shellParse(struct shell_data* sd) {
  unsigned int uint1;
  switch (shellGetc(sd)) {
  case 'd': {
    if ( shellGetWhitespace(sd) ) return -1;
    if ( shellGetUnsignedInteger(sd, &uint1) ) return -1;
    if ( shellGetEol(sd) ) return -1;
    shellCmd_d(uint1);
    break;
  }
  case 'q': {
    if ( shellGetEol(sd) ) return -1;
    shellCmd_q();
    break;
  }
  default:
    return -1;
  }
  return 0;
}

void shellRun(struct shell_data* sd) {
  unsigned int i;
  int count;

  int room = SHELL_DATA_BUF_LEN - sd->bufWritePos;
  if ( sd->bufWritePos < sd->bufGetcPos ) room -= SHELL_DATA_BUF_LEN - sd->bufGetcPos;
  count = read(0, sd->buf + sd->bufWritePos, room );
  if ( count < 0 ) {
    if (errno == EAGAIN || errno == EWOULDBLOCK) {
      return;
    }
  }

  if ( count == 0 ) { 
    printf("end of input\n");
    return;
  }

  sd->bufWritePos += count; 
  
  while (true) {
    for (i = 0; i < SHELL_DATA_BUF_LEN && i < sd->bufWritePos; i++) {
      if (sd->buf[i] == '\n') break;
    }
    if ( i == SHELL_DATA_BUF_LEN ) {
      // consume entire buffer, it overflowed
      sd->skipToEol = true;
      sd->bufWritePos = 0; 
      return;
    }
    if ( i == sd->bufWritePos) return; // need more data.
    
    if ( ! sd->skipToEol )
      if ( shellParse(sd) ) {
	printf("syntax error\n");
      }

    // flush the buffer one char past the '\n';
    {
      unsigned int j;
      for (j=0, i++; i < sd->bufWritePos; i++, j++) {
	sd->buf[j] = sd->buf[i];
      }
      sd->bufWritePos = j;
      sd->bufGetcPos = j;
    }

  }
}

void shell(void) {
  shellRun(&shellData);
}  

void shellInit(void) {
  /* we want non-blocking reads */
  int flags = fcntl(0, F_GETFL);
  flags |= O_NONBLOCK;	
  fcntl(0, F_SETFL, flags);
}


