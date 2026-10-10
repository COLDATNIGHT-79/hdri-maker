cmake_minimum_required(VERSION 3.15)
project(hdri_processing LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build as shared library (.dll on Windows, .so on Linux)
add_library(hdri_processing SHARED
    hdri_processing.cpp
    hdri_processing.h
)

# Platform-specific settings
if(WIN32)
    # On Windows, output the DLL to the project root for easy access
    set_target_properties(hdri_processing PROPERTIES
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../"
        RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_SOURCE_DIR}/../"
        RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_SOURCE_DIR}/../"
        PREFIX ""
    )
    # Enable SIMD optimizations on MSVC
    if(MSVC)
        target_compile_options(hdri_processing PRIVATE /O2 /fp:fast /arch:AVX2)
    endif()
else()
    set_target_properties(hdri_processing PROPERTIES
        LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/../"
        PREFIX ""
    )
    # Enable optimizations on GCC/Clang
    target_compile_options(hdri_processing PRIVATE -O3 -ffast-math -mavx2)
endif()

# Use OpenMP for parallelization if available
find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    target_link_libraries(hdri_processing PRIVATE OpenMP::OpenMP_CXX)
endif()

target_include_directories(hdri_processing PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
