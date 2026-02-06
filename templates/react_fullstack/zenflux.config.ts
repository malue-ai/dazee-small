import { defineConfig } from "@/lib/zenflux";

export default defineConfig({
  // 功能开关
  modules: {
    llm: true,       // 启用 LLM 能力
    database: true,  // 启用数据库能力
    storage: false,  // 启用文件存储 (可选)
    auth: false,     // 启用用户认证 (可选)
  },
  
  // LLM 配置
  llm: {
    defaultModel: "claude-sonnet",
  },
});
