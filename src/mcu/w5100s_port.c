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

    /* HW reset above left the chip in a fully-known state.
     * Skip wizchip_init(): its internal wizchip_sw_reset() does not wait long
     * enough for W5100S (library wait ≈ 10 µs; chip needs ≈ 2 ms), so the
     * buffer-size writes that follow land during the reset and are discarded,
     * leaving register state undefined.  Configure 1 KB TX/RX per socket
     * directly instead — chip is fully stable after the 500 ms HW-reset delay. */
    for (int8_t i = 0; i < _WIZCHIP_SOCK_NUM_; i++) {
        setSn_TXBUF_SIZE(i, 1);
        setSn_RXBUF_SIZE(i, 1);
    }
    printf("W5100S ready\n");
}
