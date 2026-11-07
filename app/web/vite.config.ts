import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend runs on 127.0.0.1:8000 during development.
// In production the same build is served by FastAPI from /demo/, and the
// homepage in site/ is served from /.
const apiTarget = 'http://127.0.0.1:8000'

export default defineConfig({
  base: '/demo/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      '/health': { target: apiTarget, changeOrigin: true },
    },
  },
})
