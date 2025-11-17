"""
Конфигурация для создания векторной базы данных
"""
import os
from pathlib import Path

# Пути
BASE_DIR = Path(__file__).parent
DOCUMENTS_DIR = BASE_DIR / "all_documents"
METADATA_CSV = BASE_DIR / "all_documents.csv"
VECTOR_DB_DIR = BASE_DIR / "vector_db" / "chroma_db"

# OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_MODEL = "openai/text-embedding-3-large"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Настройки чанкования
CHUNK_SIZE_TOKENS = 324  # Максимальный размер чанка в токенах
CHUNK_OVERLAP_SENTENCES = 2  # Перекрытие в предложениях для SemanticChunker
BATCH_SIZE = 100  # Размер батча для API эмбеддингов

# Настройки SemanticChunker
SEMANTIC_CHUNKER_BUFFER_SIZE = 2  # Размер буфера (перекрытие в предложениях)
SEMANTIC_CHUNKER_BREAKPOINT_THRESHOLD_TYPE = "percentile"  # Тип порога разрыва

# Создаем директорию для векторной БД
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

# Настройки агента
AGENT_LLM_MODEL = "google/gemini-2.5-flash-lite"
AGENT_MAX_ITERATIONS = 40  # Максимальное количество шагов агента
AGENT_VERBOSE = True  # Вывод действий агента в реальном времени

# Tavily API
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "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")
TAVILY_SEARCH_DEPTH = "basic"  # basic или advanced
TAVILY_MAX_RESULTS = 5  # Количество результатов веб-поиска по умолчанию

# Настройки инструментов
STOCK_QUOTES_DEFAULT_PERIOD_DAYS = 30  # Период по умолчанию для котировок
VECTOR_DB_DEFAULT_RESULTS = 5  # Количество результатов поиска в векторной БД

# Логирование
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Сохранение финансовых отчетов
FINANCIAL_REPORTS_DIR = BASE_DIR / "financial_reports"
FINANCIAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Кэш графиков
CHARTS_CACHE_DIR = BASE_DIR / "charts_cache"
CHARTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

