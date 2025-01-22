FROM python:3.10-slim

# Установка необходимых пакетов для Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    apt-transport-https \
    ca-certificates \
    curl \
    unzip \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY requirements.txt .
COPY bot.py .

# Установка зависимостей Python
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python", "bot.py"]
