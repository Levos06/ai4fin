# Создание векторной базы данных

Этот скрипт создает векторную базу данных из всех документов в папке `all_documents/` с использованием семантического чанкования и эмбеддингов через OpenRouter API.

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Настройка

Все настройки находятся в файле `config.py`:

- `OPENROUTER_API_KEY` - API ключ OpenRouter
- `CHUNK_SIZE_TOKENS` - Максимальный размер чанка (512 токенов)
- `CHUNK_OVERLAP_SENTENCES` - Перекрытие в предложениях (2 предложения)
- `BATCH_SIZE` - Размер батча для API (100)

## Запуск

```bash
python create_vector_db.py
```

## Что делает скрипт

1. **Загружает метаданные** из `all_documents.csv`
2. **Обрабатывает все документы** из папки `all_documents/`:
   - Очищает текст
   - Применяет семантическое чанкование с перекрытием в 2 предложения
   - Ограничивает размер чанков до 512 токенов
3. **Генерирует эмбеддинги** через OpenRouter API батчами
4. **Сохраняет в Chroma DB** с метаданными:
   - URL документа
   - Название
   - Тип (статья/документ)
   - Источник (alph/books/fin/fincult/gazprom/moex)
   - Индекс чанка
   - Заголовок раздела
   - Позиция в документе

## Результат

Векторная база данных сохраняется в `vector_db/chroma_db/` и может быть использована для семантического поиска.

## Использование векторной БД

Пример использования:

```python
import chromadb
from chromadb.config import Settings
from openrouter_embeddings import OpenRouterEmbeddings
from config import VECTOR_DB_DIR, OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_BASE_URL

# Подключаемся к БД
client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))
collection = client.get_collection("documents")

# Инициализируем эмбеддинги
embeddings = OpenRouterEmbeddings(
    api_key=OPENROUTER_API_KEY,
    model=OPENROUTER_MODEL,
    base_url=OPENROUTER_BASE_URL
)

# Создаем эмбеддинг для запроса
query = "Что такое инвестиции?"
query_embedding = embeddings.embed_query(query)

# Ищем похожие документы
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5
)

# Выводим результаты
for i, doc in enumerate(results['documents'][0]):
    print(f"\nРезультат {i+1}:")
    print(f"Текст: {doc[:200]}...")
    print(f"Метаданные: {results['metadatas'][0][i]}")
```

