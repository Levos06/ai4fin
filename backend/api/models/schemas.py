"""
Pydantic схемы для запросов и ответов API
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatMessage(BaseModel):
    """Сообщение в чате"""
    role: str  # "user" или "assistant"
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    """Запрос на обработку сообщения"""
    message: str
    session_id: Optional[str] = None
    use_memory: bool = True


class AgentStep(BaseModel):
    """Шаг работы агента"""
    step_number: int
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    timestamp: datetime


class ChatResponse(BaseModel):
    """Ответ агента"""
    message: str
    session_id: str
    steps: List[AgentStep] = []
    sources: List[Dict[str, Any]] = []
    timestamp: datetime


class StreamChunk(BaseModel):
    """Чанк стриминга"""
    type: str  # "step", "token", "final", "error"
    data: Dict[str, Any]
    timestamp: datetime


class SessionInfo(BaseModel):
    """Информация о сессии"""
    session_id: str
    created_at: str  # ISO format string
    message_count: int = 0
    last_message_at: Optional[str] = None  # ISO format string
    title: Optional[str] = None  # Название диалога (первые 10 символов первого запроса)


class ExportRequest(BaseModel):
    """Запрос на экспорт диалога"""
    session_id: str
    format: str = "json"  # "json" или "txt"

