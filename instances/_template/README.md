# 实例模板

## 创建新实例

1. 复制此目录，改名为你的实例名：
   ```bash
   cp -r instances/_template instances/my-agent
   ```

2. 修改 `config.yaml`：
   - `instance.name` 改为实例名
   - `storage.base_path` 改为 `~/.xiaodazi/my-agent`
   - `agent.provider` 选择 `qwen` 或 `claude`

3. 复制并填写 API Keys：
   ```bash
   cp .env.example .env
   # 编辑 .env，填入你的 API Key
   ```

4. 编辑 `prompt.md`，定义搭子的人格和能力

5. 从 `xiaodazi` 复制需要的 Skills 和 LLM 配置：
   ```bash
   cp instances/xiaodazi/config/llm_profiles.yaml instances/my-agent/config/
   ```

6. 启动：
   ```bash
   AGENT_INSTANCE=my-agent python main.py
   ```

## 目录结构

```
my-agent/
├── config.yaml              用户配置
├── config/
│   ├── skills.yaml          Skills 清单
│   └── llm_profiles.yaml    LLM 路由（从 xiaodazi 复制）
├── prompt.md                人格提示词
├── .env                     API Keys（不提交 git）
└── skills/                  Skill 目录
```
