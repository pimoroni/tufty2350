// Fixed-arena allocator: implicit free list with boundary-tag coalescing
// (classic CS:APP layout). Single-threaded; fatlfs is called from one context.
#include "fatlfs_arena.h"
#include <stdint.h>
#include <string.h>

typedef uintptr_t word_t;            // header/footer word (also carries alloc bit)
#define WSIZE   (sizeof(word_t))
#define ALIGN   (2 * WSIZE)          // 8 on 32-bit, 16 on 64-bit
#define MIN_BLK (2 * ALIGN)          // header+footer + room for a min payload

static uint8_t *g_base, *g_end;      // usable range [g_base, g_end)
static size_t   g_used, g_peak;

static inline size_t roundup(size_t n) { return (n + (ALIGN - 1)) & ~(size_t)(ALIGN - 1); }
static inline word_t pack(size_t sz, int alloc) { return (word_t)sz | (word_t)(alloc & 1); }
static inline size_t blk_size(word_t *hdr) { return (size_t)(*hdr & ~(word_t)1); }
static inline int    blk_alloc(word_t *hdr) { return (int)(*hdr & 1); }
static inline word_t *hdr_of(void *payload) { return (word_t *)((uint8_t *)payload - WSIZE); }
static inline void   *payload_of(word_t *hdr) { return (uint8_t *)hdr + WSIZE; }
static inline word_t *ftr_of(word_t *hdr) { return (word_t *)((uint8_t *)hdr + blk_size(hdr) - WSIZE); }
static inline word_t *next_hdr(word_t *hdr) { return (word_t *)((uint8_t *)hdr + blk_size(hdr)); }
static inline word_t *prev_ftr(word_t *hdr) { return (word_t *)((uint8_t *)hdr - WSIZE); }

static void set_block(word_t *hdr, size_t sz, int alloc) {
    *hdr = pack(sz, alloc);
    *ftr_of(hdr) = pack(sz, alloc);
}

void fatlfs_arena_init(void *base, size_t size) {
    // Align the usable region; leave a sentinel (allocated, size 0) at each end so
    // coalescing never walks off the arena.
    uintptr_t start = ((uintptr_t)base + (ALIGN - 1)) & ~(uintptr_t)(ALIGN - 1);
    uintptr_t stop = ((uintptr_t)base + size) & ~(uintptr_t)(ALIGN - 1);
    g_used = g_peak = 0;
    if (stop <= start + 4 * WSIZE) { g_base = g_end = (uint8_t *)start; return; }
    // Prologue sentinel word (allocated), then one big free block, then epilogue.
    word_t *pro = (word_t *)start;
    *pro = pack(0, 1);                       // prologue footer-ish sentinel
    word_t *first = pro + 1;
    uint8_t *epi = (uint8_t *)stop - WSIZE;
    size_t free_sz = (uint8_t *)epi - (uint8_t *)first;
    set_block(first, free_sz, 0);
    *(word_t *)epi = pack(0, 1);             // epilogue sentinel
    g_base = (uint8_t *)first;
    g_end = epi;
}

static void split(word_t *hdr, size_t need) {
    size_t sz = blk_size(hdr);
    if (sz - need >= MIN_BLK) {
        set_block(hdr, need, 1);
        word_t *rest = next_hdr(hdr);
        set_block(rest, sz - need, 0);
    } else {
        set_block(hdr, sz, 1);
    }
}

void *fatlfs_arena_malloc(size_t n) {
    if (n == 0 || g_base == g_end) return NULL;
    size_t need = roundup(n + 2 * WSIZE);       // + header + footer
    if (need < MIN_BLK) need = MIN_BLK;
    for (word_t *h = (word_t *)g_base; (uint8_t *)h < g_end; h = next_hdr(h)) {
        if (!blk_alloc(h) && blk_size(h) >= need) {
            split(h, need);
            g_used += blk_size(h);
            if (g_used > g_peak) g_peak = g_used;
            return payload_of(h);
        }
    }
    return NULL;                                  // out of arena
}

void fatlfs_arena_free(void *p) {
    if (!p) return;
    word_t *h = hdr_of(p);
    size_t sz = blk_size(h);
    g_used -= sz;
    set_block(h, sz, 0);
    // coalesce with next
    word_t *nx = next_hdr(h);
    if ((uint8_t *)nx < g_end && !blk_alloc(nx)) {
        set_block(h, blk_size(h) + blk_size(nx), 0);
    }
    // coalesce with prev
    word_t *pf = prev_ftr(h);
    if ((uint8_t *)pf >= g_base - WSIZE && !blk_alloc(pf)) {
        size_t psz = blk_size(pf);
        word_t *ph = (word_t *)((uint8_t *)h - psz);
        if ((uint8_t *)ph >= g_base) {
            set_block(ph, psz + blk_size(h), 0);
        }
    }
}

void *fatlfs_arena_calloc(size_t n, size_t sz) {
    size_t tot = n * sz;
    if (sz && tot / sz != n) return NULL;         // overflow
    void *p = fatlfs_arena_malloc(tot);
    if (p) memset(p, 0, tot);
    return p;
}

void *fatlfs_arena_realloc(void *p, size_t n) {
    if (!p) return fatlfs_arena_malloc(n);
    if (n == 0) { fatlfs_arena_free(p); return NULL; }
    word_t *h = hdr_of(p);
    size_t cur = blk_size(h) - 2 * WSIZE;          // current payload capacity
    if (n <= cur) return p;                        // fits (don't bother shrinking)
    void *np = fatlfs_arena_malloc(n);
    if (!np) return NULL;
    memcpy(np, p, cur);
    fatlfs_arena_free(p);
    return np;
}

size_t fatlfs_arena_used(void) { return g_used; }
size_t fatlfs_arena_peak(void) { return g_peak; }
