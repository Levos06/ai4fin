import React from 'react'
import Message from './Message'
import './MessageList.css'

function MessageList({ messages, currentStep, currentThought, currentToolCall, isLoading }) {
  return (
    <div className="message-list">
      {messages.length === 0 && (
        <div className="empty-state">
          <h3>Начните диалог</h3>
          <p>Задайте вопрос о финансовых данных, акциях или инвестициях</p>
        </div>
      )}
      {messages.map((message, index) => (
        <Message
          key={index}
          message={message}
          isLast={index === messages.length - 1}
        />
      ))}
      {/* Контейнер для мыслей и уведомлений о вызовах инструментов на одном уровне */}
      {(currentThought || currentToolCall) && (
        <div className="agent-thoughts-container">
          {/* Размышления агента - слева */}
          {currentThought && (
            <div className="agent-thought">
              {currentThought.length > 1000 ? currentThought.substring(0, 1000) + "..." : currentThought}
            </div>
          )}
          {/* Уведомления о вызовах инструментов - справа */}
          {currentToolCall && (
            <div className="agent-thought tool-call">
              {currentToolCall.length > 1000 ? currentToolCall.substring(0, 1000) + "..." : currentToolCall}
            </div>
          )}
        </div>
      )}
      {isLoading && messages.length > 0 && (
        <div className="loading-indicator">
          <div className="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      )}
    </div>
  )
}

export default MessageList

