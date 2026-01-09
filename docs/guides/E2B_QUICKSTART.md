# E2B 快速开始指南

> **5分钟内完成 E2B 集成配置和测试**

## 📋 前置条件

✅ Python 3.11+ 已安装  
✅ liuy 虚拟环境已激活  
✅ 网络连接正常  

## 🚀 三步配置

### Step 1: 获取 E2B API Key

1. 访问 https://e2b.dev/dashboard
2. 注册/登录账号（支持 GitHub 登录）
3. 点击 "Create API Key"
4. 复制生成的 API Key（格式：`e2b_***`）

### Step 2: 配置 API Key

**方式 1: 运行配置向导（推荐）**

```bash
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
source /Users/liuyi/Documents/langchain/liuy/bin/activate
python scripts/configure_e2b.py
```

按照提示输入您的 API Key。

**方式 2: 手动创建 .env 文件**

在项目根目录创建 `.env` 文件：

```bash
# E2B Configuration
E2B_API_KEY=e2b_your_actual_key_here

# Anthropic API Key (如果还没配置)
ANTHROPIC_API_KEY=sk-ant-***
```

### Step 3: 运行测试

**运行完整测试（推荐）**

```bash
bash scripts/test_e2b_complete.sh
```

或者**直接运行 Python 测试**：

```bash
source /Users/liuyi/Documents/langchain/liuy/bin/activate
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
python tests/test_e2b_e2e_real.py
```

## ✅ 预期结果

测试成功后，您应该看到：

```
🎉 所有真实测试通过！E2B 集成成功！

📊 测试总结:
  Sandbox ID: sb_***
  总执行次数: 5
  已安装包: 3 个 (requests, pandas, beautifulsoup4)
  执行历史: 5 条
  文件记录: 3 个

✅ E2B Python 沙箱已成功集成到 Zenflux Agent V3.7
```

## 🎯 测试内容

| 测试项 | 说明 | 验证内容 |
|-------|------|---------|
| **基础执行** | 运行简单 Python 代码 | E2B API 连接正常 |
| **网络请求** | 调用 httpbin.org API | 网络访问正常 |
| **数据分析** | pandas 处理 CSV | 自动包安装 + 文件同步 |
| **多轮对话** | 连续执行代码 | 沙箱持久化和复用 |
| **Memory 集成** | 验证状态记录 | WorkingMemory 正确工作 |

## 🐛 故障排查

### 问题 1: E2B SDK 未安装

```bash
pip install e2b e2b-code-interpreter
```

### 问题 2: API Key 无效

```
❌ 执行失败: Unauthorized
```

**解决**：
1. 检查 API Key 是否正确
2. 访问 https://e2b.dev/dashboard 验证 Key 状态
3. 重新生成 API Key

### 问题 3: 沙箱创建超时

```
❌ 沙箱创建失败: timeout
```

**解决**：
1. 检查网络连接
2. 稍后重试（E2B 服务可能繁忙）
3. 查看 E2B 状态页: https://status.e2b.dev

## 📚 下一步

测试通过后，您可以：

1. **查看完整文档**: `docs/E2B_INTEGRATION.md`
2. **运行示例代码**: `python examples/e2b_simple_example.py`
3. **集成到 Agent**: 已自动集成，使用 `code_sandbox` 能力即可
4. **开始使用**: Agent 会自动在需要时使用 E2B

## 💡 快速验证命令

```bash
# 单行验证（快速检查）
source /Users/liuyi/Documents/langchain/liuy/bin/activate && \
cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent && \
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv('E2B_API_KEY')
if api_key:
    print(f'✅ E2B_API_KEY: {api_key[:10]}...')
else:
    print('❌ E2B_API_KEY 未设置')
"
```

---

**需要帮助？**
- E2B 文档: https://e2b.dev/docs
- E2B Discord: https://discord.gg/e2b
- 项目 Issues: 提交到项目 GitHub

