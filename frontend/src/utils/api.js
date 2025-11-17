/**
 * Утилиты для работы с API
 */
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

/**
 * Получить список всех сессий
 */
export async function getSessions() {
  const response = await api.get('/api/sessions/')
  return response.data
}

/**
 * Получить данные сессии
 */
export async function getSession(sessionId) {
  const response = await api.get(`/api/sessions/${sessionId}`)
  return response.data
}

/**
 * Создать новую сессию
 */
export async function createSession() {
  const response = await api.post('/api/sessions/')
  return response.data.session_id
}

/**
 * Экспортировать сессию
 */
export async function exportSession(sessionId, format = 'json') {
  const response = await api.post(`/api/sessions/${sessionId}/export`, {
    session_id: sessionId,
    format: format
  })
  return response.data
}

