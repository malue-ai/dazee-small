import express, { Request, Response, NextFunction } from "express";
import { createServer } from "http";
import cors from "cors";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
  const app = express();
  const server = createServer(app);

  // ============================================
  // 中间件配置
  // ============================================
  
  // CORS 配置 - 允许前端开发服务器跨域访问
  app.use(cors({
    origin: process.env.NODE_ENV === "production" 
      ? false  // 生产环境禁用 CORS（同源）
      : ["http://localhost:5173", "http://127.0.0.1:5173"],  // 开发环境允许 Vite 端口
    credentials: true,
  }));
  
  app.use(express.json());
  app.use(express.urlencoded({ extended: true }));

  // 请求日志（开发环境）
  if (process.env.NODE_ENV !== "production") {
    app.use((req: Request, _res: Response, next: NextFunction) => {
      console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
      next();
    });
  }

  // ============================================
  // API 路由 - 必须在静态文件和 catch-all 之前
  // ============================================

  // 健康检查
  app.get("/api/health", (_req: Request, res: Response) => {
    res.json({ status: "ok", timestamp: new Date().toISOString() });
  });

  // 示例：认证路由
  app.post("/api/auth/login", (req: Request, res: Response) => {
    const { email, password } = req.body;

    // TODO: 实现真实的认证逻辑
    if (!email || !password) {
      return res.status(400).json({ error: "邮箱和密码不能为空" });
    }

    // 示例响应 - 替换为真实的认证实现
    res.json({
      data: {
        user: { id: "1", email },
        token: "demo-jwt-token",
      },
    });
  });

  app.post("/api/auth/register", (req: Request, res: Response) => {
    const { email, password, name } = req.body;

    if (!email || !password) {
      return res.status(400).json({ error: "邮箱和密码不能为空" });
    }

    // TODO: 实现真实的注册逻辑
    res.status(201).json({
      data: {
        user: { id: "1", email, name },
        message: "注册成功",
      },
    });
  });

  app.post("/api/auth/logout", (_req: Request, res: Response) => {
    // TODO: 实现登出逻辑（如清除 session/token）
    res.json({ data: { message: "登出成功" } });
  });

  // 示例：CRUD 路由
  app.get("/api/items", (_req: Request, res: Response) => {
    // TODO: 从数据库获取数据
    res.json({
      data: [
        { id: "1", title: "示例项目 1", status: "pending", createdAt: new Date().toISOString() },
        { id: "2", title: "示例项目 2", status: "completed", createdAt: new Date().toISOString() },
      ],
    });
  });

  app.post("/api/items", (req: Request, res: Response) => {
    const { title } = req.body;

    if (!title) {
      return res.status(400).json({ error: "标题不能为空" });
    }

    // TODO: 保存到数据库
    res.status(201).json({
      data: {
        id: Date.now().toString(),
        title,
        status: "pending",
        createdAt: new Date().toISOString(),
      },
    });
  });

  // API 404 处理 - 未匹配的 /api/* 路由
  app.all("/api/*", (_req: Request, res: Response) => {
    res.status(404).json({ error: "API 端点不存在" });
  });

  // ============================================
  // 静态文件服务
  // ============================================
  const staticPath =
    process.env.NODE_ENV === "production"
      ? path.resolve(__dirname, "public")
      : path.resolve(__dirname, "..", "dist", "public");

  app.use(express.static(staticPath));

  // 客户端路由 - 所有非 API 请求返回 index.html
  app.get("*", (_req: Request, res: Response) => {
    res.sendFile(path.join(staticPath, "index.html"));
  });

  // ============================================
  // 错误处理
  // ============================================
  app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    console.error("[Server Error]", err);
    res.status(500).json({ error: "服务器内部错误" });
  });

  const port = process.env.PORT || 3000;
  const host = process.env.HOST || "0.0.0.0";  // 监听所有网络接口

  server.listen(Number(port), host, () => {
    console.log(`Server running on http://${host}:${port}/`);
    console.log(`API available at http://localhost:${port}/api`);
    console.log(`Health check: http://localhost:${port}/api/health`);
  });
}

startServer().catch(console.error);