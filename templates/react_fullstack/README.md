# React 全栈项目模板

一个基于 **Vite + React + TypeScript + TailwindCSS** 的现代化全栈项目脚手架。

## 快速开始

```bash
# 1. 安装后端依赖并启动
cd server
npm install
npm run dev

# 2. 安装前端依赖并启动（新开一个终端）
cd client
npm install
npm run dev
```

前端访问：http://localhost:5173
后端 API：http://localhost:3000/api

## 项目结构

```
├── client/          # React 前端
│   ├── src/
│   │   ├── components/   # 组件
│   │   ├── pages/        # 页面
│   │   ├── hooks/        # 自定义 Hooks
│   │   ├── lib/          # 工具函数
│   │   └── contexts/     # React Context
│   └── ...
├── server/          # Express 后端
│   └── src/
│       └── index.ts      # 入口文件
├── shared/          # 共享类型定义
│   └── types.ts
├── IDEAS.md         # 设计文档
└── README.md
```

## 技术栈

| 模块 | 技术 |
|------|------|
| 前端框架 | React 18 |
| 构建工具 | Vite 5 |
| 类型系统 | TypeScript |
| 样式方案 | TailwindCSS |
| 后端框架 | Express |
| 运行时 | Node.js |
