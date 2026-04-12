#include "psram_allocator.hpp"

#define PV_STD_ALLOCATOR PSRAMAllocator
#define PV_MALLOC psram_malloc
#define PV_MALLOC0 psram_malloc0
#define PV_FREE psram_free
#define PV_REALLOC psram_realloc

#define PV_DELETE(cls, ptr) ptr->~cls(); PV_FREE(ptr)