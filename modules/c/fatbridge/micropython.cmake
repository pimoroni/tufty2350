add_library(usermod_fatbridge INTERFACE)

target_sources(usermod_fatbridge INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/fatbridge.c
    ${CMAKE_CURRENT_LIST_DIR}/fatbridge_msc.c
)

target_include_directories(usermod_fatbridge INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(usermod INTERFACE usermod_fatbridge)
