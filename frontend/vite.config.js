import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,

    proxy: {
      // /api/auth/* → auth service :5001
      '/api/auth': {
        target: process.env.VITE_AUTH_URL || 'http://localhost:5001',
        changeOrigin: true,
      },
      // /api/project/* → project service :5002
      '/api/project': {
        target: process.env.VITE_PROJECT_URL || 'http://localhost:5002',
        changeOrigin: true,
      },
      // /api/query/* → query service :5003
      '/api/query': {
        target: process.env.VITE_QUERY_URL || 'http://localhost:5003',
        changeOrigin: true,
      },
    },
  },
})