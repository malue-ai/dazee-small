# 项目设计文档

## 项目结构说明

本项目采用 **前后端分离** 架构：

```
├── client/          # React 前端 (Vite + TypeScript)
├── server/          # Node.js 后端 (Express + TypeScript)
├── shared/          # 前后端共享的类型定义
└── IDEAS.md         # 本文档
```

## 技术栈

### 前端 (client/)
- **React 18** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具（开发服务器端口 5173）
- **TailwindCSS** - 样式方案

### 后端 (server/)
- **Express** - Web 框架
- **TypeScript** - 类型安全
- **端口 3000**

### 共享 (shared/)
- **types.ts** - 前后端共用的 TypeScript 类型定义

---

## 开发指南

### 启动项目

```bash
# 1. 安装依赖（在 client 和 server 目录分别执行）
cd client && npm install
cd server && npm install

# 2. 启动后端 (端口 3000)
cd server && npm run dev

# 3. 启动前端 (端口 5173)
cd client && npm run dev
```

### 添加新功能的标准流程

1. **定义类型** - 在 `shared/types.ts` 中定义数据类型
2. **实现后端 API** - 在 `server/src/index.ts` 中添加路由
3. **实现前端调用** - 在 `client/src/lib/api.ts` 中添加 API 函数
4. **创建组件** - 在 `client/src/components/` 中创建 UI 组件
5. **创建页面** - 在 `client/src/pages/` 中组装页面

---

## 目录约定

### client/src/

| 目录 | 用途 |
|------|------|
| `components/` | 可复用 UI 组件 |
| `pages/` | 页面级组件 |
| `hooks/` | 自定义 React Hooks |
| `contexts/` | React Context (全局状态) |
| `lib/` | 工具函数、API 客户端 |

### server/src/

| 文件 | 用途 |
|------|------|
| `index.ts` | 入口文件，包含路由定义 |
| `routes/` | 路由模块（可按需拆分） |
| `services/` | 业务逻辑（可按需拆分） |

---

## API 设计规范

- 基础路径：`/api`
- RESTful 风格
- 响应格式：`{ data: T }` 或 `{ error: string }`

示例：
```
GET    /api/items      获取列表
POST   /api/items      创建
PUT    /api/items/:id  更新
DELETE /api/items/:id  删除
```

---

## 样式规范

使用 TailwindCSS，遵循以下原则：
- 组件内直接使用 className
- 复杂样式抽取为组件
- 颜色使用 Tailwind 预设色板
