"""
Сервис для управления сессиями и историей диалогов
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import uuid

# Добавляем корневую директорию в путь
ROOT_DIR = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import BASE_DIR

# Директория для сессий
SESSIONS_DIR = BASE_DIR / "backend" / "sessions"


class SessionService:
    """Сервис для управления сессиями"""
    
    def __init__(self):
        self.sessions_dir = SESSIONS_DIR
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, Dict] = {}
    
    def create_session(self) -> str:
        """Создать новую сессию"""
        session_id = str(uuid.uuid4())
        session_data = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "message_count": 0,
            "last_message_at": None,
            "title": "Новый диалог"  # Устанавливаем название по умолчанию
        }
        self.sessions[session_id] = session_data
        self._save_session(session_id, session_data)
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None):
        """Добавить сообщение в сессию"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "session_id": session_id,
                "created_at": datetime.now().isoformat(),
                "messages": [],
                "last_message_at": None,
                "message_count": 0,
                "title": "Новый диалог"  # Устанавливаем название по умолчанию
            }
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        # Извлекаем источники из metadata и добавляем в сообщение
        if metadata and "sources" in metadata:
            message["sources"] = metadata["sources"]
        
        self.sessions[session_id]["messages"].append(message)
        self.sessions[session_id]["last_message_at"] = datetime.now().isoformat()
        self.sessions[session_id]["message_count"] = len(self.sessions[session_id]["messages"])
        
        # Устанавливаем название диалога из первого сообщения пользователя
        # Обновляем title если он None или "Новый диалог"
        current_title = self.sessions[session_id].get("title")
        if role == "user" and (current_title is None or current_title == "Новый диалог"):
            # Берем первые 15 символов первого запроса
            title = content.strip()[:15]
            if len(content.strip()) > 15:
                title += "..."
            self.sessions[session_id]["title"] = title
        
        self._save_session(session_id, self.sessions[session_id])
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Получить данные сессии"""
        # Сначала проверяем в памяти (самый быстрый способ)
        if session_id in self.sessions:
            session_data = self.sessions[session_id]
            # Извлекаем источники из metadata для всех сообщений (для совместимости)
            messages = session_data.get("messages", [])
            for msg in messages:
                if "sources" not in msg and msg.get("metadata", {}).get("sources"):
                    msg["sources"] = msg["metadata"]["sources"]
            return session_data
        
        # Пытаемся загрузить из файла
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    # Добавляем message_count если его нет
                    if "message_count" not in session_data:
                        session_data["message_count"] = len(session_data.get("messages", []))
                    # Добавляем title если его нет (из первого сообщения пользователя)
                    if "title" not in session_data or session_data.get("title") is None:
                        messages = session_data.get("messages", [])
                        for msg in messages:
                            if msg.get("role") == "user":
                                content = msg.get("content", "").strip()
                                title = content[:15] if content else "Новый диалог"
                                if len(content) > 15:
                                    title += "..."
                                session_data["title"] = title
                                break
                        if "title" not in session_data:
                            session_data["title"] = "Новый диалог"
                    
                    # Извлекаем источники из metadata для всех сообщений (для совместимости со старыми сессиями)
                    messages = session_data.get("messages", [])
                    for msg in messages:
                        if "sources" not in msg and msg.get("metadata", {}).get("sources"):
                            msg["sources"] = msg["metadata"]["sources"]
                    
                    # Кэшируем в памяти
                    self.sessions[session_id] = session_data
                    return session_data
            except Exception as e:
                # Логируем ошибку, но не падаем
                print(f"Error loading session {session_id} from file: {e}")
                return None
        
        return None
    
    def get_all_sessions(self) -> List[Dict]:
        """Получить список всех сессий"""
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    # Добавляем message_count если его нет
                    if "message_count" not in session_data:
                        session_data["message_count"] = len(session_data.get("messages", []))
                    # Добавляем title если его нет (из первого сообщения пользователя)
                    if "title" not in session_data or session_data.get("title") is None:
                        messages = session_data.get("messages", [])
                        for msg in messages:
                            if msg.get("role") == "user":
                                content = msg.get("content", "").strip()
                                title = content[:15] if content else "Новый диалог"
                                if len(content) > 15:
                                    title += "..."
                                session_data["title"] = title
                                break
                        if "title" not in session_data:
                            session_data["title"] = "Новый диалог"
                    sessions.append(session_data)
            except Exception as e:
                # Пропускаем поврежденные файлы
                print(f"Error loading session {session_file}: {e}")
                continue
        
        # Сортируем сессии, обрабатывая None значения
        def get_sort_key(session):
            # Используем last_message_at если есть, иначе created_at
            # Если оба None, используем пустую строку
            last_msg = session.get("last_message_at")
            created = session.get("created_at", "")
            return last_msg if last_msg else created
        
        return sorted(sessions, key=get_sort_key, reverse=True)
    
    def _save_session(self, session_id: str, session_data: Dict):
        """Сохранить сессию в файл"""
        session_file = self.sessions_dir / f"{session_id}.json"
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
    
    def export_session(self, session_id: str, format: str = "json") -> str:
        """Экспортировать сессию в указанном формате"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Сессия {session_id} не найдена")
        
        if format == "json":
            return json.dumps(session, ensure_ascii=False, indent=2)
        elif format == "txt":
            lines = [
                f"Сессия: {session_id}",
                f"Создана: {session.get('created_at', 'N/A')}",
                f"Последнее сообщение: {session.get('last_message_at', 'N/A')}",
                "",
                "=" * 80,
                "История диалога:",
                "=" * 80,
                ""
            ]
            for msg in session.get("messages", []):
                role = "Пользователь" if msg["role"] == "user" else "Ассистент"
                lines.append(f"[{role}] {msg.get('timestamp', 'N/A')}")
                lines.append(msg.get("content", ""))
                lines.append("")
            return "\n".join(lines)
        else:
            raise ValueError(f"Неподдерживаемый формат: {format}")


# Глобальный экземпляр сервиса
session_service = SessionService()

