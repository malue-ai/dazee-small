import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      // 代理 API 请求到后端
      '/api': {
        target: 'http://192.168.1.183:8000',
        changeOrigin: true
      }
    }
  }
})

