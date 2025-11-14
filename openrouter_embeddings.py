"""
Кастомный класс для работы с эмбеддингами через OpenRouter API
"""
from typing import List, Optional
try:
    from langchain_core.embeddings import Embeddings
except ImportError:
    try:
        from langchain.embeddings.base import Embeddings
    except ImportError:
        from langchain.embeddings import Embeddings
from openai import OpenAI


class OpenRouterEmbeddings(Embeddings):
    """Класс для генерации эмбеддингов через OpenRouter API"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "openai/text-embedding-3-large",
        base_url: str = "https://openrouter.ai/api/v1",
        site_url: Optional[str] = None,
        site_name: Optional[str] = None,
        batch_size: int = 100
    ):
        """
        Инициализация OpenRouter эмбеддингов
        
        Args:
            api_key: API ключ OpenRouter
            model: Модель для эмбеддингов
            base_url: Base URL для API
            site_url: URL сайта (опционально)
            site_name: Название сайта (опционально)
            batch_size: Размер батча для обработки
        """
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model = model
        self.site_url = site_url
        self.site_name = site_name
        self.batch_size = batch_size
    
    def _prepare_headers(self) -> dict:
        """Подготовка заголовков для запроса"""
        headers = {}
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name
        return headers
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Генерация эмбеддингов для списка текстов
        
        Args:
            texts: Список текстов для обработки
            
        Returns:
            Список эмбеддингов
        """
        all_embeddings = []
        headers = self._prepare_headers()
        
        # Обработка батчами
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            try:
                response = self.client.embeddings.create(
                    extra_headers=headers,
                    model=self.model,
                    input=batch,
                    encoding_format="float"
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
            except Exception as e:
                print(f"Ошибка при обработке батча {i//self.batch_size + 1}: {e}")
                # В случае ошибки возвращаем пустые эмбеддинги для этого батча
                all_embeddings.extend([[0.0] * 3072 for _ in batch])  # text-embedding-3-large имеет размерность 3072
        
        return all_embeddings
    
    def embed_query(self, text: str) -> List[float]:
        """
        Генерация эмбеддинга для одного текста (запроса)
        
        Args:
            text: Текст для обработки
            
        Returns:
            Эмбеддинг
        """
        headers = self._prepare_headers()
        
        try:
            response = self.client.embeddings.create(
                extra_headers=headers,
                model=self.model,
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Ошибка при генерации эмбеддинга: {e}")
            # Возвращаем нулевой вектор в случае ошибки
            return [0.0] * 3072  # text-embedding-3-large имеет размерность 3072

