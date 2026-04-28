#include <string.h>
#include <stdlib.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "CH9120_Test.h"
#include "square_4ch.pio.h"

// GPIO pins for PIO outputs (CH1..CH4). Must not conflict with CH9120:
//   UART1 TX=20, RX=21, CFG=18, RES=19
#define BASE_PIN        2u
#define DEFAULT_FREQ_HZ 100u
#define MAX_FREQ_HZ     10000000u

static PIO  g_pio;
static uint g_sm;
static uint g_offset;

// Stop the SM, reinitialise with new frequency, restart.
// pio_sm_init() inside square_4ch_program_init() clears FIFOs automatically.
static void set_frequency(uint32_t freq_hz) {
    if (freq_hz < 1u)          freq_hz = 1u;
    if (freq_hz > MAX_FREQ_HZ) freq_hz = MAX_FREQ_HZ;
    pio_sm_set_enabled(g_pio, g_sm, false);
    square_4ch_program_init(g_pio, g_sm, g_offset, BASE_PIN, freq_hz);
}

// Extract integer value of "frequency" key from a JSON object string.
// Returns true and writes *out on success.
static bool parse_freq(const char *buf, uint32_t *out) {
    const char *p = strstr(buf, "\"frequency\"");
    if (!p) return false;
    p += 11; // skip past "frequency"
    while (*p == ' ' || *p == '\t' || *p == ':') p++;
    char *end;
    long v = strtol(p, &end, 10);
    if (end == p || v <= 0) return false;
    *out = (uint32_t)v;
    return true;
}

int main(void) {
    CH9120_init();

    g_pio    = pio0;
    g_sm     = 0;
    g_offset = pio_add_program(g_pio, &square_4ch_program);
    square_4ch_program_init(g_pio, g_sm, g_offset, BASE_PIN, DEFAULT_FREQ_HZ);

    char rx_buf[128];
    int  rx_len = 0;

    while (1) {
        while (uart_is_readable(UART_ID1)) {
            char c = (char)uart_getc(UART_ID1);

            // '{' resets the accumulator so partial/stale data is discarded
            if (c == '{') {
                rx_buf[0] = '{';
                rx_len = 1;
                continue;
            }

            if (rx_len > 0 && rx_len < (int)sizeof(rx_buf) - 1) {
                rx_buf[rx_len++] = c;
            }

            if (c == '}' && rx_len > 0) {
                rx_buf[rx_len] = '\0';
                uint32_t freq;
                if (parse_freq(rx_buf, &freq)) {
                    set_frequency(freq);
                }
                rx_len = 0;
            }
        }
    }
}
