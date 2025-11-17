import React, { useEffect, useRef } from 'react'
import './ChartViewer.css'

function ChartViewer({ chartHtml, title, chartType }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (containerRef.current && chartHtml) {
      // Очищаем контейнер
      containerRef.current.innerHTML = ''
      
      // Создаем временный контейнер для парсинга HTML
      const tempDiv = document.createElement('div')
      tempDiv.innerHTML = chartHtml
      
      // Находим div с графиком (Plotly создает div с id начинающимся с "chart_")
      const chartDiv = tempDiv.querySelector('[id^="chart_"]')
      
      if (chartDiv) {
        // Клонируем div с графиком
        const clonedDiv = chartDiv.cloneNode(true)
        const chartId = clonedDiv.id || chartDiv.id
        containerRef.current.appendChild(clonedDiv)
        
        // Извлекаем скрипты из HTML
        const scripts = tempDiv.querySelectorAll('script')
        
        // Сначала загружаем внешние скрипты (Plotly CDN)
        const externalScripts = Array.from(scripts).filter(s => s.src)
        const inlineScripts = Array.from(scripts).filter(s => !s.src)
        
        // Загружаем внешние скрипты
        let loadedExternal = 0
        const loadExternalScripts = () => {
          if (externalScripts.length === 0) {
            // Нет внешних скриптов, сразу выполняем встроенные
            executeInlineScripts()
            return
          }
          
          externalScripts.forEach((script) => {
            const existingScript = document.querySelector(`script[src="${script.src}"]`)
            if (!existingScript) {
              const newScript = document.createElement('script')
              newScript.src = script.src
              newScript.async = false
              newScript.onload = () => {
                loadedExternal++
                if (loadedExternal === externalScripts.length) {
                  // Все внешние скрипты загружены, теперь выполняем встроенные
                  executeInlineScripts()
                }
              }
              newScript.onerror = () => {
                loadedExternal++
                if (loadedExternal === externalScripts.length) {
                  executeInlineScripts()
                }
              }
              document.head.appendChild(newScript)
            } else {
              loadedExternal++
              if (loadedExternal === externalScripts.length) {
                executeInlineScripts()
              }
            }
          })
        }
        
        // Выполняем встроенные скрипты (инициализация Plotly)
        const executeInlineScripts = () => {
          // Небольшая задержка, чтобы убедиться, что div добавлен в DOM
          setTimeout(() => {
            inlineScripts.forEach((script) => {
              const newScript = document.createElement('script')
              newScript.textContent = script.textContent
              // Добавляем скрипт в body, чтобы он выполнился
              document.body.appendChild(newScript)
            })
          }, 100)
        }
        
        // Начинаем загрузку
        loadExternalScripts()
      } else {
        // Fallback: вставляем весь HTML
        containerRef.current.innerHTML = chartHtml
      }
    }
  }, [chartHtml])

  if (!chartHtml) return null

  return (
    <div className="chart-viewer">
      {title && <h4 className="chart-title">{title}</h4>}
      <div 
        ref={containerRef} 
        className="chart-container"
        data-chart-type={chartType}
      />
    </div>
  )
}

export default ChartViewer

