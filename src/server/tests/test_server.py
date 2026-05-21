"""Tests for src/server/server.py"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import server as srv
from server import _broadcast_state, _state_frame, app, mcu_tcp_handler


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_state():
    """Reset global server state before and after every test."""
    srv.current_frequency = 100
    srv.current_direction = "forward"
    srv.connected_mcus.clear()
    yield
    srv.connected_mcus.clear()


@pytest.fixture
async def client():
    """Async HTTP client talking directly to the ASGI app (no TCP lifespan)."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _mock_writer(addr=("127.0.0.1", 9999)):
    w = MagicMock()
    w.get_extra_info.return_value = addr
    w.drain = AsyncMock()
    return w


# ── _state_frame ──────────────────────────────────────────────────────────────

def test_state_frame_default():
    data = json.loads(_state_frame().decode().strip())
    assert data == {"frequency": 100, "direction": "forward"}


def test_state_frame_reflects_globals():
    srv.current_frequency = 440
    srv.current_direction = "backward"
    data = json.loads(_state_frame().decode().strip())
    assert data == {"frequency": 440, "direction": "backward"}


def test_state_frame_ends_with_newline():
    assert _state_frame().endswith(b"\n")


# ── _broadcast_state ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_broadcast_sends_frame_to_all_writers():
    w1, w2 = _mock_writer(), _mock_writer()
    srv.connected_mcus.extend([w1, w2])

    await _broadcast_state()

    frame = _state_frame()
    w1.write.assert_called_once_with(frame)
    w2.write.assert_called_once_with(frame)


@pytest.mark.anyio
async def test_broadcast_removes_stale_writer():
    good = _mock_writer()
    bad = _mock_writer()
    bad.drain.side_effect = ConnectionResetError("gone")
    srv.connected_mcus.extend([good, bad])

    await _broadcast_state()

    assert bad not in srv.connected_mcus
    assert good in srv.connected_mcus


@pytest.mark.anyio
async def test_broadcast_empty_list_does_not_raise():
    await _broadcast_state()


# ── GET /frequency ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_frequency_default(client):
    resp = await client.get("/frequency")
    assert resp.status_code == 200
    assert resp.json() == {"frequency": 100, "direction": "forward", "clients": 0}


@pytest.mark.anyio
async def test_get_frequency_reflects_state(client):
    srv.current_frequency = 250
    srv.current_direction = "backward"
    data = (await client.get("/frequency")).json()
    assert data["frequency"] == 250
    assert data["direction"] == "backward"


@pytest.mark.anyio
async def test_get_frequency_counts_connected_clients(client):
    srv.connected_mcus.append(_mock_writer())
    data = (await client.get("/frequency")).json()
    assert data["clients"] == 1


# ── POST /frequency ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_set_frequency_valid(client):
    resp = await client.post("/frequency", json={"frequency": 300})
    assert resp.status_code == 200
    assert resp.json()["frequency"] == 300
    assert srv.current_frequency == 300


@pytest.mark.anyio
async def test_set_frequency_zero_rejected(client):
    resp = await client.post("/frequency", json={"frequency": 0})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_set_frequency_negative_rejected(client):
    resp = await client.post("/frequency", json={"frequency": -1})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_set_frequency_missing_field_rejected(client):
    resp = await client.post("/frequency", json={})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_set_frequency_broadcasts(client):
    writer = _mock_writer()
    srv.connected_mcus.append(writer)
    await client.post("/frequency", json={"frequency": 500})
    writer.write.assert_called()


# ── GET /direction ────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_get_direction_default(client):
    resp = await client.get("/direction")
    assert resp.status_code == 200
    assert resp.json() == {"direction": "forward"}


@pytest.mark.anyio
async def test_get_direction_reflects_state(client):
    srv.current_direction = "backward"
    assert (await client.get("/direction")).json() == {"direction": "backward"}


# ── POST /direction ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_set_direction_forward(client):
    srv.current_direction = "backward"
    resp = await client.post("/direction", json={"direction": "forward"})
    assert resp.status_code == 200
    assert resp.json()["direction"] == "forward"
    assert srv.current_direction == "forward"


@pytest.mark.anyio
async def test_set_direction_backward(client):
    resp = await client.post("/direction", json={"direction": "backward"})
    assert resp.status_code == 200
    assert resp.json()["direction"] == "backward"
    assert srv.current_direction == "backward"


@pytest.mark.anyio
async def test_set_direction_case_insensitive(client):
    resp = await client.post("/direction", json={"direction": "FORWARD"})
    assert resp.status_code == 200
    assert resp.json()["direction"] == "forward"


@pytest.mark.anyio
async def test_set_direction_invalid_rejected(client):
    resp = await client.post("/direction", json={"direction": "left"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_set_direction_missing_field_rejected(client):
    resp = await client.post("/direction", json={})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_set_direction_broadcasts(client):
    writer = _mock_writer()
    srv.connected_mcus.append(writer)
    await client.post("/direction", json={"direction": "backward"})
    writer.write.assert_called()


# ── mcu_tcp_handler ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_handler_sends_initial_state_on_connect():
    reader = AsyncMock()
    reader.read.return_value = b""
    writer = _mock_writer()

    await mcu_tcp_handler(reader, writer)

    writer.write.assert_any_call(_state_frame())


@pytest.mark.anyio
async def test_handler_removes_writer_on_disconnect():
    reader = AsyncMock()
    reader.read.return_value = b""
    writer = _mock_writer()

    await mcu_tcp_handler(reader, writer)

    assert writer not in srv.connected_mcus
    writer.close.assert_called_once()


@pytest.mark.anyio
async def test_handler_removes_writer_on_exception():
    reader = AsyncMock()
    reader.read.side_effect = OSError("connection reset")
    writer = _mock_writer()

    await mcu_tcp_handler(reader, writer)

    assert writer not in srv.connected_mcus
    writer.close.assert_called_once()


@pytest.mark.anyio
async def test_handler_multiple_clients_tracked():
    """Second client connects while first is still active."""
    readers = [AsyncMock(), AsyncMock()]
    writers = [_mock_writer(("10.0.0.1", 1)), _mock_writer(("10.0.0.2", 2))]

    # First client reads one message then disconnects, second is immediate
    readers[0].read.side_effect = [b"ping", b""]
    readers[1].read.return_value = b""

    import asyncio
    await asyncio.gather(
        mcu_tcp_handler(readers[0], writers[0]),
        mcu_tcp_handler(readers[1], writers[1]),
    )

    assert writers[0] not in srv.connected_mcus
    assert writers[1] not in srv.connected_mcus
