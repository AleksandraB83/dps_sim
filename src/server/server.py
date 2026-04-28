#!/usr/bin/env python3
"""
DPS Signal Controller — Python server.

REST API (HTTP, port 8080):
  GET  /frequency          → {"frequency": <Hz>}
  POST /frequency          → body: {"frequency": <Hz>}  → {"frequency": <Hz>, "clients": <N>}

TCP server (port 2000, for MCU via CH9120):
  On connect: server sends the current frequency immediately.
  On POST /frequency: server broadcasts the new frequency to all connected MCUs.

Frame format (JSON text, newline-terminated):  {"frequency": <Hz>}\n
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

current_frequency: int = 100          # Hz — last value set via REST API
connected_mcus: List[asyncio.StreamWriter] = []  # active MCU TCP connections

MCU_TCP_HOST = "0.0.0.0"
MCU_TCP_PORT = 2000


# ─── TCP helpers ──────────────────────────────────────────────────────────────

def _frame(freq: int) -> bytes:
    return (json.dumps({"frequency": freq}) + "\n").encode()


async def _send(writer: asyncio.StreamWriter, freq: int) -> None:
    writer.write(_frame(freq))
    await writer.drain()


# ─── MCU TCP connection handler ───────────────────────────────────────────────

async def mcu_tcp_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    connected_mcus.append(writer)
    log.info("MCU connected: %s  (total: %d)", addr, len(connected_mcus))

    try:
        await _send(writer, current_frequency)
        # Keep the connection open; detect disconnect via empty read.
        while True:
            data = await reader.read(256)
            if not data:
                break
    except Exception as exc:
        log.warning("MCU %s error: %s", addr, exc)
    finally:
        if writer in connected_mcus:
            connected_mcus.remove(writer)
        writer.close()
        log.info("MCU disconnected: %s  (total: %d)", addr, len(connected_mcus))


# ─── App lifespan: start TCP server alongside HTTP ────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    server = await asyncio.start_server(mcu_tcp_handler, MCU_TCP_HOST, MCU_TCP_PORT)
    log.info("MCU TCP server listening on %s:%d", MCU_TCP_HOST, MCU_TCP_PORT)
    try:
        yield
    finally:
        server.close()
        await server.wait_closed()


app = FastAPI(title="DPS Signal Controller", lifespan=lifespan)


# ─── REST API ─────────────────────────────────────────────────────────────────

class FrequencyUpdate(BaseModel):
    frequency: int = Field(..., gt=0, description="Output frequency in Hz (must be > 0)")


@app.get("/frequency")
async def get_frequency():
    return {"frequency": current_frequency}


@app.post("/frequency")
async def set_frequency(update: FrequencyUpdate):
    global current_frequency
    current_frequency = update.frequency

    frame = _frame(current_frequency)
    stale: List[asyncio.StreamWriter] = []

    for writer in connected_mcus:
        try:
            writer.write(frame)
            await writer.drain()
        except Exception:
            stale.append(writer)

    for writer in stale:
        connected_mcus.remove(writer)

    log.info("Frequency → %d Hz  (active clients: %d)", current_frequency, len(connected_mcus))
    return {"frequency": current_frequency, "clients": len(connected_mcus)}


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
