#!/usr/bin/env python3
"""
DPS Signal Controller — сервер с поддержкой направления.

REST API (HTTP, порт 8080):
  GET  /frequency   → {"frequency":<Hz>, "direction":<str>, "clients":<N>}
  POST /frequency   → тело: {"frequency":<Hz>}   → возвращает то же, что GET
  GET  /direction   → {"direction":<str>}
  POST /direction   → тело: {"direction":"forward"|"backward"} → обновляет и транслирует

TCP сервер (порт 2000, для MCU через CH9120):
  - При подключении сразу шлёт {"frequency":..., "direction":...}\n
  - При любом изменении (частота/направление) мгновенно рассылает новое состояние всем MCU.
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

# ── Глобальное состояние ─────────────────────────────────────────────
current_frequency: int = 100
current_direction: str = "forward"          # "forward" или "backward"
connected_mcus: List[asyncio.StreamWriter] = []

MCU_TCP_HOST = "0.0.0.0"
MCU_TCP_PORT = 2000

# ── Формирование кадра для MCU ───────────────────────────────────────
def _state_frame() -> bytes:
    """JSON с частотой и направлением, завершённый символом новой строки."""
    return (json.dumps({"frequency": current_frequency,
                        "direction": current_direction}) + "\n").encode()

async def _send_state(writer: asyncio.StreamWriter) -> None:
    """Отправить текущее состояние одному MCU."""
    writer.write(_state_frame())
    await writer.drain()

async def _broadcast_state() -> None:
    """Разослать состояние всем подключённым MCU."""
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
    log.info("Broadcast: freq=%d Hz, dir=%s, clients=%d",
             current_frequency, current_direction, len(connected_mcus))

# ── Обработчик TCP-соединений от MCU ──────────────────────────────────
async def mcu_tcp_handler(reader: asyncio.StreamReader,
                          writer: asyncio.StreamWriter) -> None:
    addr = writer.get_extra_info("peername")
    connected_mcus.append(writer)
    log.info("MCU подключён: %s (всего: %d)", addr, len(connected_mcus))

    try:
        await _send_state(writer)   # немедленно отправить текущие параметры
        while True:
            # просто ждём, пока клиент не закроет соединение
            data = await reader.read(256)
            if not data:
                break
    except Exception as exc:
        log.warning("MCU %s ошибка: %s", addr, exc)
    finally:
        if writer in connected_mcus:
            connected_mcus.remove(writer)
        writer.close()
        log.info("MCU отключён: %s (всего: %d)", addr, len(connected_mcus))

# ── Время жизни приложения: запуск TCP-сервера ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    server = await asyncio.start_server(mcu_tcp_handler, MCU_TCP_HOST, MCU_TCP_PORT)
    log.info("TCP сервер для MCU запущен на %s:%d", MCU_TCP_HOST, MCU_TCP_PORT)
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

# ── Модели Pydantic ───────────────────────────────────────────────────
class FrequencyUpdate(BaseModel):
    frequency: int = Field(..., gt=0, description="Частота в Гц (>0)")

class DirectionUpdate(BaseModel):
    direction: str = Field(..., description="Направление: 'forward' или 'backward'")

    @validator('direction')
    def valid_direction(cls, v):
        v = v.lower()
        if v not in ("forward", "backward"):
            raise ValueError("Допустимы только 'forward' или 'backward'")
        return v

# ── REST API ──────────────────────────────────────────────────────────
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

# ── Точка входа ───────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")