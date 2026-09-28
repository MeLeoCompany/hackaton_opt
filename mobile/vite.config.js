import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Мобильное приложение бригады — отдельный фронтенд рядом с диспетчерским.
// Бэкенд тот же: относительный /api проксирует vite.
export default defineConfig({
  plugins: [vue()],
  // на сервере приложение отдаётся по /mobile/, локально — из корня dev-сервера
  base: process.env.VITE_BASE || '/',
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
