import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Мобильное приложение бригады — отдельный фронтенд рядом с диспетчерским.
// Бэкенд тот же: относительный /api проксирует vite.
export default defineConfig({
  plugins: [vue()],
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
