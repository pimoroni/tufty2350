add_library(usermod_bench INTERFACE)

target_sources(usermod_bench INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/bench.c
    ${CMAKE_CURRENT_LIST_DIR}/bench.cpp
)

target_include_directories(usermod_bench INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_bench)
