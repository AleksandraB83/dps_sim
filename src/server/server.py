#!/usr/bin/env python3
"""
DPS Signal Controller — Python server.

REST API (HTTP):
  GET  /frequency          → {"frequency": <Hz>}
  POST /frequency          → body: {"frequency": <Hz>}  → {"frequency": <Hz>, "clients": <N>}

WebSocket (for MCU):
  ws://<host>:8080/ws
  On connect: server sends current frequency immediately.
  On POST /frequency: server broadcasts new frequency to all connected MCU clients.

Frame format (JSON text):  {"frequency": <Hz>}
"""

import asyncio
import json
import logging
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="DPS Signal Controller")

current_frequency: int = 100          # Hz — last value set via REST API
connected_mcus: List[WebSocket] = []  # active MCU WebSocket connections


class FrequencyUpdate(BaseModel):
    frequency: int = Field(..., gt=0, description="Output frequency in Hz (must be > 0)")


# ─── REST API ─────────────────────────────────────────────────────────────────

@app.get("/frequency")
async def get_frequency():
    return {"frequency": current_frequency}


@app.post("/frequency")
async def set_frequency(update: FrequencyUpdate):
    global current_frequency
    current_frequency = update.frequency

    message = json.dumps({"frequency": current_frequency})
    stale: List[WebSocket] = []

    for ws in connected_mcus:
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)

    for ws in stale:
        connected_mcus.remove(ws)

    log.info("Frequency → %d Hz  (active clients: %d)", current_frequency, len(connected_mcus))
    return {"frequency": current_frequency, "clients": len(connected_mcus)}


# ─── WebSocket endpoint for MCU ───────────────────────────────────────────────

@app.websocket("/ws")
async def mcu_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_mcus.append(websocket)
    client = websocket.client
    log.info("MCU connected: %s  (total: %d)", client, len(connected_mcus))

    try:
        # Send the current frequency immediately so new MCU doesn't wait
        await websocket.send_text(json.dumps({"frequency": current_frequency}))

        # Keep the connection alive; MCU doesn't send data, but we must
        # await something to detect disconnection.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        log.info("MCU disconnected: %s  (total: %d)", client, len(connected_mcus) - 1)
    except Exception as exc:
        log.warning("MCU %s error: %s", client, exc)
    finally:
        if websocket in connected_mcus:
            connected_mcus.remove(websocket)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
