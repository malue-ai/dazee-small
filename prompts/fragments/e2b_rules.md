# E2B 沙盒使用规范

当使用 E2B 沙盒执行代码时：

## 基本原则
- 文件操作在 `/home/user/project` 目录下
- 安装依赖前检查是否已存在
- **conversation_id 由系统自动注入，无需手动传递**
- **Web 项目必须使用 `index.html` 作为入口文件**，这样预览 URL 可以直接访问

## 沙盒工具
| 工具 | 用途 |
|------|------|
| `sandbox_write_file` | 写入文件 |
| `sandbox_read_file` | 读取文件 |
| `sandbox_list_files` | 列出目录 |
| `sandbox_run_command` | 执行命令（支持 background 模式） |
| `sandbox_execute_python` | 执行 Python 代码 |
| `sandbox_get_public_url` | 获取服务公开 URL |

## 启动 Web 服务
使用 `sandbox_run_command` 的 `background=true` 模式启动服务：
```json
{
  "command": "python -m http.server 8080",
  "background": true,
  "port": 8080
}
```

## ⚠️ 重要：禁止输出预览 URL

**严禁在回复中输出沙盒的预览 URL 或访问链接！**

❌ 错误示例（不要这样做）：
```
🌐 点击下方链接打开游戏：
https://8080-xxx.e2b.app/game.html
```

✅ 正确做法：
- 启动服务后，系统会自动将预览链接发送给前端
- 前端会自动显示预览窗口
- 只需告知用户"服务已启动"或"项目已部署"即可

**原因**：URL 已通过事件系统自动传递给前端，无需重复输出。

## 静态 Web 项目规范

创建纯 HTML/CSS/JS 项目时：

1. **入口文件必须命名为 `index.html`**（不要用 `game.html`、`app.html` 等）
2. 其他资源文件放在同级目录或子目录

```
/home/user/project/
├── index.html      ← 入口文件（必须）
├── style.css       ← 样式文件（可选）
├── script.js       ← 脚本文件（可选）
└── assets/         ← 资源目录（可选）
```

**原因**：预览 URL 直接指向根目录，使用 `index.html` 可以自动被 HTTP 服务器识别为默认页面。

## 常见命令
```bash
# Python
pip install <package>
python script.py

# Node.js
npm install <package>
node script.js
```

## 注意事项
- 大文件操作可能需要时间
- 网络请求可能有限制
- 执行完成后清理临时文件

