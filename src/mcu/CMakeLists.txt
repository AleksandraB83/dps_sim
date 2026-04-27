cmake_minimum_required(VERSION 3.13)

# Pico SDK must be initialised before project()
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(square_4ch C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

# ─── WIZnet ioLibrary_Driver ──────────────────────────────────────────────────
# Downloads the official WIZnet socket library at configure time.
# Requires an internet connection on first cmake run.
# To pin a specific commit: replace GIT_TAG value with the commit SHA.

include(FetchContent)

FetchContent_Declare(ioLibrary_Driver
    GIT_REPOSITORY https://github.com/Wiznet/ioLibrary_Driver.git
    GIT_TAG        master
)
FetchContent_MakeAvailable(ioLibrary_Driver)

# ioLibrary_Driver has no CMakeLists.txt of its own; add its sources manually.
add_library(iolibrary STATIC
    ${iolibrary_driver_SOURCE_DIR}/Ethernet/W5100S/w5100s.c
    ${iolibrary_driver_SOURCE_DIR}/Ethernet/socket.c
    ${iolibrary_driver_SOURCE_DIR}/Ethernet/wizchip_conf.c
)

target_include_directories(iolibrary PUBLIC
    ${iolibrary_driver_SOURCE_DIR}/Ethernet
    ${iolibrary_driver_SOURCE_DIR}/Ethernet/W5100S
)

# w5100s.h defines _WIZCHIP_ internally, but some versions of the library
# also require it as a compile flag.  Define it here for safety.
target_compile_definitions(iolibrary PUBLIC _WIZCHIP_=W5100S)

# ─── Executable ───────────────────────────────────────────────────────────────

add_executable(square_4ch
    main.c
    w5100s_port.c
)

pico_generate_pio_header(square_4ch ${CMAKE_CURRENT_LIST_DIR}/square_4ch.pio)

target_link_libraries(square_4ch
    pico_stdlib
    hardware_pio
    hardware_clocks
    hardware_spi
    hardware_gpio
    iolibrary
)

# USB CDC for debug output; disable UART
pico_enable_stdio_usb(square_4ch 1)
pico_enable_stdio_uart(square_4ch 0)

pico_add_extra_outputs(square_4ch)
