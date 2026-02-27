#include <string.h>
#include "pico.h"

#include "tlsf.h"
#include "psram_ops.h"

#ifdef MICROPY_BUILD_TYPE
#include "py/runtime.h"
#include "py/gc.h"
#endif

// Start 3MB in and use 4MB, leaving 1MB for a RAMFS
#define PSRAM_MALLOC_BASE 0x11300000
#define PSRAM_MALLOC_SIZE 0x00400000

static tlsf_t allocator;

void *psram_malloc(size_t num_bytes) {
    if (!allocator) {
        allocator = tlsf_create_with_pool((void*)PSRAM_MALLOC_BASE, PSRAM_MALLOC_SIZE, PSRAM_MALLOC_SIZE);
    }

    void* ptr = tlsf_malloc(allocator, num_bytes);

#ifdef MICROPY_BUILD_TYPE
    if (!ptr) {
        gc_collect();
        ptr = tlsf_malloc(allocator, num_bytes);

        if (!ptr) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("PSRAM: Failed to allocate %lu bytes!"), num_bytes);
        }
    }
#endif

    return ptr;
}

void *psram_malloc0(size_t num_bytes) {
    // Round up to be 32-bit aligned
    num_bytes = (num_bytes + 3) & ~3u;
    void* ptr = psram_malloc(num_bytes);

    if (ptr) psram_memset32(ptr, 0, num_bytes >> 2);

    return ptr;
}

void *psram_realloc(void *ptr, size_t new_num_bytes) {
    if (ptr < (void*)PSRAM_MALLOC_BASE || ptr >= (void*)(PSRAM_MALLOC_BASE + PSRAM_MALLOC_SIZE)) __breakpoint();
    void* new_ptr = tlsf_realloc(allocator, ptr, new_num_bytes);

#ifdef MICROPY_BUILD_TYPE
    if (!new_ptr) {
        gc_collect();
        new_ptr = tlsf_realloc(allocator, ptr, new_num_bytes);

        if (!new_ptr) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("PSRAM: Failed to allocate %lu bytes!"), new_num_bytes);
        }
    }
#endif

    return new_ptr;
}

void psram_free(void *ptr) {
    if (ptr < (void*)PSRAM_MALLOC_BASE || ptr >= (void*)(PSRAM_MALLOC_BASE + PSRAM_MALLOC_SIZE)) __breakpoint();
    tlsf_free(allocator, ptr);
}
