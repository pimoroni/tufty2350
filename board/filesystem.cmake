# Make sure we get our VirtualEnv Python
set(Python_FIND_VIRTUALENV "FIRST")
set(Python_FIND_UNVERSIONED_NAMES "FIRST")
set(Python_FIND_STRATEGY "LOCATION")
find_package (Python COMPONENTS Interpreter Development)

message("dir2uf2/py_decl: Using Python ${Python_EXECUTABLE}")

# Convert supplies paths to absolute, for a quieter life
get_filename_component(PIMORONI_ROMFS_DIR ${PIMORONI_ROMFS_DIR} REALPATH)
get_filename_component(PIMORONI_FS_DIR ${PIMORONI_FS_DIR} REALPATH)

if (EXISTS "${PIMORONI_TOOLS_DIR}/py_decl/py_decl.py")
    add_custom_target("${MICROPY_TARGET}-verify" ALL
        COMMAND ${Python_EXECUTABLE} "${PIMORONI_TOOLS_DIR}/py_decl/py_decl.py" --to-json --verify "${CMAKE_CURRENT_BINARY_DIR}/${MICROPY_TARGET}.uf2"
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "pydecl: Verifying ${MICROPY_TARGET}.uf2"
        DEPENDS ${MICROPY_TARGET}
    )
endif()

# 4100 sectors (16MB) total
# 512 sectors (2MB) allocated for MicroPython
# 256 sectors (1MB) allocated for ROMFS
# ~3332 sectors (~13MB) for a SINGLE unified LittleFS (fatlfs build)
#
# fatlfs build: the user filesystem is one big LittleFS mounted at "/", with
# the badge OS/apps under "/system" (a subdirectory). We stage the firmware
# content under a "system/" dir and have dir2uf2 build a LittleFS image of it
# (matching the device's VfsLfs2 params), so the -with-filesystem build flashes a
# fully-populated, ready-to-run badge in one go.
set(PIMORONI_FS_STAGE "${CMAKE_BINARY_DIR}/${MICROPY_TARGET}-fs-stage")
if (EXISTS "${PIMORONI_FS_DIR}")
    add_custom_target("${MICROPY_TARGET}-fs-stage" ALL
        COMMAND ${CMAKE_COMMAND} -E rm -rf "${PIMORONI_FS_STAGE}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${PIMORONI_FS_STAGE}/system"
        COMMAND ${CMAKE_COMMAND} -E copy_directory "${PIMORONI_FS_DIR}" "${PIMORONI_FS_STAGE}/system"
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "fatlfs: staging ${PIMORONI_FS_DIR} -> /system for the unified LittleFS."
        DEPENDS ${MICROPY_TARGET}
        DEPENDS "${MICROPY_TARGET}-verify"
    )
endif()

if (EXISTS "${MICROPY_DIR}/tools/mpremote/mpremote.py" AND EXISTS "${PIMORONI_ROMFS_DIR}")
    MESSAGE("mpremote romfs build: Using root ${PIMORONI_ROMFS_DIR}.")
    MESSAGE("mpremote romfs build: Outputting filesystem binary: ${CMAKE_BINARY_DIR}/${MICROPY_TARGET}-romfs.bin")
    add_custom_target("${MICROPY_TARGET}-romfs.bin" ALL
        COMMAND ${Python_EXECUTABLE} "${MICROPY_DIR}/tools/mpremote/mpremote.py" romfs --output "${CMAKE_BINARY_DIR}/${MICROPY_TARGET}-romfs.bin" build "${PIMORONI_ROMFS_DIR}"
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "mpremote romfs build: Packing ROMFS filesystem to ${MICROPY_TARGET}-romfs.bin."
        DEPENDS ${MICROPY_TARGET}
        DEPENDS "${MICROPY_TARGET}-verify"
    )
endif()

if (EXISTS "${PIMORONI_TOOLS_DIR}/dir2uf2/dir2uf2" AND EXISTS "${PIMORONI_FS_DIR}")
    MESSAGE("dir2uf2: Using ROMFS binary: ${CMAKE_BINARY_DIR}/${MICROPY_TARGET}-romfs.bin")
    add_custom_target("${MICROPY_TARGET}-romfs.uf2" ALL
        COMMAND ${Python_EXECUTABLE} "${PIMORONI_TOOLS_DIR}/dir2uf2/dir2uf2" --fs-blockdev ROMFS --sparse --append-to "${MICROPY_TARGET}.uf2" --filename romfs.uf2 "${CMAKE_BINARY_DIR}/${MICROPY_TARGET}-romfs.bin"
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "dir2uf2: Appending ROMFS to ${MICROPY_TARGET}.uf2."
        DEPENDS ${MICROPY_TARGET}
        DEPENDS "${MICROPY_TARGET}-romfs.bin"
        DEPENDS "${MICROPY_TARGET}.uf2"
        DEPENDS "${MICROPY_TARGET}-verify"
    )
endif()

if (EXISTS "${PIMORONI_TOOLS_DIR}/dir2uf2/dir2uf2" AND EXISTS "${PIMORONI_FS_DIR}")
    MESSAGE("dir2uf2: Building unified LittleFS from ${PIMORONI_FS_STAGE} (content under /system).")
    # Build a LittleFS image of the staged tree and append it to the whole-flash
    # "MicroPython" block device. Params MUST match the device's VfsLfs2 mount
    # (rp2.Flash block_size=4096, VfsLfs2 readsize=32, progsize=256) or _boot.py
    # would fail to mount and silently reformat.
    add_custom_target("${MICROPY_TARGET}-with-filesystem.uf2" ALL
        COMMAND ${Python_EXECUTABLE} "${PIMORONI_TOOLS_DIR}/dir2uf2/dir2uf2" --fs-type lfs --fs-blockdev MicroPython --fs-compact --sparse --block-size 4096 --read-size 32 --prog-size 256 --append-to "${MICROPY_TARGET}-romfs.uf2" --filename with-filesystem.uf2 "${PIMORONI_FS_STAGE}"
        WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
        COMMENT "dir2uf2: Building + appending unified LittleFS (/system) to ${MICROPY_TARGET}.uf2."
        DEPENDS "${MICROPY_TARGET}-romfs.uf2"
        DEPENDS "${MICROPY_TARGET}-fs-stage"
        DEPENDS "${MICROPY_TARGET}-verify"
    )
endif()