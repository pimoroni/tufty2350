add_library(powman INTERFACE)

target_sources(powman INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/powman.c
    ${CMAKE_CURRENT_LIST_DIR}/rosc.c
)

target_include_directories(powman INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(powman INTERFACE hardware_powman hardware_gpio hardware_flash hardware_i2c hardware_pwm)
