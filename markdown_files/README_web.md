# Financial Agent Web Interface

Веб-интерфейс для финансового AI-агента.

## Структура проекта

```
.
├── backend/              # FastAPI backend
│   ├── api/
│   │   ├── main.py      # Главный файл приложения
│   │   ├── models/      # Pydantic модели
│   │   ├── routes/      # API routes
│   │   └── services/    # Бизнес-логика
│   ├── sessions/         # Сохраненные сессии диалогов
│   └── requirements.txt
├── frontend/             # React frontend
│   ├── src/
│   │   ├── components/  # React компоненты
│   │   ├── hooks/       # React hooks
│   │   └── App.jsx
│   └── package.json
└── agent.py              # Основной агент (используется backend)
```

## Установка

### Backend

```bash
cd backend
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Запуск

### Backend

```bash
cd backend
python run.py
```

Или:

```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Backend будет доступен на `http://localhost:8000`

### Frontend

```bash
cd frontend
npm run dev
```

Frontend будет доступен на `http://localhost:3000`

## API Endpoints

### WebSocket

- `ws://localhost:8000/api/chat/ws` - WebSocket для стриминга ответов

### REST API

- `GET /` - Информация об API
- `GET /health` - Health check
- `POST /api/chat/message` - Отправка сообщения (без стриминга)
- `GET /api/sessions/` - Список всех сессий
- `GET /api/sessions/{session_id}` - Данные сессии
- `POST /api/sessions/` - Создать новую сессию
- `POST /api/sessions/{session_id}/export` - Экспорт сессии

## Функциональность

- ✅ Чат-интерфейс в стиле ChatGPT
- ✅ Стриминг ответов в реальном времени
- ✅ Визуализация промежуточных шагов агента
- ✅ Сохранение истории диалогов
- ✅ Экспорт результатов (JSON, TXT, копирование)
- ✅ Управление памятью диалога

## Разработка

### Backend

Backend использует FastAPI с WebSocket поддержкой для стриминга.

### Frontend

Frontend использует React с Vite для быстрой разработки.

## Docker (будущее)

Планируется создание Docker контейнера для удобного развертывания.

## Быстрый старт

См. [QUICKSTART_web.md](QUICKSTART_web.md) для инструкций по быстрому запуску.

## Структура компонентов Frontend

- `ChatInterface` - Главный компонент чата
- `MessageList` - Список сообщений
- `Message` - Отдельное сообщение
- `MessageInput` - Поле ввода
- `ToolStepViewer` - Визуализация шагов агента
- `SourcesList` - Список источников
- `ExportButton` - Кнопка экспорта
- `SessionPanel` - Панель истории диалогов

## Структура Backend

- `api/main.py` - Главный файл FastAPI приложения
- `api/routes/chat.py` - WebSocket и REST endpoints для чата
- `api/routes/sessions.py` - Endpoints для управления сессиями
- `api/services/agent_service.py` - Сервис для работы с агентом
- `api/services/session_service.py` - Сервис для управления сессиями
- `api/models/schemas.py` - Pydantic модели

