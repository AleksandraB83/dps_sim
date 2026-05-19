FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/server/server.py .
COPY src/client/ /usr/share/nginx/html/
COPY etc/docker/nginx.conf /etc/nginx/sites-available/default
COPY etc/docker/supervisord.conf /etc/supervisor/conf.d/app.conf

EXPOSE 80 2000

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
