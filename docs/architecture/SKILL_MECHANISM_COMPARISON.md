# Skill 机制对比分析：Clawdbot vs ZenFlux Agent

🆕 V6.2: 深度分析与架构启发

---

## 一、Clawdbot Skill 机制核心特点

### 1. **声明式注册 + 多源加载**

```typescript
// src/agents/skills/workspace.ts:152-157
const merged = new Map<string, Skill>();
// 优先级: extra < bundled < managed < workspace
for (const skill of extraSkills) merged.set(skill.name, skill);
for (const skill of bundledSkills) merged.set(skill.name, skill);
for (const skill of managedSkills) merged.set(skill.name, skill);
for (const skill of workspaceSkills) merged.set(skill.name, skill);
```

**特点：**
- 无需代码注册，放入目录即可
- 多源加载：bundled（内置）、managed（全局）、workspace（项目）、extra（自定义）
- 高优先级覆盖低优先级（workspace 可覆盖 bundled）

---

### 2. **动态资格门控（Eligibility）**

```typescript
// src/agents/skills/config.ts:90-151
export function shouldIncludeSkill(params: {
  entry: SkillEntry;
  config?: MoltbotConfig;
  eligibility?: SkillEligibilityContext;
}): boolean {
  // 1. 检查配置禁用
  if (skillConfig?.enabled === false) return false;
  
  // 2. 检查 bundled 白名单
  if (!isBundledSkillAllowed(entry, allowBundled)) return false;
  
  // 3. 检查 OS 兼容性
  if (osList.length > 0 && !osList.includes(platform)) return false;
  
  // 4. 如果 always=true，跳过后续检查
  if (entry.metadata?.always === true) return true;
  
  // 5-7. 检查 bins/env/config
  // ...
}
```

**门控维度：**
- `enabled`: 显式禁用/启用
- `allowBundled`: 内置技能白名单（防止过载）
- `os`: 操作系统限制
- `bins`: 必需的 CLI 工具（全部满足或任一满足）
- `env`: 必需的环境变量
- `config`: 必需的配置路径（如 `browser.enabled`）

---

### 3. **延迟加载 + Prompt 注入**

```typescript
// src/agents/system-prompt.ts:15-33
function buildSkillsSection(params) {
  return [
    "## Skills (mandatory)",
    "Before replying: scan <available_skills> <description> entries.",
    "- If exactly one skill clearly applies: read its SKILL.md with Read, then follow it.",
    "- If multiple could apply: choose the most specific one, then read/follow it.",
    "- If none clearly apply: do not read any SKILL.md.",
    "Constraints: never read more than one skill up front; only read after selecting.",
    params.skillsPrompt,  // <available_skills> XML 格式
  ];
}
```

**注入的 Prompt 格式：**
```xml
<available_skills>
  <skill name="github" location="/path/to/skills/github/SKILL.md">
    <description>Interact with GitHub using the `gh` CLI...</description>
  </skill>
</available_skills>
```

**延迟加载策略：**
- 只注入 `name` + `description` 到系统 Prompt（成本低）
- Agent 根据描述选择最相关的技能
- 使用 `Read` 工具读取完整 `SKILL.md`（按需加载）
- 避免一次性加载 50+ 技能导致 token 爆炸

---

### 4. **热重载 + 变更监听**

```typescript
// src/agents/skills/refresh.ts
export function ensureSkillsWatcher(params: {
  workspaceDir: string;
  config?: MoltbotConfig;
}) {
  const watcher = chokidar.watch(watchPaths, {
    ignoreInitial: true,
    awaitWriteFinish: {
      stabilityThreshold: debounceMs,
      pollInterval: 100,
    },
    ignored: DEFAULT_SKILLS_WATCH_IGNORED,
  });
  
  watcher.on("add", (p) => schedule(p));
  watcher.on("change", (p) => schedule(p));
  watcher.on("unlink", (p) => schedule(p));
}

export function bumpSkillsSnapshotVersion(params?: {
  workspaceDir?: string;
  reason?: "watch" | "manual" | "remote-node";
}): number {
  // 更新版本号，触发 Prompt 重新生成
}
```

**特点：**
- 使用 `chokidar` 监听 skills 目录变更
- 250ms 防抖，避免频繁刷新
- 变更后自动 bump 版本号
- Agent 检测到版本变化后重新加载

---

### 5. **安装管理器（Installer）**

```typescript
// src/agents/skills-install.ts
export async function installSkill(params: SkillInstallRequest): Promise<SkillInstallResult> {
  const spec = findInstallSpec(entry, params.installId);
  
  switch (spec.kind) {
    case "brew": return ["brew", "install", spec.formula];
    case "node": return buildNodeInstallCommand(spec.package, prefs);
    case "go": return ["go", "install", spec.module];
    case "uv": return ["uv", "tool", "install", spec.package];
    case "download": return await installDownloadSpec({...});
  }
  
  const result = await runCommandWithTimeout(argv, { timeoutMs, env });
  return { ok: result.code === 0, ... };
}
```

**支持的安装方式：**
- `brew`: Homebrew 安装
- `node`: npm/pnpm/yarn/bun 安装
- `go`: Go module 安装
- `uv`: uv tool 安装
- `download`: 下载 + 解压

**用户偏好配置：**
```json
{
  "skills": {
    "install": {
      "preferBrew": true,
      "nodeManager": "npm"
    }
  }
}
```

---

### 6. **用户命令模式（User Invocable）**

```typescript
// src/agents/skills/workspace.ts:316-370
export function buildWorkspaceSkillCommandSpecs(workspaceDir, opts?) {
  const userInvocable = eligible.filter(
    entry => entry.invocation?.userInvocable !== false
  );
  
  // 生成命令规范
  return userInvocable.map(entry => ({
    name: sanitizeSkillCommandName(entry.skill.name),
    skillName: entry.skill.name,
    description: entry.skill.description,
    dispatch: resolveDispatchSpec(entry),
  }));
}
```

**SKILL.md frontmatter 配置：**
```yaml
user-invocable: true                 # 可作为 /命令 调用
disable-model-invocation: false      # 从模型 prompt 中排除
command-dispatch: tool               # 命令分发方式
command-tool: exec                   # 目标工具名
command-arg-mode: raw                # 参数传递模式
```

---

## 二、ZenFlux Agent 当前实现

### 1. **静态加载 + 启动时资格检查**

```python
# scripts/instance_loader.py
def _check_skill_eligibility(skill: SkillConfig) -> bool:
    # 检查 bins
    for bin_name in required_bins:
        if shutil.which(bin_name) is None:
            return False
    
    # 检查 env
    for env_name in required_env:
        if not os.getenv(env_name):
            return False
    
    # 检查 OS
    if supported_os and current_os not in supported_os:
        return False
    
    return True
```

**特点：**
- ✅ 启动时检查依赖
- ❌ 无热重载（需重启实例）
- ❌ 无安装引导（用户需手动安装）

---

### 2. **全量加载 Skills 到 Prompt**

```python
# core/prompt/instance_cache.py
skills_prompt = self._build_skills_prompt(skills)
# 将所有 SKILL.md 内容一次性加载到系统 Prompt
```

**问题：**
- 52 个 Skills 全量加载导致 Prompt 过长
- Token 成本高（每次对话都包含所有 Skills）
- 无延迟加载机制

---

## 三、对 ZenFlux Agent 的启发

### ⭐ 启发 1：实现延迟加载机制

**目标：**
- 只在系统 Prompt 中注入 Skills 列表（name + description）
- Agent 根据任务选择相关 Skill 后，通过 `Read` 工具读取完整内容

**实现方案：**

```python
# core/prompt/skill_prompt_builder.py
def build_skills_summary_prompt(skills: List[SkillConfig]) -> str:
    """
    构建 Skills 简要列表（仅 name + description）
    
    注入到系统 Prompt 的格式：
    <available_skills>
      <skill name="github" location="/path/to/SKILL.md">
        <description>Interact with GitHub...</description>
      </skill>
    </available_skills>
    """
    lines = ["<available_skills>"]
    for skill in skills:
        lines.append(f'  <skill name="{skill.name}" location="{skill.skill_path}/SKILL.md">')
        lines.append(f'    <description>{skill.description}</description>')
        lines.append('  </skill>')
    lines.append("</available_skills>")
    return "\n".join(lines)
```

**系统 Prompt 指令更新：**
```markdown
## Skills（技能）

扫描 `<available_skills>` 的 `<description>` 条目。
- 恰好一个技能适用 → 使用 Read 工具读取其 SKILL.md 并遵循
- 多个可能适用 → 选择最具体的
- 没有适用的 → 不读取

**重要：** 切勿在选择前读取多个 Skills。
```

**收益：**
- 系统 Prompt 大小从 ~50K tokens 降至 ~5K tokens
- 每次对话节省 Token 成本 90%
- 按需加载，提升响应速度

---

### ⭐ 启发 2：集成安装管理器到 instance_loader

**设计方案：**

```python
# scripts/instance_loader.py

async def load_instance_with_dependency_check(
    instance_name: str,
    auto_install: bool = False,  # 是否自动安装
    interactive: bool = False,   # 是否交互式引导
) -> SimpleAgent:
    """
    加载实例 + 依赖检查
    
    Args:
        instance_name: 实例名称
        auto_install: 是否自动安装缺失依赖
        interactive: 是否交互式引导用户
    
    Returns:
        Agent 实例
    """
    # 1. 检查依赖
    checker = DependencyChecker(instance_name)
    results = checker.check_all_skills()
    
    if results['missing']:
        logger.warning(f"发现 {len(results['missing'])} 个 Skills 缺少依赖")
        
        if interactive:
            # 交互式引导
            checker.run_interactive(results)
            # 等待用户确认后继续
        elif auto_install:
            # 自动安装
            script = checker.generate_install_script(results)
            await run_install_script(script)
        else:
            # 仅提示
            logger.info("运行以下命令查看详情：")
            logger.info(f"  python scripts/check_instance_dependencies.py {instance_name}")
    
    # 2. 加载实例
    agent = await load_instance(instance_name)
    return agent
```

**配置控制（config.yaml）：**

```yaml
# ==================== Skills 依赖管理配置 ====================
skill_dependency_check:
  enabled: true                # 是否启用依赖检查
  mode: "prompt"               # 检查模式：prompt（提示）/ auto（自动安装）/ interactive（交互式）
  fail_on_missing: false       # 缺少依赖时是否阻止启动
  install_preferences:
    prefer_brew: true          # 优先使用 Homebrew
    node_manager: "npm"        # npm/pnpm/yarn/bun
```

**启动流程：**

```bash
# 模式 1: 仅提示（默认）
python scripts/run_instance.py client_agent
# 输出: ⚠️ 30 个 Skills 缺少依赖，运行 check_instance_dependencies.py 查看详情

# 模式 2: 交互式引导
python scripts/run_instance.py client_agent --interactive
# 输出: 
#   📦 peekaboo 需要安装: brew install steipete/tap/peekaboo
#   是否安装? [Y/n]

# 模式 3: 自动安装
python scripts/run_instance.py client_agent --auto-install
# 输出: 
#   📦 正在安装 peekaboo...
#   ✅ 安装成功
```

---

### ⭐ 启发 3：实现 Skills 热重载

**设计方案：**

```python
# core/skill/watcher.py
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class SkillsWatcher(FileSystemEventHandler):
    """Skills 目录监听器"""
    
    def __init__(self, skills_dir: Path, callback):
        self.skills_dir = skills_dir
        self.callback = callback
        self.debounce_timer = None
        self.debounce_delay = 0.25  # 250ms
    
    def on_any_event(self, event):
        """文件变更事件"""
        if event.is_directory:
            return
        
        if event.src_path.endswith("SKILL.md"):
            self._schedule_reload(event.src_path)
    
    def _schedule_reload(self, changed_path: str):
        """防抖重载"""
        if self.debounce_timer:
            self.debounce_timer.cancel()
        
        self.debounce_timer = asyncio.create_task(
            self._debounced_reload(changed_path)
        )
    
    async def _debounced_reload(self, changed_path: str):
        """延迟重载"""
        await asyncio.sleep(self.debounce_delay)
        logger.info(f"检测到 Skill 变更: {changed_path}")
        await self.callback(changed_path)
```

**集成到 instance_loader：**

```python
# scripts/instance_loader.py

async def load_instance_with_hot_reload(instance_name: str) -> SimpleAgent:
    """加载实例 + 启用热重载"""
    agent = await load_instance(instance_name)
    
    # 启用热重载
    if config.skill_hot_reload.enabled:
        skills_dir = instance_dir / "skills"
        
        async def on_skill_changed(path: str):
            logger.info(f"重新加载 Skills: {path}")
            # 重新加载 Skills 并更新 Agent 的系统 Prompt
            new_skills = load_skills(skills_dir)
            agent.update_skills(new_skills)
        
        watcher = SkillsWatcher(skills_dir, on_skill_changed)
        observer = Observer()
        observer.schedule(watcher, str(skills_dir), recursive=True)
        observer.start()
    
    return agent
```

**配置控制（config.yaml）：**

```yaml
skill_hot_reload:
  enabled: true                # 是否启用热重载
  debounce_ms: 250             # 防抖延迟（毫秒）
  watch_patterns:
    - "*.md"
    - "*.yaml"
```

---

### ⭐ 启发 4：多源加载 + 优先级覆盖

**目标：**
- 支持全局 Skills（`~/.zenflux/skills`）
- 支持项目 Skills（`instances/client_agent/skills`）
- 支持额外目录（配置中的 `extra_dirs`）
- 高优先级覆盖低优先级（项目 > 全局 > 内置）

**实现方案：**

```python
# core/skill/loader.py

def load_skills_from_multiple_sources(
    instance_name: str,
    config: InstanceConfig,
) -> List[SkillConfig]:
    """
    从多个来源加载 Skills
    
    优先级：extra < bundled < global < instance
    """
    skills_map = {}  # name -> SkillConfig
    
    # 1. 加载额外目录 Skills（最低优先级）
    for extra_dir in config.skill_sources.extra_dirs:
        extra_skills = load_skills_from_dir(Path(extra_dir), source="extra")
        for skill in extra_skills:
            skills_map[skill.name] = skill
    
    # 2. 加载内置 Skills
    bundled_skills = load_skills_from_dir(
        PROJECT_ROOT / "skills",
        source="bundled"
    )
    for skill in bundled_skills:
        skills_map[skill.name] = skill  # 覆盖 extra
    
    # 3. 加载全局 Skills
    global_skills_dir = Path.home() / ".zenflux" / "skills"
    if global_skills_dir.exists():
        global_skills = load_skills_from_dir(global_skills_dir, source="global")
        for skill in global_skills:
            skills_map[skill.name] = skill  # 覆盖 bundled
    
    # 4. 加载实例 Skills（最高优先级）
    instance_skills_dir = PROJECT_ROOT / "instances" / instance_name / "skills"
    instance_skills = load_skills_from_dir(instance_skills_dir, source="instance")
    for skill in instance_skills:
        skills_map[skill.name] = skill  # 覆盖 global
    
    return list(skills_map.values())
```

**配置控制（config.yaml）：**

```yaml
skill_sources:
  bundled_enabled: true        # 是否启用内置 Skills
  bundled_allowlist:           # 内置 Skills 白名单（为空表示全部启用）
    - github
    - gemini
  global_enabled: true         # 是否启用全局 Skills
  extra_dirs:                  # 额外 Skills 目录
    - "~/Projects/my-skills"
```

---

### ⭐ 启发 5：Skill 配置增强

**扩展 SKILL.md frontmatter：**

```yaml
---
name: github
description: "Interact with GitHub using the `gh` CLI"
metadata:
  moltbot:
    always: false              # 跳过所有门控检查
    emoji: "🐙"
    homepage: "https://cli.github.com"
    os: ["darwin", "linux"]    # 支持的操作系统
    requires:
      bins: ["gh"]             # 必需的 CLI 工具（全部满足）
      anyBins: ["git"]         # 必需的 CLI 工具（任一满足）
      env: ["GITHUB_TOKEN"]    # 必需的环境变量
      config: ["github.enabled"]  # 必需的配置路径
    install:
      - kind: "brew"
        formula: "gh"
      - kind: "download"
        url: "https://github.com/cli/cli/releases/download/v2.40.0/gh_2.40.0_macOS_amd64.tar.gz"
        extract: true
        stripComponents: 1
user-invocable: true           # 可作为用户命令调用
disable-model-invocation: false  # 是否从模型 prompt 中排除
---

# GitHub Skill

Use the `gh` CLI to interact with GitHub...
```

**新增字段说明：**
- `always`: 跳过依赖检查，始终加载（用于无依赖的 Skills）
- `anyBins`: 任一工具满足即可（如 `spogo` 或 `spotify_player`）
- `config`: 检查配置路径（如 `browser.enabled`）
- `user-invocable`: 用户可通过 `/github` 命令直接调用
- `disable-model-invocation`: 从模型 Prompt 中排除（仅作为用户命令）

---

## 四、集成到 Instance Loader 的建议

### 方案 A：启动时检查 + 提示

**适用场景：** 本地开发环境

```python
# scripts/instance_loader.py

async def load_instance(instance_name: str) -> SimpleAgent:
    # ... 现有加载逻辑 ...
    
    # 🆕 启动时检查依赖
    if config.skill_dependency_check.enabled:
        from core.skill.dynamic_loader import DependencyChecker
        
        checker = DependencyChecker(instance_name)
        results = checker.check_all_skills()
        
        if results['missing']:
            mode = config.skill_dependency_check.mode
            
            if mode == "prompt":
                # 仅提示
                logger.warning(f"⚠️ {len(results['missing'])} 个 Skills 缺少依赖")
                logger.info("运行以下命令查看详情：")
                logger.info(f"  python scripts/check_instance_dependencies.py {instance_name}")
            
            elif mode == "auto":
                # 自动安装
                logger.info(f"📦 自动安装 {len(results['missing'])} 个 Skills 依赖...")
                script = checker.generate_install_script(results)
                await run_install_script_async(script)
                logger.info("✅ 依赖安装完成，重新加载 Skills")
                # 重新加载 Skills
                skills = load_skills(instance_dir / "skills")
            
            elif mode == "interactive":
                # 交互式引导
                checker.run_interactive(results)
            
            if config.skill_dependency_check.fail_on_missing:
                raise RuntimeError(f"Skills 依赖不满足，无法启动")
    
    return agent
```

---

### 方案 B：部署态配置引导

**适用场景：** 生产环境部署

```bash
# 部署脚本：deploy_instance.sh

#!/bin/bash

INSTANCE_NAME="client_agent"

echo "📋 检查实例依赖..."
python scripts/check_instance_dependencies.py "$INSTANCE_NAME"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ 部分 Skills 缺少依赖"
    echo ""
    echo "请选择操作："
    echo "  1) 生成安装脚本（推荐运维人员）"
    echo "  2) 交互式配置"
    echo "  3) 忽略并继续（仅启用可用 Skills）"
    
    read -p "选择 [1/2/3]: " choice
    
    case $choice in
        1)
            python scripts/check_instance_dependencies.py "$INSTANCE_NAME" \
                --generate-install --output "install_deps.sh"
            echo "✅ 安装脚本已生成: install_deps.sh"
            echo "💡 请运行: bash install_deps.sh"
            exit 1
            ;;
        2)
            python scripts/check_instance_dependencies.py "$INSTANCE_NAME" --interactive
            ;;
        3)
            echo "⚠️ 将仅启用满足依赖的 Skills"
            ;;
    esac
fi

echo ""
echo "🚀 启动实例..."
python scripts/run_instance.py "$INSTANCE_NAME"
```

---

## 五、推荐实施优先级

### P0（核心收益）
1. **延迟加载机制** - 立即实施，节省 90% Token 成本
2. **依赖检查集成到 instance_loader** - 提升用户体验

### P1（体验提升）
3. **多源加载 + 优先级覆盖** - 支持全局 Skills
4. **安装管理器集成** - 自动化依赖安装

### P2（高级功能）
5. **Skills 热重载** - 开发体验优化
6. **用户命令模式** - 支持 `/github` 命令

---

## 六、总结

Clawdbot 的 Skill 机制提供了以下关键启发：

| 机制 | Clawdbot | ZenFlux Agent 现状 | 建议 |
|------|----------|-------------------|------|
| 加载策略 | 延迟加载（仅 name+desc） | 全量加载 | ⭐ 实现延迟加载 |
| 依赖管理 | 自动安装 + 交互引导 | 手动安装 | ⭐ 集成到 instance_loader |
| 多源加载 | 4 级优先级 | 单一来源 | 实现多源加载 |
| 热重载 | 文件监听 + 自动刷新 | 需重启 | 可选实现 |
| 安装器 | brew/npm/go/uv/download | 无 | 实现安装管理器 |
| 用户命令 | 支持 `/command` | 无 | 可选实现 |

**核心收益：**
- Token 成本降低 90%（延迟加载）
- 部署体验提升（自动依赖检查 + 安装引导）
- 扩展性增强（多源加载 + 热重载）
