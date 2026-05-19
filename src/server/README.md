# DPS Signal Controller — сервер

HTTP REST API сервер для управления частотой сигналов на платах RP2040-ETH.

Сервер принимает команды через REST API и рассылает новую частоту всем подключённым платам по WebSocket.

---

## Архитектура

```
Клиент (curl / веб-интерфейс)
        │  POST /frequency
        ▼
   [Python сервер]  ←→  GET /frequency
        │
        │ WebSocket broadcast
        ├──────────────────────────▶ [RP2040-ETH #1]
        ├──────────────────────────▶ [RP2040-ETH #2]
        └──────────────────────────▶ [RP2040-ETH #N]
```

При подключении новой платы сервер сразу отправляет ей текущее значение частоты — плата не ждёт следующего изменения.

---

## Требования

- Python 3.11+

---

## Установка

```bash
cd src/server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Запуск

```bash
python server.py
```

Сервер слушает на `0.0.0.0:8080`.

---

## REST API

### Получить текущую частоту

```http
GET /frequency
```

Ответ:

```json
{"frequency": 100}
```

### Установить новую частоту

```http
POST /frequency
Content-Type: application/json

{"frequency": 500}
```

Ответ:

```json
{"frequency": 500, "clients": 2}
```

`clients` — количество плат, которым была отправлена команда.

Примеры через curl:

```bash
# Получить текущую частоту
curl http://localhost:8080/frequency

# Установить 500 Гц
curl -X POST http://localhost:8080/frequency \
     -H "Content-Type: application/json" \
     -d '{"frequency": 500}'
```

---

## WebSocket (для плат)

Эндпоинт для подключения RP2040-ETH:

```
ws://<host>:8080/ws
```

Формат сообщения (JSON, text-фрейм):

```json
{"frequency": 100}
```

Сервер отправляет сообщение:
- сразу при подключении новой платы (текущее значение);
- после каждого успешного `POST /frequency` (новое значение).

---

## Конфигурация

Настройки в начале [server.py](server.py):

| Параметр | Значение по умолчанию | Описание                           |
| -------- | --------------------- | ---------------------------------- |
| host     | `0.0.0.0`             | сетевой интерфейс                  |
| port     | `8080`                | порт HTTP и WebSocket              |
| частота  | `100`                 | начальное значение при старте (Гц) |
