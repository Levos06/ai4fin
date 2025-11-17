# Инструкция по запуску в Docker

Этот документ описывает, как запустить Financial AI Agent в Docker контейнерах.

## Требования

- Docker (версия 20.10 или выше)
- Docker Compose (версия 2.0 или выше)

## Быстрый старт

### 1. Подготовка переменных окружения

Скопируйте файл `env.example` в `.env`:

```bash
cp env.example .env
```

Откройте `.env` и укажите ваши API ключи:

```env
OPENROUTER_API_KEY=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
TAVILY_API_KEY=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
```

**Важно:** Если вы не укажете API ключи в `.env`, будут использованы значения по умолчанию из `config.py`. Для production обязательно используйте свои ключи!

### 2. Запуск контейнеров

Запустите все сервисы одной командой:

```bash
docker-compose up -d
```

Эта команда:
- Соберет образы для бэкенда и фронтенда
- Запустит оба контейнера
- Настроит сеть между ними
- Смонтирует необходимые volumes

### 3. Проверка работы

После запуска проверьте статус контейнеров:

```bash
docker-compose ps
```

Вы должны увидеть два контейнера в статусе `Up`:
- `financial-agent-backend` (порт 8000)
- `financial-agent-frontend` (порт 80)

### 4. Доступ к приложению

Откройте браузер и перейдите по адресу:

```
http://localhost
```

Или если порт 80 занят, используйте:

```
http://localhost:80
```

## Управление контейнерами

### Остановка

```bash
docker-compose down
```

### Остановка с удалением volumes (удалит все данные!)

```bash
docker-compose down -v
```

### Просмотр логов

Все логи:
```bash
docker-compose logs
```

Логи бэкенда:
```bash
docker-compose logs backend
```

Логи фронтенда:
```bash
docker-compose logs frontend
```

Логи в реальном времени:
```bash
docker-compose logs -f
```

### Перезапуск

```bash
docker-compose restart
```

Перезапуск конкретного сервиса:
```bash
docker-compose restart backend
```

### Пересборка образов

Если вы изменили код и нужно пересобрать образы:

```bash
docker-compose build
docker-compose up -d
```

Или одной командой:

```bash
docker-compose up -d --build
```

## Структура данных

Следующие директории монтируются как volumes и сохраняют данные между перезапусками:

- `./vector_db` - векторная база данных (ChromaDB)
- `./backend/sessions` - сохраненные диалоги
- `./charts_cache` - кэш графиков
- `./logs` - логи приложения
- `./all_documents` - документы для базы знаний

## Проблемы и решения

### Порт уже занят

Если порт 8000 или 80 занят, измените порты в `docker-compose.yml`:

```yaml
services:
  backend:
    ports:
      - "8001:8000"  # Измените 8001 на свободный порт
  frontend:
    ports:
      - "8080:80"  # Измените 8080 на свободный порт
```

### Ошибки при сборке

Если возникают ошибки при сборке, попробуйте:

```bash
docker-compose build --no-cache
```

### Контейнер не запускается

Проверьте логи:

```bash
docker-compose logs backend
docker-compose logs frontend
```

### Проблемы с правами доступа

На Linux/Mac может потребоваться изменить права доступа:

```bash
sudo chown -R $USER:$USER vector_db backend/sessions charts_cache logs
```

## Производственное развертывание

Для production рекомендуется:

1. Использовать переменные окружения из безопасного хранилища
2. Настроить HTTPS через reverse proxy (nginx, traefik)
3. Использовать Docker secrets для API ключей
4. Настроить мониторинг и логирование
5. Использовать Docker Swarm или Kubernetes для оркестрации

## Дополнительная информация

- Бэкенд доступен напрямую на `http://localhost:8000`
- API документация: `http://localhost:8000/docs`
- WebSocket endpoint: `ws://localhost:8000/ws`

