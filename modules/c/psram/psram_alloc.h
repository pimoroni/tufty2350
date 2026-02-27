#pragma once

#include <stddef.h>

void *psram_malloc(size_t num_bytes);
void *psram_malloc0(size_t num_bytes);
void *psram_realloc(void *ptr, size_t new_num_bytes);
void psram_free(void *ptr);