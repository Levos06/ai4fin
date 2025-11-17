import React, { useState, useEffect, useRef } from 'react'
import './ExportButton.css'

function ExportButton({ message }) {
  const [showMenu, setShowMenu] = useState(false)
  const [showCopyNotification, setShowCopyNotification] = useState(false)
  const containerRef = useRef(null)

  // Закрываем меню при клике вне его
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setShowMenu(false)
      }
    }

    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showMenu])

  const handleExport = async (format) => {
    try {
      let content = ''
      let filename = ''
      let mimeType = ''

      if (format === 'json') {
        content = JSON.stringify({
          message: message.content,
          sources: message.sources || [],
          timestamp: message.timestamp
        }, null, 2)
        filename = `chat-export-${Date.now()}.json`
        mimeType = 'application/json'
      } else if (format === 'txt') {
        content = `Сообщение от ${new Date(message.timestamp).toLocaleString('ru-RU')}\n\n`
        content += `${message.content}\n\n`
        if (message.sources && message.sources.length > 0) {
          content += 'Источники:\n'
          message.sources.forEach((source, index) => {
            content += `${index + 1}. ${source.type || 'unknown'}`
            if (source.ticker) content += ` - ${source.ticker}`
            if (source.url) content += ` - ${source.url}`
            content += '\n'
          })
        }
        filename = `chat-export-${Date.now()}.txt`
        mimeType = 'text/plain'
      }

      // Создаем blob и скачиваем
      const blob = new Blob([content], { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      setShowMenu(false)
    } catch (error) {
      console.error('Export error:', error)
      alert('Ошибка при экспорте')
    }
  }

  const handleCopy = () => {
    try {
      // Используем execCommand - не требует разрешения браузера
      const textarea = document.createElement('textarea')
      textarea.value = message.content
      textarea.style.position = 'fixed'
      textarea.style.left = '-999999px'
      textarea.style.top = '-999999px'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      
      textarea.focus()
      textarea.select()
      textarea.setSelectionRange(0, 99999) // Для мобильных устройств
      
      const successful = document.execCommand('copy')
      document.body.removeChild(textarea)
      
      if (successful) {
        setShowCopyNotification(true)
        setTimeout(() => setShowCopyNotification(false), 2000)
      }
    } catch (err) {
      console.error('Copy error:', err)
      // В случае ошибки просто не показываем уведомление
    }
  }

  return (
    <div className="export-buttons-container">
      {showCopyNotification && (
        <div className="copy-notification">
          Скопировано в буфер обмена
        </div>
      )}
      <button
        className="copy-button"
        onClick={handleCopy}
        title="Копировать текст"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      </button>
      <div className="export-button-container" ref={containerRef}>
        <button
          className="export-button"
          onClick={() => setShowMenu(!showMenu)}
          title="Экспорт"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
        </button>
        {showMenu && (
          <div className="export-menu">
            <button onClick={() => handleExport('json')}>Экспорт JSON</button>
            <button onClick={() => handleExport('txt')}>Экспорт TXT</button>
          </div>
        )}
      </div>
    </div>
  )
}

export default ExportButton

