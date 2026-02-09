import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // Tauri 需要固定端口
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true
      }
    }
  },
  // 清除 Tauri 开发时的控制台警告
  clearScreen: false,
  // 环境变量前缀
  envPrefix: ['VITE_', 'TAURI_'],
  build: {
    // Tauri 在 Windows 上使用 Chromium，在 macOS/Linux 上使用 WebKit
    // 需要针对 ES2021 构建
    target: process.env.TAURI_PLATFORM === 'windows' ? 'chrome105' : 'safari14',
    // 在 debug 构建时不压缩
    minify: !process.env.TAURI_DEBUG ? 'esbuild' : false,
    // 在 debug 构建时生成 sourcemap
    sourcemap: !!process.env.TAURI_DEBUG,
  },
})

