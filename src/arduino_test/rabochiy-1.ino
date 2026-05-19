#include <Arduino.h>
#include <hardware/pwm.h>

const uint pins[4] = {0, 1, 2, 3};
const uint pwmFreq = 1000;                  // базовая частота ШИМ 1 кГц
const uint pwmWrap = 65000;
const uint dutyHalf = pwmWrap / 2;          // 50% для ШИМ
const uint dutyFull = pwmWrap;              // 100% для постоянного свечения

uint slice_num[4];
uint channel[4];

// Таблица фаз: строки – фаза (0..3), столбцы – каналы (0,1,2,3)
const bool phaseTable[4][4] = {
    {1, 0, 1, 0},   // фаза 0: каналы 0 и 2 – HIGH, каналы 1 и 3 – LOW
    {1, 1, 1, 1},   // фаза 1: все HIGH
    {0, 1, 0, 1},   // фаза 2: каналы 1 и 3 – HIGH, каналы 0 и 2 – LOW
    {0, 0, 0, 0}    // фаза 3: все LOW
};

volatile uint8_t phase = 0;
struct repeating_timer timer;
volatile uint32_t callCount = 0;
volatile uint32_t callsPerPhase = 0;
volatile bool enabled = true;

bool timerCallback(struct repeating_timer *t) {
    if (!enabled) return true;
    callCount++;
    if (callCount >= callsPerPhase) {
        callCount = 0;
        phase = (phase + 1) % 4;
        for (int i = 0; i < 4; i++) {
            pwm_set_chan_level(slice_num[i], channel[i], 
                               phaseTable[phase][i] ? dutyHalf : 0);
        }
    }
    return true;
}

void setMode(uint8_t mode) {
    // mode = 0 -> 0 Гц (только каналы 1 и 3 горят постоянно)
    // mode = 1..10 -> частота mode Гц (все 4 канала со сдвигом 90°)
    if (mode == 0) {
        enabled = false;
        // Отключаем таймерное переключение, устанавливаем уровни вручную
        pwm_set_chan_level(slice_num[0], channel[0], dutyFull);
        pwm_set_chan_level(slice_num[1], channel[1], 0);
        pwm_set_chan_level(slice_num[2], channel[2], dutyFull);
        pwm_set_chan_level(slice_num[3], channel[3], 0);
        Serial.println("0 Гц: горят только каналы 1 и 3 (GP0, GP2)");
        return;
    }
    
    // Для частот от 1 до 10 Гц
    enabled = true;
    uint32_t freq = mode;  // mode = 1..10
    // callsPerPhase = 1000 / freq (так как таймер 250 мкс, 1/4 периода = 250000 мкс, деление на 250 мкс = 1000/freq)
    callsPerPhase = 1000 / freq;
    if (callsPerPhase < 1) callsPerPhase = 1;
    callCount = 0;
    phase = 0;
    // Установить начальные уровни (фаза 0)
    for (int i = 0; i < 4; i++) {
        pwm_set_chan_level(slice_num[i], channel[i], phaseTable[0][i] ? dutyHalf : 0);
    }
    Serial.print(freq); Serial.println(" Гц, все 4 канала, сдвиг 90°");
}

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("Инициализация: 0 Гц (только 1 и 3), затем 1..10 Гц каждые 10 секунд");

    for (int i = 0; i < 4; i++) {
        gpio_set_function(pins[i], GPIO_FUNC_PWM);
        slice_num[i] = pwm_gpio_to_slice_num(pins[i]);
        channel[i]   = pwm_gpio_to_channel(pins[i]);
        float clockDiv = (125000000.0f / pwmFreq) / (pwmWrap + 1);
        pwm_set_clkdiv(slice_num[i], clockDiv);
        pwm_set_wrap(slice_num[i], pwmWrap);
        pwm_set_chan_level(slice_num[i], channel[i], 0);
        pwm_set_enabled(slice_num[i], true);
        Serial.printf("GPIO %d: slice %d, channel %d\n", pins[i], slice_num[i], channel[i]);
    }

    add_repeating_timer_us(-250, timerCallback, NULL, &timer);

    // Циклическая смена режимов: 0,1,2,...,10, затем снова 0
    uint32_t lastChange = millis();
    uint8_t currentMode = 0;
    setMode(0);
    while (true) {
        if (millis() - lastChange >= 10000) {
            lastChange = millis();
            currentMode++;
            if (currentMode > 10) currentMode = 0;
            setMode(currentMode);
        }
        delay(10);
    }
}

void loop() {
    // пусто
}