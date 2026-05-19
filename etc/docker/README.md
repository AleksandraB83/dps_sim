# Docker

Единый образ с nginx и Python-сервером под управлением supervisord.

- **nginx** (порт 80) — раздаёт веб-клиент и проксирует `/frequency`, `/direction` на Python-сервер
- **server** (порт 8080, внутренний) — FastAPI сервер управления MCU
- **TCP** (порт 2000) — подключение MCU-устройств напрямую к серверу

## Структура

```
etc/docker/
├── Dockerfile          # Единый образ: nginx + Python-сервер
├── nginx.conf          # Конфигурация nginx
├── supervisord.conf    # Запуск nginx и server через supervisord
├── docker-compose.yml  # Запуск контейнера
└── README.md
```

## Быстрый старт

```bash
docker compose -f etc/docker/docker-compose.yml up --build
```

Клиент доступен на [http://localhost](http://localhost).  
Порт `2000` (TCP) открыт для подключения MCU-устройств.

## Сборка вручную

Сборку запускать из корня репозитория:

```bash
docker build -f etc/docker/Dockerfile -t dps-sim .
docker run -p 80:80 -p 2000:2000 dps-sim
```

## GitHub Actions

При push в `master` образ собирается и публикуется в GitHub Container Registry:

```
ghcr.io/<owner>/<repo>:latest
```

Подробнее — в [.github/workflows/docker.yml](../../.github/workflows/docker.yml).
