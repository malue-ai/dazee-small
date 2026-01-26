"""
E2B 前端项目模板定义

基于 Node.js 20，预装前端开发常用工具：
- pnpm（快速包管理器）
- vite（现代构建工具）
- serve（静态文件服务器）
- create-vite、create-next-app（项目脚手架）
"""

from e2b import Template, wait_for_port

# 前端开发模板
frontend_template = (
    Template()
    .from_node_image("20")  # Node.js 20 LTS
    .set_envs({
        "NODE_ENV": "development",
        "HOME": "/home/user",
        "NPM_CONFIG_PREFIX": "/home/user/.npm-global",
        "PATH": "/home/user/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    })
    .run_commands([
        # 创建用户目录
        "mkdir -p /home/user/.npm-global",
        "mkdir -p /home/user/app",
        
        # 安装全局工具
        "npm install -g pnpm",
        "npm install -g vite",
        "npm install -g serve",
        "npm install -g create-vite",
        "npm install -g create-next-app",
        
        # 验证安装
        "node --version",
        "npm --version",
        "pnpm --version",
    ])
)

# 模板别名
FRONTEND_TEMPLATE_ALIAS = "zenflux-frontend"
FRONTEND_TEMPLATE_ALIAS_DEV = "zenflux-frontend-dev"
