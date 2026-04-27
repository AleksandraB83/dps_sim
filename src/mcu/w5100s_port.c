#include <stdio.h>
#include "w5100s_port.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "pico/stdlib.h"

/* Waveshare RP2040-ETH W5100S wiring (fixed by board layout) */
#define ETH_SPI   spi1
#define ETH_SCK   10
#define ETH_MOSI  11
#define ETH_MISO  12
#define ETH_CS    13
#define ETH_RST   15

static uint8_t spi_rb(void)
{
    uint8_t tx = 0xFF, rx;
    spi_write_read_blocking(ETH_SPI, &tx, &rx, 1);
    return rx;
}

static void spi_wb(uint8_t b)
{
    spi_write_blocking(ETH_SPI, &b, 1);
}

static void cs_sel(void)   { gpio_put(ETH_CS, 0); }
static void cs_desel(void) { gpio_put(ETH_CS, 1); }

void w5100s_port_init(void)
{
    /* SPI1 at 10 MHz */
    spi_init(ETH_SPI, 10u * 1000u * 1000u);
    gpio_set_function(ETH_SCK,  GPIO_FUNC_SPI);
    gpio_set_function(ETH_MOSI, GPIO_FUNC_SPI);
    gpio_set_function(ETH_MISO, GPIO_FUNC_SPI);

    gpio_init(ETH_CS);
    gpio_set_dir(ETH_CS, GPIO_OUT);
    gpio_put(ETH_CS, 1);

    /* Hardware reset */
    gpio_init(ETH_RST);
    gpio_set_dir(ETH_RST, GPIO_OUT);
    gpio_put(ETH_RST, 0);
    sleep_ms(10);
    gpio_put(ETH_RST, 1);
    sleep_ms(500);  /* W5100S: PLL lock + internal init, datasheet minimum ~200 ms */

    /* Wire up WIZnet library callbacks */
    reg_wizchip_cs_cbfunc(cs_sel, cs_desel);
    reg_wizchip_spi_cbfunc(spi_rb, spi_wb);

    /* 1 KB per socket × 4 = 4 KB total: safe for W5100 and W5100S alike */
    uint8_t rx_sz[4] = {1, 1, 1, 1};
    uint8_t tx_sz[4] = {1, 1, 1, 1};
    int8_t  rc       = wizchip_init(tx_sz, rx_sz);
    if (rc != 0)
        printf("W5100S init error: %d\n", rc);
    else
        printf("W5100S ready\n");
}
