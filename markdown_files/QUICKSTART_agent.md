# Быстрый старт агента

## 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

## 2. Проверка конфигурации

Убедитесь, что в `config.py` правильно настроены:
- `OPENROUTER_API_KEY` - ваш API ключ OpenRouter
- `TAVILY_API_KEY` - ваш API ключ Tavily (уже настроен)
- `AGENT_LLM_MODEL` - модель LLM (по умолчанию `google/gemini-2.5-flash-lite`)

## 3. Первый запуск

### Простой запрос
```bash
python agent.py "Какая цена акций Apple?"
```

### Интерактивный режим
```bash
python agent.py --interactive
```

## 4. Примеры использования

### Котировки
```bash
# Американские акции
python agent.py "Цена AAPL"

# Российские акции (автоматически добавит .ME)
python agent.py "Цена акций Газпрома"
```

### Поиск в базе знаний
```bash
python agent.py "Что такое облигации?"
```

### Поиск в интернете
```bash
python agent.py "Последние новости про Apple"
```

### Комбинированный запрос
```bash
python agent.py "Цена AAPL и что говорит база знаний о технологических акциях?"
```

## 5. Управление памятью

**С памятью (для прода):**
```bash
python agent.py --memory --interactive
```

**Без памяти (для тестирования):**
```bash
python agent.py --no-memory --interactive
```

## Формат вывода

Агент выводит структурированные JSON в реальном времени:
- `user_query` - запрос пользователя
- `agent_action` - действие агента (какой инструмент вызывает)
- `tool_result` - результат работы инструмента
- `final_answer` - финальный ответ

## Логи

Все действия логируются в `logs/agent_YYYYMMDD_HHMMSS.log`

## Устранение проблем

### Ошибка импорта модулей
```bash
pip install -r requirements.txt
```

### Ошибка подключения к векторной БД
Убедитесь, что векторная БД создана:
```bash
python create_vector_db.py
```

### Ошибка API ключей
Проверьте `config.py` - все ключи должны быть правильными.

