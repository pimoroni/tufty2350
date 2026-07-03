// Embedded port shim: route fatlfs's malloc/free/calloc/realloc to the fixed
// PSRAM arena instead of libc malloc. Enabled with -DFATLFS_ARENA_ALLOC.
#ifndef FATLFS_PORT_H
#define FATLFS_PORT_H
#ifdef FATLFS_ARENA_ALLOC
#include "fatlfs_arena.h"
#define malloc(n)    fatlfs_arena_malloc(n)
#define free(p)      fatlfs_arena_free(p)
#define calloc(n,s)  fatlfs_arena_calloc((n),(s))
#define realloc(p,n) fatlfs_arena_realloc((p),(n))
#endif
#endif
