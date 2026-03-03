# Cursor 规则说明

## 📋 规则概览

| 规则 | 说明 | 应用范围 |
|------|------|----------|
| **00-project-setup** | 项目环境配置（Python 虚拟环境、运行命令） | 全局 |
| **01-general-conventions** | Python/FastAPI 核心规范（异步、数据库、性能优化、API 设计） | 全局 |
| **02-api-development** | 三层架构（Router/Service/Model） | API 开发 |
| **03-testing** | 测试规范（pytest、Mock、AAA） | 测试 |
| **04-logging** | 日志规范（上下文追踪） | 全局 |
| **05-documentation** | 文档编写规范 | 全局 |
| **06-configuration** | 配置文件规范（YAML、环境变量） | 配置 |
| **07-frontend** | Vue 3 + TypeScript 前端开发规范 | `frontend/**` |
| **08-styling** | TailwindCSS 样式规范 | `frontend/**` |
| **13-brand-neutrality** | 品牌中立规范（禁止竞品框架名） | 全局 |
| **14-agent-design-philosophy** | LLM-First 设计理念（强制） | 全局 |
| **15-architecture-cleanup** | 架构清理规范（意图识别 V9.0） | 全局 |
| **16-prompt-engineering** | 系统提示词编写规范 | `prompts/**`, `instances/**` |
| **17-design-system** | 前端设计系统（Apple Liquid + 琥珀黄） | `frontend/**` |
| **17-llm-first-architecture** | LLM-First 架构原则 | 全局 |
| **18-context-engineering** | **上下文工程极限优化规范（核心）** | `core/context/**`, `tools/**`, `skills/**` |

## 🎯 设计原则

1. **简洁优先**：每个规则 ≤ 100 行
2. **无重复**：核心概念在 01 统一定义
3. **职责明确**：每个规则只管自己的领域
4. **实用至上**：只保留真正有用的内容

## 📖 规则说明

### 01-general-conventions（核心规范）
- **必读**：所有开发人员必须遵守
- 包含：异步编程、错误处理、数据模型、数据库 ORM、性能优化、API 设计
- 作用：避免在其他规则中重复基础内容

### 02-api-development（架构规范）
- 三层架构原则：Router → Service → Model
- 核心：业务逻辑只写一次，HTTP 和 gRPC 复用

### 03-testing（测试规范）
- 测试组织、命名、AAA 模式
- Mock 使用和异步测试

### 04-logging（日志规范）
- 统一日志系统使用
- 上下文追踪（request_id/session_id/user_id）
- 性能监控

### 05-documentation（文档规范）
- README 必备章节
- API 文档格式
- 维护约定

### 06-configuration（配置规范）
- YAML 编写规范
- 环境变量管理
- 配置校验

### 07-frontend（前端规范）
- **作用范围**：`frontend/**/*.{vue,ts,js,tsx,jsx}`
- Vue 3 + Nuxt 3 + TypeScript
- Composition API 最佳实践
- 代码实现准则（来自 awesome-cursorrules）

### 08-styling（样式规范）
- **作用范围**：`frontend/**/*.{vue,css,tsx,jsx}`、`tailwind.config.*`
- TailwindCSS utility classes
- DaisyUI 组件库
- TypeScript 严格模式（来自 awesome-cursorrules）

## 🚀 快速开始

**后端开发**（按顺序阅读）：
1. **01-general-conventions** - 了解核心规范（异步、数据库、性能优化）
2. **02-api-development** - 理解架构设计
3. **04-logging** - 学会正确使用日志

**前端开发**（按顺序阅读）：
1. **07-frontend** - Vue 3 开发规范（仅在 `frontend/` 目录生效）
2. **08-styling** - TailwindCSS 样式规范（仅在 `frontend/` 目录生效）

## ✨ 精简历程

- **原来**：12 个规则，约 1800 行
- **精简后**：6 个规则，403 行（减少 66%）
- **现在**：8 个规则，524 行（新增前端、样式规范，数据库规范已合并至核心规范）

## 📝 维护指南

### 添加新规则
1. 确保不与现有规则重复
2. 保持在 100 行以内
3. 使用清晰的文件夹命名（无需数字前缀）
4. 更新此 README

### 修改规则
1. 修改后确保总行数 ≤ 100
2. 避免添加冗长的代码示例
3. 一句话能说清就不用代码

## 🔗 参考资源

- [Cursor Rules 官方文档](https://cursor.directory/rules/python)
- [FastAPI 官方最佳实践](https://fastapi.tiangolo.com/)
