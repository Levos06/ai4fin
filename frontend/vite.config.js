import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    allowedHosts: ['app.levossadtchi.ru'],  // ← добавляем эту строку
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true, // Поддержка WebSocket для всех /api маршрутов
      }
    }
  }
})
