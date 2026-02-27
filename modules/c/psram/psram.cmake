  add_library(psram INTERFACE)

  target_sources(psram INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/psram_alloc.c
    ${CMAKE_CURRENT_LIST_DIR}/psram_ops.c
    ${CMAKE_CURRENT_LIST_DIR}/tlsf/tlsf.c
  )

  target_include_directories(psram INTERFACE 
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/tlsf
    ${CMAKE_CURRENT_LIST_DIR}/tlsf/include
  )

  target_link_libraries(psram INTERFACE pico_platform)

  set_source_files_properties(
    ${CMAKE_CURRENT_LIST_DIR}/tlsf/tlsf.c
    PROPERTIES COMPILE_OPTIONS
    "-O2;-fgcse-after-reload;-floop-interchange;-fpeel-loops;-fpredictive-commoning;-fsplit-paths;-ftree-loop-distribute-patterns;-ftree-loop-distribution;-ftree-vectorize;-ftree-partial-pre;-funswitch-loops"
  )
