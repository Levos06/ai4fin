import React, { useState, useRef, useEffect } from 'react'
import MessageList from './MessageList'
import MessageInput from './MessageInput'
import ToolStepViewer from './ToolStepViewer'
import SessionPanel from './SessionPanel'
import { useWebSocket } from '../hooks/useWebSocket'
import './ChatInterface.css'

function ChatInterface() {
  const [messages, setMessages] = useState([])
  const [currentStep, setCurrentStep] = useState(null)
  const [currentThought, setCurrentThought] = useState(null)
  const [currentToolCall, setCurrentToolCall] = useState(null)
  const [sessionId, setSessionId] = useState(null)
  const useMemory = true  // Память всегда включена
  const [isLoading, setIsLoading] = useState(false)
  const [sessions, setSessions] = useState([])
  const messagesEndRef = useRef(null)

  const handleRefreshSessions = async () => {
    try {
      const { getSessions } = await import('../utils/api')
      const newSessions = await getSessions()
      setSessions(newSessions || [])
    } catch (error) {
      console.error('Error refreshing sessions:', error)
    }
  }

  const { sendMessage, isConnected } = useWebSocket({
    onMessage: (data) => {
      handleWebSocketMessage(data)
    },
    onError: (error) => {
      console.error('WebSocket error:', error)
      setIsLoading(false)
    }
  })

  const handleWebSocketMessage = (data) => {
    const { type, data: messageData } = data

    switch (type) {
      case 'start':
        setIsLoading(true)
        setCurrentStep(null)
        // Очищаем tool call, но НЕ очищаем currentThought при start - он должен оставаться видимым
        setCurrentToolCall(null)
        // setCurrentThought(null)
        if (messageData.session_id) {
          setSessionId(messageData.session_id)
        }
        break

      case 'thought':
        // Разделяем thoughts и tool calls
        console.log('[DEBUG] Received thought:', messageData.text)
        if (messageData.text) {
          if (messageData.text.startsWith('Вызываю')) {
            // Это уведомление о вызове инструмента
            console.log('[DEBUG] Setting currentToolCall to:', messageData.text?.substring(0, 50))
            setCurrentToolCall(messageData.text)
          } else {
            // Это размышление агента
            console.log('[DEBUG] Setting currentThought to:', messageData.text?.substring(0, 50))
            setCurrentThought(messageData.text)
            console.log('[DEBUG] currentThought set successfully')
          }
        } else {
          console.warn('[WARN] Received thought with empty text!')
        }
        break

      case 'thought_remove':
        // Удаляем размышление (используется только при необходимости)
        setCurrentThought(null)
        break

      case 'step':
        // Удаляем уведомление о вызове инструмента после получения результата
        setCurrentToolCall(null)
        // НЕ удаляем thought - мысли должны оставаться видимыми
        // Не устанавливаем currentStep, чтобы не показывать плашку внизу
        // Шаги теперь показываются только как уведомления о вызовах инструментов
        // setCurrentStep(messageData)
        break

      case 'step_update':
        // Обновляем существующий шаг
        setCurrentStep(messageData)
        break


      case 'final':
        setIsLoading(false)
        setCurrentStep(null)
        setCurrentThought(null)  // Удаляем thought только при финальном ответе
        setCurrentToolCall(null)  // Удаляем tool call при финальном ответе
        // Добавляем финальный ответ как новое сообщение
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: messageData.answer,
          isStreaming: false,
          sources: messageData.sources || [],
          steps: messageData.steps || [],
          timestamp: new Date().toISOString()
        }])
        break

      case 'session_created':
      case 'session_updated':
        // Обновляем список сессий
        if (handleRefreshSessions) {
          handleRefreshSessions()
        }
        break

      case 'error':
        setIsLoading(false)
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `Ошибка: ${messageData.error}`,
          isError: true,
          timestamp: new Date().toISOString()
        }])
        break
    }
  }

  const handleSendMessage = async (text) => {
    if (!text.trim() || isLoading) return

    // НЕ очищаем currentThought при отправке сообщения - он должен оставаться видимым
    // setCurrentThought(null)

    // Если sessionId не установлен, создаем новую сессию
    let currentSessionId = sessionId
    if (!currentSessionId) {
      try {
        const { createSession } = await import('../utils/api')
        currentSessionId = await createSession()
        setSessionId(currentSessionId)
        // Обновляем список сессий
        if (handleRefreshSessions) {
          await handleRefreshSessions()
        }
      } catch (error) {
        console.error('Error creating session:', error)
        return
      }
    }

    // Добавляем сообщение пользователя
    const userMessage = {
      role: 'user',
      content: text,
      timestamp: new Date().toISOString()
    }
    setMessages(prev => [...prev, userMessage])

    // Отправляем через WebSocket с гарантированно установленным session_id
    sendMessage({
      type: 'message',
      message: text,
      session_id: currentSessionId,
      use_memory: useMemory
    })
  }

  const handleLoadSession = async (session) => {
    try {
      // Загружаем полные данные сессии через API
      const { getSession } = await import('../utils/api')
      const fullSession = await getSession(session.session_id)
      
      setSessionId(fullSession.session_id)
      
      // Преобразуем сообщения, извлекая источники из metadata (для совместимости со старыми сессиями)
      const messages = (fullSession.messages || []).map(msg => ({
        ...msg,
        sources: msg.sources || msg.metadata?.sources || []
      }))
      
      setMessages(messages)
      
      // При загрузке сессии очищаем память агента через специальное сообщение
      sendMessage({
        type: 'clear_memory',
        session_id: fullSession.session_id
      })
    } catch (error) {
      console.error('Error loading session:', error)
      // Fallback: используем данные из списка
      setSessionId(session.session_id)
      const fallbackMessages = (session.messages || []).map(msg => ({
        ...msg,
        sources: msg.sources || msg.metadata?.sources || []
      }))
      setMessages(fallbackMessages)
    }
  }

  const handleNewSession = async () => {
    try {
      // Создаем новую сессию через API
      const { createSession } = await import('../utils/api')
      const newSessionId = await createSession()
      setSessionId(newSessionId)
      setMessages([])
      setCurrentStep(null)
      setCurrentThought(null)
      setCurrentToolCall(null)
      // Обновляем список сессий
      if (handleRefreshSessions) {
        await handleRefreshSessions()
      }
      // Память будет очищена автоматически при создании новой сессии
    } catch (error) {
      console.error('Error creating new session:', error)
      // Fallback: просто очищаем состояние
      setSessionId(null)
      setMessages([])
      setCurrentStep(null)
      setCurrentThought(null)
      setCurrentToolCall(null)
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentThought, currentToolCall])

  return (
    <div className="chat-interface">
      <SessionPanel
        sessions={sessions}
        currentSessionId={sessionId}
        onLoadSession={handleLoadSession}
        onNewSession={handleNewSession}
        onRefreshSessions={handleRefreshSessions}
      />
      <div className="chat-main">
        <div className="chat-messages-wrapper">
          <div className="chat-messages">
            <MessageList
              messages={messages}
              currentStep={currentStep}
              currentThought={currentThought}
              currentToolCall={currentToolCall}
              isLoading={isLoading}
            />
            <div ref={messagesEndRef} />
          </div>
          {currentStep && (
            <ToolStepViewer step={currentStep} />
          )}
        </div>
          <MessageInput
            onSend={handleSendMessage}
            disabled={isLoading || !isConnected}
            isLoading={isLoading}
          />
      </div>
    </div>
  )
}

export default ChatInterface

