
#ifndef __shell_h__
#define __shell_h__

#include <stdio.h> 
#include <stdbool.h>

void shell(void);
void shellInit(void);
unsigned int shellDebugFlags(void);

#ifdef DEBUG_SHELL
#define logf(num, ...) do { if (shellDebugFlags() & 1 << num) printf(__VA_ARGS__ ); } while(0)
#else
#define logf(num, ...) 
#endif

#endif
