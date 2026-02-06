import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initApiBaseUrl } from './api'
import './style.css'
import 'markstream-vue/index.css'
import { enableMermaid } from 'markstream-vue'

// 启用 Mermaid 图表渲染
enableMermaid()

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 初始化 API 基础 URL（Tauri 模式下从 Rust 获取后端地址）
initApiBaseUrl().then(() => {
  app.mount('#app')
}).catch((err) => {
  console.error('API 初始化失败:', err)
  app.mount('#app')
})
