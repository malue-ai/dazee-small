import express from 'express'
import cors from 'cors'

const app = express()
const PORT = process.env.PORT || 3000

// 中间件
app.use(cors())
app.use(express.json())

// ==========================================
// API 路由
// ==========================================

// 健康检查
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

// TODO: 在此添加业务路由
// 示例：
// app.get('/api/items', (req, res) => { ... })
// app.post('/api/items', (req, res) => { ... })
// app.put('/api/items/:id', (req, res) => { ... })
// app.delete('/api/items/:id', (req, res) => { ... })

// ==========================================
// 启动服务
// ==========================================
app.listen(PORT, () => {
  console.log(`
🚀 Server is running!
➜  Local:   http://localhost:${PORT}
➜  API:     http://localhost:${PORT}/api/health
  `)
})