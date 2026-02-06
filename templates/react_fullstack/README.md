# React 全栈项目模板

一个基于 **Vite + React + TypeScript + TailwindCSS + Express** 的现代化全栈项目脚手架。

## 快速开始

```bash
# 1. 安装依赖
npm install

# 2. 启动开发服务器（前后端同时启动）
npm run dev
```

- 前端访问：http://localhost:5173
- 后端 API：http://localhost:3000/api
- 健康检查：http://localhost:3000/api/health

### 其他命令

```bash
# 仅启动前端
npm run dev:client

# 仅启动后端
npm run dev:server

# 类型检查
npm run check

# 代码格式化
npm run format

# 构建生产版本
npm run build

# 启动生产服务
npm start
```

## 项目结构

```
├── client/              # React 前端
│   ├── index.html       # HTML 入口
│   └── src/
│       ├── App.tsx      # 应用入口（路由配置）
│       ├── main.tsx     # React 渲染入口
│       ├── index.css    # 全局样式（Tailwind + 主题变量）
│       ├── const.ts     # 前端常量
│       ├── components/  # 可复用组件
│       │   ├── ui/      # UI 基础组件（shadcn/ui）
│       │   ├── ErrorBoundary.tsx
│       │   └── StatusCard.tsx
│       ├── pages/       # 页面级组件
│       │   ├── HomePage.tsx
│       │   └── NotFound.tsx
│       ├── hooks/       # 自定义 Hooks
│       │   └── useApi.ts
│       └── contexts/    # React Context
│           └── ThemeContext.tsx
├── server/              # Express 后端
│   └── index.ts         # 服务器入口（包含所有 API 路由）
├── shared/              # 前后端共享代码
│   ├── types.ts         # 共享类型定义
│   └── const.ts         # 共享常量
├── package.json         # 依赖和脚本
├── vite.config.ts       # Vite 配置（含代理设置）
├── tsconfig.json        # TypeScript 配置
└── README.md            # 本文件
```

## 技术栈

| 模块 | 技术 | 版本 |
|------|------|------|
| 前端框架 | React | 19 |
| 构建工具 | Vite | 7 |
| 类型系统 | TypeScript | 5 |
| 样式方案 | TailwindCSS | 4 |
| UI 组件 | shadcn/ui + Radix UI | - |
| 路由 | wouter | 3 |
| 表单 | react-hook-form + zod | - |
| 图表 | recharts | 2 |
| 动画 | framer-motion | 12 |
| 后端框架 | Express | 4 |
| 包管理器 | npm | - |

## 开发指南

### 添加新功能的标准流程

1. **定义类型** - 在 `shared/types.ts` 中定义数据类型
2. **实现后端 API** - 在 `server/index.ts` 中添加路由
3. **实现前端调用** - 在 `client/src/hooks/useApi.ts` 中添加 API 函数
4. **创建组件** - 在 `client/src/components/` 中创建 UI 组件
5. **创建页面** - 在 `client/src/pages/` 中组装页面
6. **添加路由** - 在 `client/src/App.tsx` 中配置路由

### 目录约定

#### client/src/

| 目录 | 用途 | 示例 |
|------|------|------|
| `components/` | 可复用 UI 组件 | Button, Card, Modal |
| `components/ui/` | shadcn/ui 基础组件 | button.tsx, card.tsx |
| `pages/` | 页面级组件 | HomePage, UserPage |
| `hooks/` | 自定义 React Hooks | useApi, useAuth |
| `contexts/` | React Context | ThemeContext |
| `lib/` | 工具函数 | utils.ts, cn() |

#### server/

| 目录/文件 | 用途 |
|-----------|------|
| `index.ts` | 入口文件，包含路由定义 |
| `routes/` | 路由模块（可按需拆分） |
| `services/` | 业务逻辑（可按需拆分） |

## API 设计规范

- 基础路径：`/api`
- RESTful 风格
- 响应格式：`{ data: T }` 或 `{ error: string }`

### 内置 API 示例

```
GET    /api/health        健康检查
POST   /api/auth/login    用户登录
POST   /api/auth/register 用户注册
POST   /api/auth/logout   用户登出
GET    /api/items         获取列表
POST   /api/items         创建项目
```

### 添加新 API

在 `server/index.ts` 中添加路由：

```typescript
// GET 请求示例
app.get("/api/users/:id", (req: Request, res: Response) => {
  const { id } = req.params;
  // TODO: 从数据库获取用户
  res.json({ data: { id, name: "User" } });
});

// POST 请求示例
app.post("/api/users", (req: Request, res: Response) => {
  const { name, email } = req.body;
  if (!name || !email) {
    return res.status(400).json({ error: "缺少必填字段" });
  }
  // TODO: 保存到数据库
  res.status(201).json({ data: { id: "1", name, email } });
});
```

## 主题配置

主题相关配置在 `client/src/index.css` 中：

```css
:root {
  --background: oklch(1 0 0);      /* 背景色 */
  --foreground: oklch(0.145 0 0);  /* 前景色 */
  --primary: oklch(0.205 0 0);     /* 主色调 */
  /* ... 更多变量 */
}

.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  /* ... 暗色主题变量 */
}
```

### 切换主题

在 `App.tsx` 中配置 ThemeProvider：

```tsx
<ThemeProvider
  defaultTheme="light"  // 默认主题
  switchable            // 启用主题切换
>
```

使用 `useTheme` hook 切换主题：

```tsx
const { theme, setTheme } = useTheme();
setTheme("dark");  // 切换到暗色主题
```

## UI 组件使用

本项目集成了 shadcn/ui 组件库，位于 `client/src/components/ui/`。

### 已安装组件

- button, card, tooltip
- sonner (toast 通知)
- 更多 Radix UI 原语组件

### 添加新组件

参考 shadcn/ui 文档，手动复制组件代码到 `components/ui/` 目录。

## 常见问题

### Q: 前端如何调用后端 API？

使用 `client/src/hooks/useApi.ts` 中的 hook：

```tsx
import { api } from "@/lib/api";
import { useApi } from "@/hooks/useApi";

const { data, loading, error, refetch } = useApi(() => api.getItems());
```

### Q: 如何添加环境变量？

- 前端：在 `.env` 中添加 `VITE_` 前缀变量，通过 `import.meta.env.VITE_XXX` 访问
- 后端：直接使用 `process.env.XXX`

### Q: 生产环境如何部署？

```bash
# 1. 构建
npm run build

# 2. 启动（会同时服务前端静态文件和后端 API）
npm start
```

### Q: 如何连接数据库？

在 `server/index.ts` 中添加数据库连接，推荐使用：
- PostgreSQL: `pg` + `drizzle-orm`
- MongoDB: `mongoose`
- SQLite: `better-sqlite3`

