#pragma once

#include <stdint.h>

// Fast memset of 32-bit aligned memory with a 32-bit constant for large blocks of PSRAM.
void psram_memset32(void* ptr, uint32_t val, uint32_t num_words);
