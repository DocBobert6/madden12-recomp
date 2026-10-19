# madden12 - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(madden12 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(generated/rexglue.cmake)

# Sources
set(MADDEN12_SOURCES
    src/main.cpp
    src/touch_controls.cpp
    src/crash_reporter.cpp
)

if(WIN32)
    add_executable(madden12 WIN32 ${MADDEN12_SOURCES})
elseif(ANDROID)
    # Android: libmain.so, which SDL's Java activity loads and starts (SDL_main).
    add_library(madden12 SHARED ${MADDEN12_SOURCES})
    set_target_properties(madden12 PROPERTIES OUTPUT_NAME main)
    # Calls between the library's own functions (the recompiled game calls
    # its functions millions of times a second) bound directly, not through
    # the PLT.
    target_compile_options(madden12 PRIVATE -fno-semantic-interposition)
    target_link_options(madden12 PRIVATE -Wl,-Bsymbolic-functions)
else()
    add_executable(madden12 ${MADDEN12_SOURCES})
endif()

rexglue_setup_target(madden12 GPU_PLUGINS xenos)

if(REXSDK_DIR AND TARGET imgui)
    # SDK source tree: ImGui is not on the public include path.
    target_include_directories(madden12 PRIVATE
        $<TARGET_PROPERTY:imgui,INTERFACE_INCLUDE_DIRECTORIES>)
endif()
