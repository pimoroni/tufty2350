add_library(usermod_fatlfs INTERFACE)

target_sources(usermod_fatlfs INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/fatlfs.c
    ${CMAKE_CURRENT_LIST_DIR}/fatlfs_arena.c
    ${CMAKE_CURRENT_LIST_DIR}/fatlfs_msc.c
)

target_include_directories(usermod_fatlfs INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${MICROPY_DIR}/lib/littlefs
)

# Route fatlfs's malloc/free/calloc/realloc to the fixed PSRAM arena (fatlfs_arena.c)
# instead of libc malloc, which on RP2 is backed by scarce SRAM.
target_compile_definitions(usermod_fatlfs INTERFACE
    FATLFS_ARENA_ALLOC=1
)

target_link_libraries(usermod INTERFACE usermod_fatlfs)
