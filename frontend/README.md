# ZenFlux Agent - 前端

基于 Vue 3 + Vite 的现代化 AI 对话界面

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架（Composition API）
- **Vite** - 下一代前端构建工具
- **Vue Router** - 官方路由管理器
- **Pinia** - 状态管理库
- **Axios** - HTTP 客户端
- **Marked** - Markdown 渲染引擎
- **Highlight.js** - 代码语法高亮

## 功能特性

### ✅ 已实现

- **🎨 现代化 UI**
  - 渐变色主题设计
  - 统一的卡片样式组件
  - 流畅的动画效果
  - 响应式布局

- **💬 智能对话**
  - 实时流式响应（SSE）
  - Markdown 渲染
  - 代码语法高亮
  - 消息时间戳
  - 自动滚动

- **📚 知识库管理**
  - 文件拖拽上传
  - 支持多种文件格式（PDF、Word、PowerPoint、Markdown、文本、图片、音视频）
  - 文档列表管理
  - 文档状态监控
  - 统计信息展示

- **🔧 会话管理**
  - 用户 ID 持久化
  - 多对话支持
  - 会话状态查询

### 🚧 开发中

- 断线重连机制
- 多会话管理面板
- 会话历史记录
- 更多工具集成

## 快速开始

### 安装依赖

```bash
cd frontend
npm install
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:3000

### 构建生产版本

```bash
npm run build
```

构建产物将生成在 `dist` 目录

### 预览生产构建

```bash
npm run preview
```

## 项目结构

```
frontend/
├── public/              # 静态资源
├── src/
│   ├── api/            # API 接口封装
│   │   └── axios.js    # Axios 配置
│   ├── components/     # 公共组件
│   │   ├── Card.vue            # 统一卡片组件
│   │   ├── MarkdownRenderer.vue # Markdown 渲染器
│   │   └── KnowledgeUpload.vue  # 知识库上传组件
│   ├── router/         # 路由配置
│   │   └── index.js
│   ├── stores/         # Pinia 状态管理
│   │   ├── chat.js     # 聊天状态
│   │   └── knowledge.js # 知识库状态
│   ├── views/          # 页面组件
│   │   └── ChatView.vue # 主聊天界面
│   ├── App.vue         # 根组件
│   ├── main.js         # 入口文件
│   └── style.css       # 全局样式
├── index.html          # HTML 模板
├── vite.config.js      # Vite 配置
└── package.json        # 依赖配置
```

## 组件说明

### Card 组件

统一的卡片样式组件，支持多种变体：

```vue
<Card title="标题" variant="primary">
  内容
</Card>
```

变体类型：
- `default` - 默认样式
- `primary` - 主色调（蓝紫色左边框）
- `success` - 成功（绿色左边框）
- `warning` - 警告（橙色左边框）
- `error` - 错误（红色左边框）

### MarkdownRenderer 组件

支持 Markdown 渲染和代码高亮：

```vue
<MarkdownRenderer :content="markdownText" />
```

特性：
- 完整的 Markdown 语法支持
- 代码语法高亮
- 表格、列表、引用
- 图片、链接

### KnowledgeUpload 组件

知识库文档管理：

```vue
<KnowledgeUpload :user-id="userId" />
```

功能：
- 拖拽上传文件
- 批量上传
- 文档列表展示
- 文档删除
- 统计信息

## API 接口

### 聊天接口

```javascript
// 发送消息（同步）
await chatStore.sendMessage(content, conversationId)

// 发送消息（流式）
await chatStore.sendMessageStream(content, conversationId, (event) => {
  // 处理事件
})

// 获取会话状态
await chatStore.getSessionStatus(sessionId)

// 获取用户会话列表
await chatStore.getUserSessions()
```

### 知识库接口

```javascript
// 上传文档
await knowledgeStore.uploadDocument(userId, file, metadata)

// 列出文档
await knowledgeStore.listDocuments(userId)

// 删除文档
await knowledgeStore.deleteDocument(userId, documentId)

// 获取统计信息
await knowledgeStore.getStats(userId)

// 检索知识库
await knowledgeStore.retrieve(userId, query, topK)
```

## 开发指南

### 添加新页面

1. 在 `src/views/` 创建新的 `.vue` 文件
2. 在 `src/router/index.js` 添加路由配置

### 添加新组件

1. 在 `src/components/` 创建组件文件
2. 在需要的地方导入并使用

### 状态管理

使用 Pinia 管理全局状态，在 `src/stores/` 目录下创建 store：

```javascript
import { defineStore } from 'pinia'

export const useMyStore = defineStore('my-store', {
  state: () => ({ /* ... */ }),
  actions: { /* ... */ }
})
```

## 环境变量

开发环境（`.env.development`）：
```
VITE_API_BASE_URL=http://localhost:8000/api
```

生产环境（`.env.production`）：
```
VITE_API_BASE_URL=/api
```

## 部署说明

### 使用 Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /path/to/dist;
    index index.html;

    # 前端路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## 注意事项

- 确保后端服务运行在 `http://localhost:8000`
- 开发时使用 `npm run dev`，Vite 会自动代理 API 请求
- 生产构建后需要配置 Nginx 等服务器来处理 API 代理
- SSE 连接需要关闭 Nginx 缓冲：`proxy_buffering off;`

## 浏览器支持

- Chrome/Edge (最新版本)
- Firefox (最新版本)
- Safari (最新版本)

## License

MIT
