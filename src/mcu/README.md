# square_4ch — 4-канальный генератор меандров на RP2040-ETH

Генерирует 4 меандра с попарным сдвигом фаз 90° через PIO RP2040.  
Частота управляется удалённо через WebSocket-соединение с сервером (`../server/`).

| Пин | Канал | Фаза |
|-----|-------|------|
| BASE_PIN + 0 | CH1 | 0° |
| BASE_PIN + 1 | CH2 | 90° |
| BASE_PIN + 2 | CH3 | 0° (= CH1) |
| BASE_PIN + 3 | CH4 | 90° (= CH2) |

По умолчанию: `BASE_PIN = 2` (GP2–GP5), начальная частота `100 Гц`.

---

## Принцип работы

При старте MCU поднимает Ethernet (W5100S через SPI1) и подключается к серверу по WebSocket.  
Сервер при подключении сразу присылает текущее значение частоты, затем — новые значения при каждом изменении.  
MCU перезапускает PIO state machine с новым делителем; сигналы меняются без прерывания генерации на других каналах.  
При потере связи MCU автоматически переподключается.

---

## Зависимости

- [Raspberry Pi Pico SDK](https://github.com/raspberrypi/pico-sdk) ≥ 1.5
- [WIZnet ioLibrary_Driver](https://github.com/Wiznet/ioLibrary_Driver) — скачивается автоматически через `FetchContent` при первом `cmake`
- CMake ≥ 3.13
- ARM GCC toolchain (`arm-none-eabi-gcc`)

### Установка на Ubuntu/Debian

```bash
sudo apt update
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential

git clone --recurse-submodules https://github.com/raspberrypi/pico-sdk.git ~/pico-sdk
echo 'export PICO_SDK_PATH=$HOME/pico-sdk' >> ~/.bashrc
source ~/.bashrc
```

---

## Настройка перед сборкой

Все параметры — в начале [main.c](main.c). Обязательно поправьте сетевые константы:

```c
// Адрес сервера
static const uint8_t  SERVER_IP[4]   = {192, 168, 1, 100};
static const uint16_t SERVER_PORT    = 8080;
static const char    *WS_HOST        = "192.168.1.100"; // должен совпадать с SERVER_IP

// IP самой платы
static const uint8_t  NET_IP[4]      = {192, 168, 1, 10};
static const uint8_t  NET_SUBNET[4]  = {255, 255, 255, 0};
static const uint8_t  NET_GATEWAY[4] = {192, 168, 1, 1};

// Начальная частота (используется до первого подключения к серверу)
#define DEFAULT_FREQ_HZ 100u

// Первый GPIO-пин сигналов (занимает BASE_PIN .. BASE_PIN+3)
#define BASE_PIN 2u
```

> **GP16–GP21 заняты W5100S** — не используйте их как `BASE_PIN`.

---

## Сборка

```bash
cd src/mcu
mkdir build && cd build
cmake ..          # скачает WIZnet ioLibrary_Driver (нужен интернет)
make -j$(nproc)
```

После успешной сборки в `build/` появится `square_4ch.uf2`.

---

## Прошивка

1. Зажать **BOOTSEL** на плате и подключить USB.
2. Плата появится как накопитель `RPI-RP2`.
3. Скопировать прошивку:

```bash
cp build/square_4ch.uf2 /media/$USER/RPI-RP2/
```

Плата перезагрузится, поднимет Ethernet и подключится к серверу.

---

## Диагностика через USB CDC

Плата выводит лог в последовательный порт (USB CDC, 115200 бод):

```
DPS Signal Controller v1.0
PIO running at 100 Hz on GP2–GP5
W5100S ready
Network: 192.168.1.10
Connecting to 192.168.1.100:8080 ...
TCP connected
WebSocket connected — waiting for commands
Signal frequency: 500 Hz
```

Просмотр:

```bash
minicom -D /dev/ttyACM0 -b 115200
# или
screen /dev/ttyACM0 115200
```

---

## Диапазон частот

| Частота        | Точность                                  |
| -------------- | ----------------------------------------- |
| 1 Гц — 4 МГц   | высокая (ошибка < 0.01%)                  |
| 4 МГц — 10 МГц | снижается (квартал-период < 8 тактов PIO) |

При 125 МГц и 100 Гц квартал-период = 312 500 тактов — джиттера нет.

---

## Распиновка W5100S (SPI1, зафиксирована платой)

| GPIO | Функция |
| ---- | ------- |
| GP10 | SCK     |
| GP11 | MOSI    |
| GP12 | MISO    |
| GP13 | CS      |
| GP15 | RST     |
