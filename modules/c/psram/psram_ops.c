#include "psram_ops.h"

#include <string.h>

void psram_memset32(void* ptr, uint32_t val, uint32_t num_words) {
    uint32_t* ptr32 = (uint32_t*)ptr;

    // Align to 64-bit cache line
    if ((uintptr_t)ptr & 4) {
        *ptr32++ = val;
        --num_words;
    }

    // Align end to cache line
    if (num_words & 1) {
        ptr32[--num_words] = val;
    }

    // Bulk of memset through non-cached alias, invalidating the cache
    uint64_t* addr = (uint64_t*)((uint8_t*)ptr32 + 0x4000000);
    const uint64_t* end = addr + (num_words >> 1);
    uint8_t* cache_clean = (uint8_t*)ptr32 + 0x8000002;
    uint64_t val64 = ((uint64_t)val << 32) | val;
    while (addr < end) {
        *addr++ = val64;
        *cache_clean = 0;
        cache_clean += 8;
    }
}
