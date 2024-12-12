# Dockerfile
# Используем официальный Python образ
FROM python:3.12-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev && \
    pip install --no-cache-dir -r requirements.txt

# Копируем всё содержимое проекта в рабочую директорию
COPY . .

# Устанавливаем переменную окружения для Django
ENV PYTHONUNBUFFERED=1
SENTRY_DSN=https://0d10bd23772642564322687a79f28779@o4508448111853568.ingest.de.sentry.io/4508448119324752

# Открываем порт для приложения
EXPOSE 8000

# Запускаем приложение с помощью gunicorn
CMD ["gunicorn", "myproject.wsgi:application", "--bind", "0.0.0.0:8000"]
