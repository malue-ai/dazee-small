"""
Skill Prompt 构建器

核心理念：
- 只在系统 Prompt 中注入 Skills 列表（name + description + location）
- Agent 根据任务选择相关 Skill 后，通过 Read 工具读取完整内容
- 避免一次性加载 50+ Skills 导致 Token 爆炸

收益：
- 系统 Prompt 大小从 ~50K tokens 降至 ~5K tokens
- 每次对话节省 Token 成本 90%
- 按需加载，提升响应速度
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SkillSummary:
    """Skill 简要信息（用于 Prompt 注入）"""

    name: str
    description: str
    location: Path  # SKILL.md 的绝对路径
    emoji: str = ""  # 可选图标
    quickstart: str = ""  # 快速启动代码片段（从 SKILL.md frontmatter 提取）
    requires_bins: List[str] = field(default_factory=list)
    requires_env: List[str] = field(default_factory=list)
    parameters: List[Dict] = field(default_factory=list)  # optional structured params
    backend_type: str = ""  # "tool" 表示可直接调用的框架工具
    tool_name: str = ""  # backend_type=tool 时对应的工具名（如 cloud_agent）


class SkillPromptBuilder:
    """
    Skill Prompt 构建器

    支持两种模式：
    1. Lazy Mode（延迟加载）：仅注入 name + description + location
    2. Eager Mode（全量加载）：注入完整 SKILL.md 内容
    """

    # ================================================================
    # Prompt 构建（无状态，staticmethod）
    # ================================================================

    @staticmethod
    def build_lazy_prompt(
        skills: List[SkillSummary],
        language: str = "zh",
    ) -> str:
        """
        构建延迟加载 Prompt（仅注入 Skills 列表）

        Args:
            skills: Skills 简要信息列表
            language: 语言（zh/en）

        Returns:
            XML 格式的 Skills 列表
        """
        if not skills:
            return ""

        # Adaptive ordering: sort by usage frequency (zero cost if no data yet)
        try:
            from core.skill.usage_tracker import get_usage_tracker
            tracker = get_usage_tracker()
            skills = tracker.sort_skills(list(skills))
        except Exception as e:
            logger.debug(f"Skill 自适应排序跳过: {e}")

        lines = ["<available_skills>"]

        for skill in skills:
            emoji_prefix = f"{skill.emoji} " if skill.emoji else ""
            # 路径压缩节省 token（绝对路径每个 skill 浪费 ~90 chars）
            # 优先级：相对路径（cwd 内）> ~/ 缩写（home 内）> 绝对路径（fallback）
            location = skill.location
            try:
                location = Path(location).relative_to(Path.cwd())
            except (ValueError, TypeError):
                try:
                    home = Path.home()
                    location = Path("~") / Path(location).relative_to(home)
                except (ValueError, TypeError, RuntimeError):
                    pass  # 无法压缩时保留绝对路径

            # backend_type=tool 的 Skill 标记工具名，告诉 LLM 直接调用
            if skill.backend_type == "tool" and skill.tool_name:
                lines.append(
                    f'  <skill name="{skill.name}" backend_type="tool" '
                    f'tool_name="{skill.tool_name}" location="{location}">'
                )
            else:
                lines.append(f'  <skill name="{skill.name}" location="{location}">')
            lines.append(f"    <description>{emoji_prefix}{skill.description}</description>")
            if skill.quickstart:
                lines.append(f"    <quickstart>\n{skill.quickstart}\n    </quickstart>")
            if skill.parameters:
                params_parts = []
                for p in skill.parameters:
                    pname = p.get("name", "")
                    ptype = p.get("type", "string")
                    pdesc = p.get("description", "")
                    req = " required" if p.get("required") else ""
                    enum = f" enum={p['enum']}" if p.get("enum") else ""
                    default = f" default={p['default']}" if "default" in p else ""
                    params_parts.append(
                        f"      <param name=\"{pname}\" type=\"{ptype}\"{req}{enum}{default}>{pdesc}</param>"
                    )
                lines.append("    <parameters>")
                lines.extend(params_parts)
                lines.append("    </parameters>")
            lines.append("  </skill>")

        lines.append("</available_skills>")

        prompt = "\n".join(lines)

        logger.debug(f"构建延迟加载 Skills Prompt: {len(skills)} 个技能, {len(prompt)} 字符")

        return prompt

    @staticmethod
    def build_lazy_instructions(
        language: str = "zh",
        instance_name: str = "",
    ) -> str:
        """
        构建延迟加载的系统指令

        Args:
            language: 语言（zh/en）
            instance_name: 实例名称（用于 Skill 路径）

        Returns:
            系统指令文本
        """
        import os

        inst = instance_name or os.environ.get("AGENT_INSTANCE", "default")
        skills_path = f"instances/{inst}/skills"

        if language == "zh":
            return f"""
## Skills（技能）

扫描 `<available_skills>` 的 `<description>` 条目，选择最匹配的 Skill。

**⚠️ 两种 Skill 类型，执行方式完全不同：**

**类型 A — `backend_type="tool"` 的 Skill（标记了 `tool_name`）：**
- 这是框架内置工具的使用指南，**直接调用 `tool_name` 指定的工具**即可
- 例如 `<skill name="cloud-agent" backend_type="tool" tool_name="cloud_agent">` → 直接调用 `cloud_agent` 工具
- **禁止** 用 nodes 读取 SKILL.md 或执行代码，直接调用工具！

**类型 B — 普通 Skill（无 `backend_type` 属性）：**
- 名称不是工具，**不能**直接调用，必须通过 `nodes` 或 `api_calling` 执行 Skill 代码
- 如果有 `<quickstart>`：按 quickstart 代码用 `nodes` 工具执行
- 如果没有 `<quickstart>`：先 Read `location` 路径的 SKILL.md，再按代码示例执行

**需安装的 Skill（description 含 [需安装: ...]）：**
1. 先用 hitl 工具请求用户确认安装（说明安装什么、为什么需要）
2. 用户同意 → 用 nodes 执行安装命令（如 pip install xxx），然后正常使用
3. 用户拒绝 → 放弃该 Skill，寻找替代方案完成任务（如用 browser 工具、用 nodes 执行 httpx 等轻量方案）

**Skill 执行失败且原因是依赖缺失时：**
不要直接跳到替代方案。先用 hitl 工具告知用户缺失了什么依赖并询问是否安装，用户同意后安装并重试，用户拒绝后再寻找替代方案。

**用户提到的 Skill 不在 `<available_skills>` 中时：**
不要说"找不到"或编造替代方案。尝试用 nodes 工具读取 `{skills_path}/{{skill-name}}/SKILL.md`（将 skill-name 替换为用户提到的名称）。如果文件存在，按其中的指引执行；如果文件不存在，用 hitl 工具告知用户该 Skill 未安装，询问是否需要用其他方式完成任务。

**用户请求安装第三方工具或 MCP Server 时：**
先评估能力边界，再行动。按以下顺序判断：
1. `<available_skills>` 中是否已有能满足需求的 Skill → 有则直接使用
2. `{skills_path}/` 下是否有未注册但存在的 Skill 目录 → 有则读取并执行
3. 用户的真实需求能否用已有工具实现（如用 browser 工具操控网页，而非安装 chrome-mcp）→ 能则说明替代方案
4. 以上都不行 → 告知用户当前没有该能力，引导用 skill-creator 创建或用 skill-finder 搜索社区 Skill

MCP 类请求（用户提到"MCP"或某个 MCP Server）：
- 本框架支持 `backend_type: mcp` 的 Skill，但需要预配置 `server_url`
- 不要尝试直接安装 MCP Server 的 npm 包然后期望能连上——框架不会自动连接任意 MCP Server
- 正确做法：引导用户提供 MCP Server 的 URL，然后用 skill-creator 创建一个 `backend_type: mcp` 的 Skill

**网络搜索/内容提取 — 按能力类别选择（从 available_skills 中匹配具体 Skill）：**
1. **框架搜索工具**（如 `web_search`）：优先直接调用，需 API Key，未配置时会返回 recovery_hint
2. **免费搜索/提取 Skill**（如 jina-reader 等）：通过 `nodes` 执行 curl 命令，零依赖。示例：`curl -sS -L --max-time 30 -H 'Accept: application/json' 'https://s.jina.ai/关键词'`
3. **云端委托**（`cloud_agent`）：本地搜索不可用时、或用户明确要求深度调研时使用
4. **爬虫 Skill**（如 Crawl4AI 等）：批量抓取或反爬场景
- **绝对禁止**：不要用 `open -a Safari`、`osascript` 打开浏览器做手动搜索！不要用 `observe_screen` 截屏来读网页！

**禁止行为：**
- 对于普通 Skill（无 `backend_type` 属性）：不要把 Skill 名当作工具名调用，必须通过 `nodes` 执行代码
- 对于 `backend_type="tool"` 的 Skill：不要用 nodes 读取 SKILL.md 或执行代码，直接调用 `tool_name` 指定的工具
- 不要把 Skill 名（如 `cloud-agent`、`ddg-search`）当作 `api_calling` 的 `api_name` 传入——它们不是注册 API
- 不要为了"可能有用"而安装系统级软件（homebrew、node、java、docker 等），这超出了 Skill 依赖范围
- 不要在未确认最终能使用的情况下安装一连串前置依赖
- 安装非 pip 包的系统级依赖前，必须用 hitl 工具征求用户同意并说明理由
- 不要安装完才告诉用户"装了但用不了"——应在安装前判断

**重要：**
- 不要在选择前读取多个 Skills
- 高级用法参考完整 SKILL.md（Read `location` 路径）
""".strip()
        else:
            return f"""
## Skills (mandatory)

Scan `<available_skills>` `<description>` entries, choose the best match.

**⚠️ Two Skill types with DIFFERENT execution methods:**

**Type A — Skills with `backend_type="tool"` (marked with `tool_name`):**
- These are usage guides for built-in tools — **call the tool specified by `tool_name` directly**
- E.g. `<skill name="cloud-agent" backend_type="tool" tool_name="cloud_agent">` → call `cloud_agent` tool directly
- Do NOT use nodes to read SKILL.md or execute code — just call the tool!

**Type B — Regular Skills (no `backend_type` attribute):**
- Names are NOT callable tools — execute Skill code via `nodes` or `api_calling`
- If Skill has `<quickstart>`: execute directly via `nodes` tool following the quickstart code
- If no `<quickstart>`: Read the SKILL.md at `location` path first, then follow its code via `nodes` or `api_calling`

**Skills requiring setup (description contains [needs setup: ...]):**
1. Use hitl tool to ask user to confirm installation (explain what and why)
2. User approves → run install command via nodes (e.g. pip install xxx), then use normally
3. User declines → abandon that Skill, find alternative approaches (e.g. browser tool, httpx via nodes)

**Skill execution fails due to missing dependency:**
Do NOT jump to alternatives immediately. First use hitl tool to inform user what dependency is missing and ask whether to install. Install and retry if approved, find alternatives only if declined.

**User mentions a Skill not in `<available_skills>`:**
Do NOT say "not found" or make up alternatives. Try reading `{skills_path}/{{skill-name}}/SKILL.md` via nodes tool (replace skill-name with what user mentioned). If the file exists, follow its instructions; if not, use hitl to inform user the Skill is not installed and ask if they want to use an alternative approach.

**When user requests installing a third-party tool or MCP Server:**
Assess capability boundaries before acting. Follow this order:
1. Does `<available_skills>` already have a Skill that meets the need? → Use it directly
2. Is there an unregistered Skill directory under `{skills_path}/`? → Read and execute it
3. Can the user's real need be met with existing tools (e.g. browser tool for web control instead of chrome-mcp)? → Explain the alternative
4. None of the above → Tell the user this capability isn't available yet, guide them to use skill-creator or skill-finder

MCP requests (user mentions "MCP" or a specific MCP Server):
- This framework supports `backend_type: mcp` Skills, but requires a pre-configured `server_url`
- Do NOT install MCP Server npm packages expecting them to "just work" — the framework won't auto-connect to arbitrary MCP Servers
- Correct approach: ask user for the MCP Server URL, then use skill-creator to create a `backend_type: mcp` Skill

**Web search / content extraction — pick by capability category (match specific Skills from available_skills):**
1. **Framework search tool** (e.g. `web_search`): call directly; requires API Key, returns recovery_hint if not configured
2. **Free search/extract Skills** (e.g. jina-reader): via `nodes` with curl, zero deps. Example: `curl -sS -L --max-time 30 -H 'Accept: application/json' 'https://s.jina.ai/keyword'`
3. **Cloud delegation** (`cloud_agent`): when local search is unavailable, or user explicitly requests deep research
4. **Crawler Skills** (e.g. Crawl4AI): for batch crawling or anti-detection scenarios
- **ABSOLUTELY FORBIDDEN**: Do NOT open Safari/browsers (`open -a Safari`, `osascript`) for manual search! Do NOT use `observe_screen` to read web pages!

**Prohibited actions:**
- For regular Skills (no `backend_type`): Do NOT call Skill names as tool names — execute code via `nodes`
- For `backend_type="tool"` Skills: Do NOT use nodes to read SKILL.md or execute code — call the `tool_name` tool directly
- Do NOT pass Skill names (like `cloud-agent`, `ddg-search`) as `api_name` to `api_calling` — they are NOT registered APIs
- Do NOT install system-level software (homebrew, node, java, docker, etc.) speculatively — this is beyond Skill dependency scope
- Do NOT install a chain of prerequisites without confirming the end result will actually work
- Before installing any non-pip system-level dependency, MUST use hitl tool to get user consent with clear justification
- Do NOT install first then tell user "installed but can't use" — assess feasibility BEFORE installation

**Constraints:**
- Never read more than one skill up front
- For advanced usage, Read the full SKILL.md at `location` path
""".strip()

    @staticmethod
    def build_eager_prompt(
        skills_content: List[tuple[str, str]],
        language: str = "zh",
    ) -> str:
        """
        构建全量加载 Prompt（注入完整 SKILL.md 内容）

        Args:
            skills_content: [(skill_name, skill_md_content), ...]
            language: 语言（zh/en）

        Returns:
            完整的 Skills 内容
        """
        if not skills_content:
            return ""

        lines = ["# 可用技能" if language == "zh" else "# Available Skills", ""]

        for skill_name, content in skills_content:
            lines.append(f"## {skill_name}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

        prompt = "\n".join(lines)

        logger.debug(
            f"构建全量加载 Skills Prompt: {len(skills_content)} 个技能, {len(prompt)} 字符"
        )

        return prompt

    # ================================================================
    # 目录扫描 + Prompt 构建
    # ================================================================

    @classmethod
    def build_from_skill_dir(
        cls,
        skills_dir: Path,
        mode: str = "lazy",
        language: str = "zh",
    ) -> str:
        """
        从单个 Skills 目录构建 Prompt

        Args:
            skills_dir: Skills 目录路径
            mode: 加载模式（lazy/eager）
            language: 语言（zh/en）

        Returns:
            构建的 Prompt
        """
        return cls.build_from_skill_dirs([skills_dir], mode=mode, language=language)

    @classmethod
    def build_from_skill_dirs(
        cls,
        skill_dirs: List[Path],
        mode: str = "lazy",
        language: str = "zh",
    ) -> str:
        """
        从多个 Skills 目录构建 Prompt，按优先级合并（列表中靠前的优先，同名不覆盖）

        典型顺序：workspace（./skills/）> instance（instances/{id}/skills/）> bundled（skills/library/）

        Args:
            skill_dirs: 目录列表，优先级从高到低
            mode: 加载模式（lazy/eager）
            language: 语言（zh/en）

        Returns:
            构建的 Prompt
        """
        if not skill_dirs:
            return ""

        # 按优先级合并：列表中靠前的目录优先，已存在的同名 skill 不再被覆盖
        merged: Dict[str, SkillSummary] = {}
        for skills_dir in skill_dirs:
            if not skills_dir or not Path(skills_dir).exists():
                continue
            skill_files = list(Path(skills_dir).glob("*/SKILL.md"))
            for skill_file in skill_files:
                summary = cls._parse_skill_summary(skill_file)
                if summary and summary.name not in merged:
                    merged[summary.name] = summary

        if not merged:
            logger.info(f"未在 {skill_dirs} 中发现 Skills")
            return ""

        summaries = list(merged.values())

        if mode == "lazy":
            return cls.build_lazy_prompt(summaries, language)

        # eager: 按 merged 顺序加载完整内容
        skills_content = []
        for summary in summaries:
            try:
                content = summary.location.read_text(encoding="utf-8")
                skills_content.append((summary.name, content))
            except Exception as e:
                logger.warning(f"读取 {summary.location} 失败: {e}")
        return cls.build_eager_prompt(skills_content, language)

    # ================================================================
    # Frontmatter 解析（单一入口，DRY）
    # ================================================================

    @classmethod
    def _parse_frontmatter(cls, content: str) -> Optional[dict]:
        """
        Parse YAML frontmatter from SKILL.md content.

        Delegates to core.skill.frontmatter.parse_skill_frontmatter.
        """
        from core.skill.frontmatter import parse_skill_frontmatter
        return parse_skill_frontmatter(content)

    @classmethod
    def _parse_skill_summary(cls, skill_file: Path) -> Optional[SkillSummary]:
        """
        解析 SKILL.md frontmatter 提取简要信息

        Args:
            skill_file: SKILL.md 文件路径

        Returns:
            SkillSummary 或 None
        """
        try:
            content = skill_file.read_text(encoding="utf-8")
            meta = cls._parse_frontmatter(content)
            if not meta:
                return None

            # name: 优先 frontmatter，回退目录名
            name = meta.get("name")
            if not isinstance(name, str) or not name:
                name = skill_file.parent.name

            # description: 必填
            description = meta.get("description", "")
            if not description:
                logger.debug(f"Skill {name} 缺少 description")
                return None

            # emoji: 从 metadata.emoji 或顶层 emoji
            emoji = ""
            metadata_block = meta.get("metadata", {})
            if isinstance(metadata_block, dict):
                emoji = str(metadata_block.get("emoji", ""))[:2]
            if not emoji:
                emoji = str(meta.get("emoji", ""))[:2]

            # requires: bins / env
            # 优先顶层 requires，fallback 到 metadata.moltbot.requires
            requires = meta.get("requires") or {}
            if not isinstance(requires, dict):
                requires = {}

            if not requires and isinstance(metadata_block, dict):
                moltbot = metadata_block.get("moltbot", {})
                if isinstance(moltbot, dict):
                    moltbot_req = moltbot.get("requires", {})
                    if isinstance(moltbot_req, dict):
                        requires = moltbot_req

            requires_bins = _ensure_str_list(requires.get("bins"))
            requires_env = _ensure_str_list(requires.get("env"))

            # parameters: optional structured param schema
            parameters = meta.get("parameters") or []
            if not isinstance(parameters, list):
                parameters = []

            return SkillSummary(
                name=name,
                description=str(description),
                location=skill_file.absolute(),
                emoji=emoji,
                requires_bins=requires_bins,
                requires_env=requires_env,
                parameters=parameters,
            )

        except Exception as e:
            logger.warning(f"解析 {skill_file} 失败: {e}")
            return None

    @classmethod
    def parse_requires(cls, skill_md_path: Path) -> Dict[str, List[str]]:
        """
        从 SKILL.md 的 frontmatter 解析 requires（bins、env），供 Loader 合并 gating。

        内部复用 _parse_skill_summary，不重复解析。

        Args:
            skill_md_path: SKILL.md 绝对路径

        Returns:
            {"bins": [...], "env": [...]}
        """
        result: Dict[str, List[str]] = {"bins": [], "env": []}
        try:
            summary = cls._parse_skill_summary(skill_md_path)
            if summary:
                result["bins"] = summary.requires_bins
                result["env"] = summary.requires_env
        except Exception as e:
            logger.debug(f"解析 requires 失败 {skill_md_path}: {e}")
        return result


# ================================================================
# 辅助函数
# ================================================================


def _ensure_str_list(value: object) -> List[str]:
    """Normalize YAML value to List[str]: handles str, list, None."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return []


# ================================================================
# 便捷函数
# ================================================================


def build_skills_prompt(
    skills_dir: Path,
    mode: str = "lazy",
    language: str = "zh",
) -> str:
    """
    构建 Skills Prompt（便捷函数）

    Args:
        skills_dir: Skills 目录路径
        mode: 加载模式（lazy/eager）
        language: 语言（zh/en）

    Returns:
        构建的 Prompt
    """
    return SkillPromptBuilder.build_from_skill_dir(skills_dir, mode, language)


def build_skills_instructions(
    language: str = "zh",
    instance_name: str = "",
) -> str:
    """
    构建 Skills 使用指令（便捷函数）

    Args:
        language: 语言（zh/en）
        instance_name: 实例名称（用于 Skill 路径）

    Returns:
        系统指令文本
    """
    return SkillPromptBuilder.build_lazy_instructions(language, instance_name=instance_name)
