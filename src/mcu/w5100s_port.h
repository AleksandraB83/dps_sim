#pragma once

/*
 * Hardware port for the Waveshare RP2040-ETH W5100S chip.
 *
 * Include order is important: w5100s.h must define _WIZCHIP_ before
 * wizchip_conf.h is processed.
 */

#include "w5100s.h"        /* chip registers + defines _WIZCHIP_ = W5100S */
#include "wizchip_conf.h"  /* wizchip_init / wizchip_setnetinfo            */
#include "socket.h"        /* socket / connect / send / recv / ...         */

/* Call once at startup before wizchip_setnetinfo(). */
void w5100s_port_init(void);
