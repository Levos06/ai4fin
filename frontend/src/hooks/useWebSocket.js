import { useEffect, useRef, useState } from 'react'

export function useWebSocket({ onMessage, onError }) {
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)

  const connect = () => {
    // В режиме разработки используем прямой URL, в продакшене - через proxy
    const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    const wsUrl = isDev 
      ? 'ws://localhost:8000/api/chat/ws'
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/chat/ws`
    
    try {
      const ws = new WebSocket(wsUrl)
      
      ws.onopen = () => {
        setIsConnected(true)
        console.log('WebSocket connected')
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
          reconnectTimeoutRef.current = null
        }
      }
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'pong') {
            // Игнорируем pong сообщения
            return
          }
          onMessage(data)
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        onError(error)
      }
      
      ws.onclose = () => {
        setIsConnected(false)
        console.log('WebSocket disconnected')
        
        // Попытка переподключения через 3 секунды
        if (!reconnectTimeoutRef.current) {
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null
            connect()
          }, 3000)
        }
      }
      
      wsRef.current = ws
    } catch (error) {
      console.error('Error creating WebSocket:', error)
      onError(error)
    }
  }

  useEffect(() => {
    connect()
    
    // Ping для поддержания соединения
    const pingInterval = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000) // Каждые 30 секунд
    
    return () => {
      clearInterval(pingInterval)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const sendMessage = (data) => {
    console.log('[DEBUG] sendMessage called with:', data)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const messageStr = JSON.stringify(data)
      console.log('[DEBUG] Sending WebSocket message:', messageStr)
      wsRef.current.send(messageStr)
    } else {
      console.error('[ERROR] WebSocket is not connected. State:', wsRef.current?.readyState)
      onError(new Error('WebSocket is not connected'))
    }
  }

  return {
    sendMessage,
    isConnected
  }
}

