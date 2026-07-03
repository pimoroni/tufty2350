// fatlfs_arena: a fixed-arena general allocator (malloc/free/calloc/realloc) so
// fatlfs can run on embedded targets without libc malloc (SRAM-limited on RP2).
// Point it at one big PSRAM buffer once; all fatlfs allocation lives inside it.
#ifndef FATLFS_ARENA_H
#define FATLFS_ARENA_H
#include <stddef.h>

// Initialise the arena over [base, base+size). Call once before any alloc.
void fatlfs_arena_init(void *base, size_t size);

void *fatlfs_arena_malloc(size_t n);
void  fatlfs_arena_free(void *p);
void *fatlfs_arena_calloc(size_t n, size_t sz);
void *fatlfs_arena_realloc(void *p, size_t n);

// Diagnostics (bytes currently handed out, and peak).
size_t fatlfs_arena_used(void);
size_t fatlfs_arena_peak(void);

#endif
