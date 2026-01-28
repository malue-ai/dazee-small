# React 全栈项目模板

一个基于 **Vite + React + TypeScript + TailwindCSS** 的现代化全栈项目脚手架。

## 快速开始

```bash
# 1. 安装依赖
npm install

# 2. 启动开发服务器（前后端同时启动）
npm run dev
```

前端访问：http://localhost:5173
后端 API：http://localhost:3000/api

### 其他命令

```bash
# 仅启动前端
npm run dev:client

# 仅启动后端
npm run dev:server

# 类型检查
npm run check

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
│       ├── components/  # 组件
│       │   └── ui/      # UI 基础组件
│       ├── pages/       # 页面
│       ├── hooks/       # 自定义 Hooks
│       ├── lib/         # 工具函数和 API 客户端
│       └── contexts/    # React Context
├── server/              # Express 后端
│   └── index.ts         # 服务器入口
├── shared/              # 前后端共享代码
│   ├── types.ts         # 共享类型定义
│   └── const.ts         # 共享常量
├── package.json         # 依赖和脚本（根目录）
├── vite.config.ts       # Vite 配置
├── tsconfig.json        # TypeScript 配置
├── IDEAS.md             # 设计文档
└── README.md
```

## 技术栈

| 模块 | 技术 |
|------|------|
| 前端框架 | React 19 |
| 构建工具 | Vite 7 |
| 类型系统 | TypeScript 5 |
| 样式方案 | TailwindCSS 4 |
| UI 组件 | shadcn/ui + Radix UI |
| 后端框架 | Express |
| 运行时 | Node.js |
| 包管理器 | pnpm |
