cmake_minimum_required(VERSION 3.12)
include(pico_sdk_import.cmake)
project(Pico_ePaper_Code)
pico_sdk_init()

#添加编译子目录
add_subdirectory(lib/CH9120)
add_subdirectory(examples)



#添加头文件目录
include_directories(examples)
include_directories(./lib/CH9120)


# 生成可执行文件
add_executable(main
main.c
)

# Generate C header from PIO program
pico_generate_pio_header(main ${CMAKE_CURRENT_LIST_DIR}/square_4ch.pio)

# enable usb output, disable uart output
pico_enable_stdio_usb(main 1)
pico_enable_stdio_uart(main 1)

# create map/bin/hex/uf2 file etc.
pico_add_extra_outputs(main)

target_link_libraries(main examples CH9120 pico_stdlib hardware_spi hardware_pio)