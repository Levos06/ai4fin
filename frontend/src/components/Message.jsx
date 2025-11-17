import React, { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import SourcesList from './SourcesList'
import ExportButton from './ExportButton'
import ChartViewer from './ChartViewer'
import './Message.css'

function Message({ message, isLast }) {
  const [showSources, setShowSources] = useState(false)

  const isUser = message.role === 'user'
  const isError = message.isError
  
  // Проверяем, есть ли графики в сообщении
  const hasCharts = !isUser && message.sources && message.sources.some(
    source => source.type === 'visualization' && source.chart_html
  )

  return (
    <div className={`message ${isUser ? 'message-user' : 'message-assistant'} ${isError ? 'message-error' : ''}`}>
      <div className={`message-content ${hasCharts ? 'message-with-chart' : ''}`}>
        <div className="message-header">
          <span className="message-role">
            {isUser ? 'Вы' : 'Ассистент'}
          </span>
          {message.timestamp && (
            <span className="message-time">
              {new Date(message.timestamp).toLocaleTimeString('ru-RU', {
                hour: '2-digit',
                minute: '2-digit'
              })}
            </span>
          )}
        </div>
        <div className="message-text">
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          )}
          {message.isStreaming && (
            <span className="streaming-cursor">|</span>
          )}
        </div>
        {/* Отображаем графики из источников */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <>
            {message.sources
              .filter(source => source.type === 'visualization' && source.chart_html)
              .map((source, index) => (
                <ChartViewer
                  key={index}
                  chartHtml={source.chart_html}
                  title={source.title}
                  chartType={source.chart_type}
                />
              ))}
          </>
        )}
        {!isUser && (
          <div className="message-footer">
            <button
              className="sources-toggle"
              onClick={() => setShowSources(!showSources)}
              disabled={!message.sources || message.sources.length === 0}
            >
              {showSources ? 'Скрыть' : 'Показать'} источники ({message.sources?.length || 0})
            </button>
            <ExportButton message={message} />
          </div>
        )}
        {showSources && message.sources && message.sources.length > 0 && (
          <SourcesList sources={message.sources} />
        )}
      </div>
    </div>
  )
}

export default Message

