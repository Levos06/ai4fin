"""
Routes для управления сессиями
"""
from fastapi import APIRouter, HTTPException
from typing import List

from api.services.session_service import session_service
from api.models.schemas import SessionInfo, ExportRequest


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/", response_model=List[SessionInfo])
async def get_all_sessions():
    """Получить список всех сессий"""
    sessions = session_service.get_all_sessions()
    return sessions


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Получить данные конкретной сессии"""
    session = session_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    return session


@router.post("/")
async def create_session():
    """Создать новую сессию"""
    session_id = session_service.create_session()
    return {"session_id": session_id}


@router.post("/{session_id}/export")
async def export_session(session_id: str, request: ExportRequest):
    """Экспортировать сессию"""
    try:
        content = session_service.export_session(session_id, request.format)
        return {
            "session_id": session_id,
            "format": request.format,
            "content": content
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

