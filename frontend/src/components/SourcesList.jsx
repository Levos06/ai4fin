import React from 'react'
import './SourcesList.css'

function SourcesList({ sources }) {
  if (!sources || sources.length === 0) return null

  return (
    <div className="sources-list">
      <h4 className="sources-title">Источники:</h4>
      <ul className="sources-items">
        {sources.map((source, index) => (
          <li key={index} className="source-item">
            <div className="source-main">
              <span className="source-type">{source.type || 'unknown'}</span>
              {source.ticker && (
                <span className="source-ticker">{source.ticker}</span>
              )}
              {source.url && (
                <a href={source.url} target="_blank" rel="noopener noreferrer" className="source-link">
                  {source.url}
                </a>
              )}
            </div>
            {/* Для веб-поиска отображаем кликабельные ссылки справа */}
            {source.type === 'web_search' && source.urls && source.urls.length > 0 && (
              <div className="web-search-links">
                {source.urls.map((urlItem, urlIndex) => (
                  <a
                    key={urlIndex}
                    href={urlItem.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="web-search-link"
                    title={urlItem.title || urlItem.url}
                  >
                    {urlItem.title || urlItem.url}
                  </a>
                ))}
              </div>
            )}
            {/* Для базы знаний отображаем кликабельные ссылки на документы справа */}
            {source.type === 'knowledge_base' && source.documents && source.documents.length > 0 && (
              <div className="web-search-links">
                {source.documents.map((doc, docIndex) => (
                  <a
                    key={docIndex}
                    href={doc.url || '#'}
                    target={doc.url ? "_blank" : undefined}
                    rel={doc.url ? "noopener noreferrer" : undefined}
                    className="web-search-link"
                    title={doc.title || doc.filename}
                    style={!doc.url ? { cursor: 'default', opacity: 0.7 } : {}}
                    onClick={!doc.url ? (e) => e.preventDefault() : undefined}
                  >
                    {doc.title || doc.filename || 'Документ'}
                  </a>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default SourcesList

