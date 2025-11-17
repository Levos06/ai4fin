"""
Главный файл FastAPI приложения
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .routes import chat, sessions


# Создаем FastAPI приложение
app = FastAPI(
    title="Financial Agent API",
    description="API для финансового AI-агента",
    version="1.0.0"
)

# Настройка CORS для работы с фронтендом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost"],  # React dev server и nginx
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роуты
app.include_router(chat.router)
app.include_router(sessions.router)


@app.get("/")
async def root():
    """Корневой endpoint"""
    return {
        "message": "Financial Agent API",
        "version": "1.0.0",
        "endpoints": {
            "websocket": "/api/chat/ws",
            "chat": "/api/chat/message",
            "sessions": "/api/sessions"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

