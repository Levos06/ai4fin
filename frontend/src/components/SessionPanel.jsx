import React, { useState, useEffect } from 'react'
import { getSessions } from '../utils/api'
import './SessionPanel.css'

function SessionPanel({ sessions, currentSessionId, onLoadSession, onNewSession, onRefreshSessions }) {
  const [localSessions, setLocalSessions] = useState(sessions || [])

  const loadSessions = async () => {
    try {
      const data = await getSessions()
      setLocalSessions(data)
      if (onRefreshSessions) {
        onRefreshSessions(data)
      }
    } catch (error) {
      console.error('Error loading sessions:', error)
    }
  }

  useEffect(() => {
    loadSessions()
    // Обновляем сессии каждые 5 секунд для синхронизации (уменьшили частоту)
    const interval = setInterval(loadSessions, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleNewSession = async () => {
    // НЕ создаем сессию здесь - это делает ChatInterface.handleNewSession
    // Просто вызываем callback, который обработает создание сессии
    if (onNewSession) {
      await onNewSession()
      // После создания сессии обновляем список
      await loadSessions()
    }
  }

  return (
    <div className="session-panel">
      <div className="session-panel-content">
          <div className="session-panel-header">
            <h3>История диалогов</h3>
            <button onClick={handleNewSession} className="new-session-button">
              + Новый
            </button>
          </div>
          <div className="session-list">
            {localSessions.length === 0 ? (
              <div className="no-sessions">Нет сохраненных диалогов</div>
            ) : (
              localSessions.map(session => (
                <div
                  key={session.session_id}
                  className={`session-item ${session.session_id === currentSessionId ? 'active' : ''}`}
                  onClick={() => onLoadSession(session)}
                >
                  <div className="session-item-header">
                    <span className="session-title">
                      {session.title || session.session_id.substring(0, 8) + '...'}
                    </span>
                    <span className="session-time">
                      {session.last_message_at
                        ? new Date(session.last_message_at).toLocaleDateString('ru-RU')
                        : new Date(session.created_at).toLocaleDateString('ru-RU')}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
    </div>
  )
}

export default SessionPanel

