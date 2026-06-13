import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 8173,
    proxy: {
      '/v1':    { target: 'http://localhost:8010', changeOrigin: true },
      '/health': { target: 'http://localhost:8010', changeOrigin: true },
      // FastAPI auto-generated docs
      '/api-backend': { target: 'http://localhost:8010', changeOrigin: true, rewrite: (p) => p.replace(/^\/api-backend/, '') },
    },
  },
})
