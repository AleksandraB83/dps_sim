#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "square_4ch.pio.h"
#include "w5100s_port.h"

// ─── Network configuration ────────────────────────────────────────────────────
//  Adjust these constants for your network before flashing.

static const uint8_t  NET_MAC[6]     = {0x00, 0x08, 0xDC, 0x11, 0x22, 0x33};
static const uint8_t  NET_IP[4]      = {192, 168, 1, 10};
static const uint8_t  NET_SUBNET[4]  = {255, 255, 255, 0};
static const uint8_t  NET_GATEWAY[4] = {192, 168, 1, 1};
static const uint8_t  NET_DNS[4]     = {8, 8, 8, 8};

static const uint8_t  SERVER_IP[4]   = {192, 168, 1, 100}; /* server address */
static const uint16_t SERVER_PORT    = 8080;
static const char    *WS_HOST        = "192.168.1.100";     /* must match SERVER_IP */
static const char    *WS_PATH        = "/ws";

#define WS_SOCKET   0u   /* W5100S socket index used for WebSocket */

// ─── Signal configuration ─────────────────────────────────────────────────────

#define BASE_PIN        2u
#define DEFAULT_FREQ_HZ 100u

// ─── PIO state ────────────────────────────────────────────────────────────────

static PIO  g_pio    = pio0;
static uint g_sm     = 0;
static uint g_offset = 0;

/*
 * Reconfigure the PIO state machine for a new output frequency.
 * Disables the SM, calls the init function with the new value (which
 * resets the PC via pio_sm_exec and repushes the X counter), then re-enables.
 */
static void set_signal_frequency(uint32_t freq_hz)
{
    if (freq_hz < 1u) freq_hz = 1u;
    pio_sm_set_enabled(g_pio, g_sm, false);
    square_4ch_program_init(g_pio, g_sm, g_offset, BASE_PIN, freq_hz);
    printf("Signal frequency: %lu Hz\n", (unsigned long)freq_hz);
}

// ─── WebSocket helpers ────────────────────────────────────────────────────────

#define WS_BUF_SIZE 512u

static uint8_t g_ws_buf[WS_BUF_SIZE];

/* Read exactly `len` bytes from socket `sn`, retrying on partial data. */
static bool net_recv_exact(uint8_t sn, uint8_t *buf, uint16_t len)
{
    uint16_t done = 0;
    while (done < len) {
        uint8_t status;
        getsockopt(sn, SO_STATUS, &status);
        if (status != SOCK_ESTABLISHED) return false;

        uint16_t avail = getSn_RX_RSR(sn);
        if (avail == 0) { sleep_ms(5); continue; }

        uint16_t chunk = (avail < (uint16_t)(len - done)) ? avail : (uint16_t)(len - done);
        int32_t  r     = recv(sn, buf + done, chunk);
        if (r <= 0) return false;
        done = (uint16_t)(done + r);
    }
    return true;
}

/*
 * Send the HTTP/1.1 Upgrade request and check for "101" in the response.
 * Uses a fixed (RFC-example) Sec-WebSocket-Key — acceptable for a client
 * that does not verify the server's Sec-WebSocket-Accept reply.
 */
static bool ws_handshake(uint8_t sn)
{
    char req[384];
    int  n = snprintf(req, sizeof(req),
        "GET %s HTTP/1.1\r\n"
        "Host: %s:%u\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n",
        WS_PATH, WS_HOST, (unsigned)SERVER_PORT);

    if (send(sn, (uint8_t *)req, (uint16_t)n) != n) return false;

    sleep_ms(300);
    int32_t r = recv(sn, g_ws_buf, (uint16_t)(WS_BUF_SIZE - 1u));
    if (r <= 0) return false;
    g_ws_buf[r] = '\0';
    return strstr((char *)g_ws_buf, "101") != NULL;
}

/* Send a masked WebSocket Pong frame with empty payload (RFC 6455 §5.5.3). */
static void ws_send_pong(uint8_t sn)
{
    /* FIN=1 opcode=Pong, MASK=1 payload_len=0, masking-key=0x00000000 */
    uint8_t frame[6] = {0x8A, 0x80, 0x00, 0x00, 0x00, 0x00};
    send(sn, frame, 6);
}

/*
 * Receive one WebSocket frame and return:
 *   >0            — new frequency value
 *   0             — frame handled (ping→pong) or irrelevant; keep looping
 *   UINT32_MAX    — fatal: close frame or I/O error; reconnect
 */
static uint32_t ws_recv_frame(uint8_t sn)
{
    uint8_t hdr[2];
    if (!net_recv_exact(sn, hdr, 2)) return UINT32_MAX;

    uint8_t  opcode = hdr[0] & 0x0Fu;
    uint32_t plen   = hdr[1] & 0x7Fu;

    if (plen == 126u) {
        uint8_t ext[2];
        if (!net_recv_exact(sn, ext, 2)) return UINT32_MAX;
        plen = ((uint32_t)ext[0] << 8) | ext[1];
    } else if (plen == 127u) {
        /* 8-byte extended length — far too large for our use, drain and skip */
        uint8_t skip[8];
        net_recv_exact(sn, skip, 8);
        return 0;
    }

    /* Server-to-client frames must not be masked (RFC 6455 §5.1) */

    if (plen >= WS_BUF_SIZE) {
        /* Drain oversized frame */
        uint32_t left = plen;
        while (left > 0) {
            uint16_t chunk = (left < WS_BUF_SIZE - 1u) ? (uint16_t)left : (uint16_t)(WS_BUF_SIZE - 1u);
            if (!net_recv_exact(sn, g_ws_buf, chunk)) return UINT32_MAX;
            left -= chunk;
        }
        return 0;
    }

    if (plen > 0) {
        if (!net_recv_exact(sn, g_ws_buf, (uint16_t)plen)) return UINT32_MAX;
    }
    g_ws_buf[plen] = '\0';

    if (opcode == 0x8u) return UINT32_MAX;           /* Close */
    if (opcode == 0x9u) { ws_send_pong(sn); return 0; } /* Ping → Pong */
    if (opcode != 0x1u && opcode != 0x0u) return 0; /* ignore non-text */

    /* Parse {"frequency": NNN} — minimal JSON extraction */
    const char *p = strstr((char *)g_ws_buf, "\"frequency\"");
    if (!p) return 0;
    p = strchr(p, ':');
    if (!p) return 0;
    p++;
    while (*p == ' ') p++;
    long val = strtol(p, NULL, 10);
    return (val > 0) ? (uint32_t)val : 0u;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

int main(void)
{
    stdio_init_all();
    sleep_ms(2000); /* wait for USB-CDC enumeration */
    printf("DPS Signal Controller v1.0\n");

    /* Start PIO signal generator at default frequency */
    g_offset = pio_add_program(g_pio, &square_4ch_program);
    square_4ch_program_init(g_pio, g_sm, g_offset, BASE_PIN, DEFAULT_FREQ_HZ);
    uint32_t current_freq = DEFAULT_FREQ_HZ;
    printf("PIO running at %u Hz on GP%u–GP%u\n",
           DEFAULT_FREQ_HZ, BASE_PIN, BASE_PIN + 3u);

    /* Initialise W5100S: SPI, GPIO, WIZnet library */
    w5100s_port_init();

    wiz_NetInfo netinfo = {
        .mac  = {NET_MAC[0], NET_MAC[1], NET_MAC[2],
                 NET_MAC[3], NET_MAC[4], NET_MAC[5]},
        .ip   = {NET_IP[0],      NET_IP[1],      NET_IP[2],      NET_IP[3]},
        .sn   = {NET_SUBNET[0],  NET_SUBNET[1],  NET_SUBNET[2],  NET_SUBNET[3]},
        .gw   = {NET_GATEWAY[0], NET_GATEWAY[1], NET_GATEWAY[2], NET_GATEWAY[3]},
        .dns  = {NET_DNS[0],     NET_DNS[1],     NET_DNS[2],     NET_DNS[3]},
        .dhcp = NETINFO_STATIC,
    };
    wizchip_setnetinfo(&netinfo);
    {
        /* Read SIPR back to confirm the write landed.
         * If this prints 0.0.0.0, the SW-reset delay in w5100s_port_init()
         * was still too short — increase sleep_ms(20) there. */
        uint8_t sipr[4];
        getSIPR(sipr);
        printf("Network: %d.%d.%d.%d  SIPR=%d.%d.%d.%d\n",
               NET_IP[0], NET_IP[1], NET_IP[2], NET_IP[3],
               sipr[0], sipr[1], sipr[2], sipr[3]);
    }

    /* Connection + receive loop with automatic reconnection */
    while (true) {
        printf("Connecting to %d.%d.%d.%d:%u ...\n",
               SERVER_IP[0], SERVER_IP[1], SERVER_IP[2], SERVER_IP[3], SERVER_PORT);

        close(WS_SOCKET);  /* ensure CLOSED state from any previous attempt */
        int8_t sock_rc = socket(WS_SOCKET, Sn_MR_TCP, 0, 0);
        if (sock_rc < 0) {
            printf("socket() failed: rc=%d SR=0x%02X\n",
                   sock_rc, getSn_SR(WS_SOCKET));
            sleep_ms(2000);
            continue;
        }

        if (connect(WS_SOCKET, (uint8_t *)SERVER_IP, SERVER_PORT) != SOCK_OK) {
            printf("connect() failed\n");
            close(WS_SOCKET);
            sleep_ms(2000);
            continue;
        }
        printf("TCP connected\n");

        if (!ws_handshake(WS_SOCKET)) {
            printf("WebSocket handshake failed\n");
            close(WS_SOCKET);
            sleep_ms(2000);
            continue;
        }
        printf("WebSocket connected — waiting for commands\n");

        while (true) {
            uint32_t freq = ws_recv_frame(WS_SOCKET);

            if (freq == UINT32_MAX) {
                printf("WebSocket closed or error — reconnecting\n");
                break;
            }

            if (freq > 0u && freq != current_freq) {
                current_freq = freq;
                set_signal_frequency(current_freq);
            }
        }

        close(WS_SOCKET);
        sleep_ms(2000);
    }
}
