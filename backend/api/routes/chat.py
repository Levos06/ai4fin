"""
Routes для чата и WebSocket
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Any
import json
from datetime import datetime

from ..services.agent_service import agent_service
from ..services.session_service import session_service
from ..models.schemas import ChatRequest, StreamChunk


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для стриминга ответов агента"""
    await websocket.accept()
    
    session_id = None
    use_memory = True
    
    try:
        while True:
            # Получаем сообщение от клиента
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            message_type = message_data.get("type")
            
            if message_type == "message":
                # Новое сообщение пользователя
                query = message_data.get("message", "")
                provided_session_id = message_data.get("session_id")
                
                # Если session_id не передан, создаем новую сессию (fallback)
                # Но обычно session_id должен быть передан из frontend
                if not provided_session_id:
                    session_id = session_service.create_session()
                    is_new_session = True
                else:
                    session_id = provided_session_id
                    # Проверяем, существует ли сессия
                    session = session_service.get_session(session_id)
                    # Если сессия существует, проверяем, первое ли это сообщение
                    # Если не существует - это ошибка, но создаем сессию для совместимости
                    # (в нормальном flow сессия должна существовать)
                    if session is None:
                        # Сессия не найдена - это может быть race condition
                        # Создаем новую сессию, но логируем предупреждение
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Session {session_id} not found, creating new one")
                        session_id = session_service.create_session()
                        is_new_session = True
                    else:
                        # Сессия существует - проверяем, первое ли это сообщение
                        is_new_session = len(session.get("messages", [])) == 0
                
                use_memory = message_data.get("use_memory", True)
                
                # ВАЖНО: Очищаем память перед началом нового диалога
                # Проверяем, первое ли это сообщение в сессии (ДО добавления нового сообщения)
                session = session_service.get_session(session_id)
                is_first_message = is_new_session or (session and len(session.get("messages", [])) == 0)
                
                # Очищаем память агента перед новым диалогом
                # Для новой сессии или первого сообщения - создаем нового агента с чистой памятью
                agent_service.get_agent(session_id, use_memory, clear_memory=is_first_message)
                
                # Сохраняем сообщение пользователя
                session_service.add_message(session_id, "user", query)
                
                # Отправляем информацию о новой сессии, если она только что создана
                if is_new_session:
                    await websocket.send_json({
                        "type": "session_created",
                        "data": {
                            "session_id": session_id,
                            "timestamp": datetime.now().isoformat()
                        }
                    })
                
                # Стримим ответ агента
                async for chunk in agent_service.stream_agent_response(query, session_id, use_memory):
                    await websocket.send_json(chunk)
                    
                    # Если это финальный ответ, сохраняем его
                    if chunk.get("type") == "final":
                        answer = chunk.get("data", {}).get("answer", "")
                        session_service.add_message(
                            session_id, 
                            "assistant", 
                            answer,
                            metadata={"sources": chunk.get("data", {}).get("sources", [])}
                        )
                        
                        # Отправляем уведомление об обновлении сессии
                        await websocket.send_json({
                            "type": "session_updated",
                            "data": {
                                "session_id": session_id,
                                "timestamp": datetime.now().isoformat()
                            }
                        })
            
            elif message_type == "clear_memory":
                # Очистка памяти агента для сессии
                session_id = message_data.get("session_id")
                if session_id:
                    agent_service.clear_agent_memory(session_id)
                    await websocket.send_json({
                        "type": "memory_cleared",
                        "data": {
                            "session_id": session_id,
                            "timestamp": datetime.now().isoformat()
                        }
                    })
            
            elif message_type == "ping":
                # Ping для поддержания соединения
                await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        error_data = {
            "type": "error",
            "data": {
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
        }
        try:
            await websocket.send_json(error_data)
        except:
            pass


@router.post("/message")
async def chat_message(request: ChatRequest):
    """REST endpoint для отправки сообщения (без стриминга)"""
    session_id = request.session_id or session_service.create_session()
    
    # Сохраняем сообщение пользователя
    session_service.add_message(session_id, "user", request.message)
    
    # Получаем ответ агента
    response_data = {
        "message": "",
        "session_id": session_id,
        "steps": [],
        "sources": [],
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        agent = agent_service.get_agent(session_id, request.use_memory)
        result = agent.run(request.message)
        
        response_data["message"] = result.get("answer", "")
        response_data["sources"] = result.get("sources", [])
        response_data["steps"] = result.get("steps", [])
        
        # Сохраняем ответ
        session_service.add_message(
            session_id,
            "assistant",
            response_data["message"],
            metadata={"sources": response_data["sources"]}
        )
        
    except Exception as e:
        response_data["error"] = str(e)
    
    return response_data

