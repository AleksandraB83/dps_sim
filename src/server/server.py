#!/usr/bin/env python3
"""
DPS Signal Controller — Python server with direction support.

REST API (HTTP, port 8080):
  GET  /frequency       -> {"frequency": <Hz>, "direction": <str>, "clients": <N>}
  POST /frequency       -> body: {"frequency": <Hz>}  -> same as GET
  GET  /direction       -> {"direction": <str>}
  POST /direction       -> body: {"direction": "forward"|"backward"} -> {"direction":..., "clients":..., "frequency":...}

TCP server (port 2000, for MCU via CH9120):
  On connect: server sends current state {"frequency": <Hz>, "direction": <str>}\n
  On any state change (frequency or direction): broadcast new JSON to all connected MCUs.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

current_frequency: int = 100          # Hz
current_direction: str = "forward"    # "forward" or "backward"
connected_mcus: List[asyncio.StreamWriter] = []

MCU_TCP_HOST = "0.0.0.0"
MCU_TCP_PORT = 2000


def _state_frame() -> bytes:
    """Формирует JSON с частотой и направлением, завершённый \\n."""
    return (json.dumps({"frequency": current_frequency, "direction": current_direction}) + "\n").encode()


async def _send_state(writer: asyncio.StreamWriter) -> None:
    """Отправляет текущее состояние (частота+направление) одному клиенту."""
    writer.write(_state_frame())
    await writer.drain()


async def _broadcast_state() -> None:
    """Расслылает текущее состояние всем подключённым MCU."""
    frame = _state_frame()
    stale = []
    for writer in connected_mcus:
        try:
            writer.write(frame)
            await writer.drain()
        except Exception:
            stale.append(writer)
    for writer in stale:
        if writer in connected_mcus:
            connected_mcus.remove(writer)
    log.info("Broadcast state: freq=%d Hz, dir=%s, active clients=%d",
             current_frequency, current_direction, len(connected_mcus))


# ─── MCU TCP connection handler ───────────────────────────────────────────────
async def mcu_tcp_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    connected_mcus.append(writer)
    log.info("MCU connected: %s  (total: %d)", addr, len(connected_mcus))

    try:
        await _send_state(writer)   # отправить текущее состояние сразу
        while True:
            # Ждём, пока клиент не закроет соединение
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


# ─── App lifespan: запуск TCP сервера ─────────────────────────────────────────
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic модели и валидация ─────────────────────────────────────────────
class FrequencyUpdate(BaseModel):
    frequency: int = Field(..., gt=0, description="Output frequency in Hz (>0)")

class DirectionUpdate(BaseModel):
    direction: str = Field(..., description="Movement direction: 'forward' or 'backward'")

    @validator('direction')
    def valid_direction(cls, v):
        v = v.lower()
        if v not in ("forward", "backward"):
            raise ValueError("direction must be 'forward' or 'backward'")
        return v

# ─── REST API ─────────────────────────────────────────────────────────────────
@app.get("/frequency")
async def get_frequency():
    return {
        "frequency": current_frequency,
        "direction": current_direction,
        "clients": len(connected_mcus)
    }

@app.post("/frequency")
async def set_frequency(update: FrequencyUpdate):
    global current_frequency
    current_frequency = update.frequency
    await _broadcast_state()
    return {
        "frequency": current_frequency,
        "direction": current_direction,
        "clients": len(connected_mcus)
    }

@app.get("/direction")
async def get_direction():
    return {"direction": current_direction}

@app.post("/direction")
async def set_direction(update: DirectionUpdate):
    global current_direction
    current_direction = update.direction.lower()
    await _broadcast_state()
    return {
        "direction": current_direction,
        "frequency": current_frequency,
        "clients": len(connected_mcus)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
