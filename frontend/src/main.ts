import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initApiBaseUrl } from './api'
import { appLog } from './utils/logger'
import './style.css'
import 'markstream-vue/index.css'
import { enableMermaid } from 'markstream-vue'

// 启用 Mermaid 图表渲染
enableMermaid()

appLog.info('应用启动中...')
appLog.info(`运行环境: ${import.meta.env.MODE}`)
appLog.info(`User-Agent: ${navigator.userAgent.slice(0, 80)}`)

// 全局拖拽防护：阻止浏览器默认的文件拖放导航行为
// 仅处理从系统拖入的外部文件（内部工作区拖拽已改为 mouse 事件方案）
document.addEventListener('dragover', (e) => e.preventDefault())
document.addEventListener('drop', (e) => e.preventDefault())

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 立即挂载（让 App.vue 内置的 SplashScreen 尽快显示，避免白屏）
app.mount('#app')
appLog.info('应用挂载完成')

// API 初始化在后台进行（SplashScreen 会通过 waitForBackendReady() 等待后端就绪）
initApiBaseUrl().catch((err) => {
  appLog.error('API 初始化失败', err)
})
