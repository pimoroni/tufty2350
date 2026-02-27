#pragma once

#include <cstddef>

extern "C" {
#include "psram_alloc.h"
}

template<class T>
struct PSRAMAllocator
{
    typedef T value_type;

    PSRAMAllocator() = default;

    template<class U>
    constexpr PSRAMAllocator(const PSRAMAllocator <U>&) noexcept {}

    [[nodiscard]] T* allocate(std::size_t n)
    {
        if (auto p = static_cast<T*>(psram_malloc(n * sizeof(T))))
        {
            return p;
        }
        return NULL;
    }

    void deallocate(T* p, std::size_t n) noexcept
    {
        psram_free(p);
    }
};

template<class T, class U>
bool operator==(const PSRAMAllocator <T>&, const PSRAMAllocator <U>&) { return true; }

template<class T, class U>
bool operator!=(const PSRAMAllocator <T>&, const PSRAMAllocator <U>&) { return false; }
