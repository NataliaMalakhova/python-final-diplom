# Dockerfile
# Используем официальный Python образ
FROM python:3.12-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё содержимое проекта в рабочую директорию
COPY . .

# Устанавливаем переменную окружения для Django
ENV PYTHONUNBUFFERED=1

# Открываем порт для приложения
EXPOSE 8000

# Запускаем приложение с помощью gunicorn
CMD ["gunicorn", "myproject.wsgi:application", "--bind", "0.0.0.0:8000"]
