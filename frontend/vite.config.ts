import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../backend/owed/static', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.API_PROXY || 'http://127.0.0.1:8000', changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, '') },
    },
  },
})
