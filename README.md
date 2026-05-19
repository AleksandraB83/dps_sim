# DPS Sim — Имитатор ДПС

Имитатор датчика положения ДПС. Генерирует 4 меандра с попарным сдвигом фаз 90° (квадратурные сигналы), управляет частотой и направлением по сети.

Состоит из двух компонентов:
- **MCU** — прошивка для RP2040-ETH: генерация сигналов через PIO, приём команд по WebSocket.
- **Server** — Python-сервер: REST API для управления частотой, рассылка команд платам по WebSocket.

---

## Архитектура

```
Клиент (curl / веб-интерфейс)
        │  POST /frequency
        ▼
   [Python сервер]  ←→  GET /frequency
        │
        │ TCP, JSON
        ├──────────────────────────▶ [RP2040-ETH #1]
        ├──────────────────────────▶ [RP2040-ETH #2]
        └──────────────────────────▶ [RP2040-ETH #N]
```

Сервер отправляет платам JSON по TCP. Плата принимает данные через CH9120 (TCP-to-UART мост).

---

## Схема подключения

### Компоненты

| № | Компонент | Кол-во | Назначение |
|---|-----------|--------|------------|
| 1 | Микроконтроллер RP2040-ETH | 1 | Генерирует квадратурные сигналы, управляет каналами |
| 2 | Оптопара (светодиод + фототранзистор) | 4 | Гальваническая развязка между 3.3 В и 24 В частями |
| 3 | Резистор ~3 кОм | 8 | Ограничение тока через оптопары |
| 4 | Реле / силовой ключ | 4 | Коммутация силовой цепи 24 В |
| 5 | Защитный диод | 4 | Защита от обратных выбросов индуктивной нагрузки |
| 6 | Источник питания +3.3 В | 1 | Питание МК и цепей управления |
| 7 | Источник питания +24 В | 1 | Питание силовых цепей |

### Подключение к RP2040-ETH

| Компонент | Вывод | Пин RP2040-ETH |
|-----------|-------|----------------|
| Энкодер | Канал A | GP0 |
| Энкодер | Канал B | GP2 |
| Энкодер | GND | GND |
| Энкодер | VCC | +3.3 V |
| Светодиод MPF | Катод | GP1 |
| Светодиод CLIFT | Катод | GP3 |

### Выходные сигналы PIO

| GPIO | Канал | Фаза |
|------|-------|------|
| BASE_PIN + 0 (GP2) | CH1 | 0° |
| BASE_PIN + 1 (GP3) | CH2 | 90° |
| BASE_PIN + 2 (GP4) | CH3 | 0° |
| BASE_PIN + 3 (GP5) | CH4 | 90° |

> GP16–GP21 заняты W5100S (SPI1) — не используйте их как BASE_PIN.

### Распиновка W5100S (SPI1)

| GPIO | Функция |
|------|---------|
| GP10 | SCK |
| GP11 | MOSI |
| GP12 | MISO |
| GP13 | CS |
| GP15 | RST |

---

## Принцип работы

Квадратурный энкодер выдаёт два сигнала A и B со сдвигом 90°, что позволяет:
- подсчитывать количество оборотов/импульсов;
- определять направление вращения.

Направление определяется по порядку изменений:

| Последовательность | Направление |
|-------------------|-------------|
| A изменился раньше B | Вперёд (+) |
| B изменился раньше A | Назад (−) |

MCU генерирует квадратурные сигналы через PIO RP2040. Частота и направление управляются удалённо: сервер отправляет JSON-пакеты по TCP, CH9120 прозрачно преобразует их в UART, MCU разбирает пакет и обновляет параметры генерации без прерывания сигналов.

---

## Сборка прошивки MCU

### Зависимости

- [Raspberry Pi Pico SDK](https://github.com/raspberrypi/pico-sdk) ≥ 1.5
- CMake ≥ 3.13
- ARM GCC toolchain (`arm-none-eabi-gcc`)
- WIZnet ioLibrary_Driver — скачивается автоматически через `FetchContent` при первом `cmake`

### Установка инструментов (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential

git clone --recurse-submodules https://github.com/raspberrypi/pico-sdk.git ~/pico-sdk
echo 'export PICO_SDK_PATH=$HOME/pico-sdk' >> ~/.bashrc
source ~/.bashrc
```

### Настройка сетевых параметров

Перед сборкой отредактируйте константы в начале [src/mcu/main.c](src/mcu/main.c):

```c
// Адрес сервера
static const uint8_t  SERVER_IP[4]   = {192, 168, 1, 100};
static const uint16_t SERVER_PORT    = 8080;
static const char    *WS_HOST        = "192.168.1.100";

// IP платы
static const uint8_t  NET_IP[4]      = {192, 168, 1, 10};
static const uint8_t  NET_SUBNET[4]  = {255, 255, 255, 0};
static const uint8_t  NET_GATEWAY[4] = {192, 168, 1, 1};

#define DEFAULT_FREQ_HZ 100u   // начальная частота до подключения к серверу
#define BASE_PIN        2u     // первый GPIO-пин сигналов (занимает BASE_PIN..BASE_PIN+3)
```

### Сборка

```bash
cd src/mcu
mkdir build && cd build
cmake ..
make -j$(nproc)
```

После успешной сборки в `build/` появится `main.uf2`.

### Прошивка

1. Зажать **BOOTSEL** на плате и подключить USB.
2. Плата появится как накопитель `RPI-RP2`.
3. Скопировать прошивку:

```bash
cp build/main.uf2 /media/$USER/RPI-RP2/
```

Плата перезагрузится, поднимет Ethernet и подключится к серверу.

### Диагностика через USB CDC

Плата выводит лог в последовательный порт (115200 бод):

```
DPS Signal Controller v1.0
PIO running at 100 Hz on GP2–GP5
W5100S ready
Network: 192.168.1.10
Connecting to 192.168.1.100:8080 ...
WebSocket connected — waiting for commands
Signal frequency: 500 Hz
```

```bash
minicom -D /dev/ttyACM0 -b 115200
# или
screen /dev/ttyACM0 115200
```

### Диапазон частот

| Диапазон | Точность |
|----------|----------|
| 1 Гц — 4 МГц | высокая (погрешность < 0.01%) |
| 4 МГц — 10 МГц | снижается (период < 8 тактов PIO) |

---

## Сервер

### Требования

- Python 3.11+

### Установка

```bash
cd src/server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Запуск

```bash
python server.py
```

Сервер слушает на `0.0.0.0:8080`.

### REST API

**Получить текущую частоту:**

```http
GET /frequency
```

```json
{"frequency": 100}
```

**Установить частоту:**

```http
POST /frequency
Content-Type: application/json

{"frequency": 500}
```

```json
{"frequency": 500, "clients": 2}
```

`clients` — количество плат, которым отправлена команда.

```bash
# Получить частоту
curl http://localhost:8080/frequency

# Установить 500 Гц
curl -X POST http://localhost:8080/frequency \
     -H "Content-Type: application/json" \
     -d '{"frequency": 500}'
```

### TCP-соединение (для плат)

Платы подключаются к серверу по TCP. Сервер отправляет JSON-пакеты:

```json
{"frequency": 100, "direction": "forward"}
```

Поле `direction` принимает значения `"forward"` / `"backward"` или `0` / `1`.

Сервер отправляет пакет при подключении платы и после каждого `POST /frequency`.

### Конфигурация сервера

Настройки в начале [src/server/server.py](src/server/server.py):

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| host | `0.0.0.0` | Сетевой интерфейс |
| port | `8080` | Порт HTTP и WebSocket |
| frequency | `100` | Начальная частота (Гц) |

---

## Структура проекта

```
dps_sim/
├── src/
│   ├── mcu/          # Прошивка RP2040-ETH
│   │   ├── main.c
│   │   ├── square_4ch.pio
│   │   ├── CMakeLists.txt
│   │   └── build/
│   └── server/       # Python-сервер
│       ├── server.py
│       └── requirements.txt
└── doc/              # Документация
```
