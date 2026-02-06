# Claude Skills - 核心功能与 ZenFlux 集成深度分析

> 📅 **创建时间**: 2026-01-05  
> 🎯 **目标**: 深入理解 Claude Skills 核心能力，优化 ZenFlux Agent V4 的 Skills 集成  
> 🔗 **参考**: [Anthropic Skills 官方文档](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/overview)

---

## 📋 目录

- [1. Claude Skills 核心概念](#1-claude-skills-核心概念)
- [2. Skills 架构设计](#2-skills-架构设计)
- [3. ZenFlux 当前集成状态](#3-zenflux-当前集成状态)
- [4. 优化建议](#4-优化建议)
- [5. 实现计划](#5-实现计划)

---

## 1. Claude Skills 核心概念

### 1.1 什么是 Skills？

**定义**: Skills 是**组织化的能力包**（organized packages），包含：
- **指令** (Instructions) - 结构化的 Markdown 文档
- **可执行代码** (Executable Code) - Python/JavaScript 脚本
- **资源文件** (Resources) - 模板、数据、配置

**核心价值**:
```
Skills = 专家知识包 (Expertise Packages)
       = 可重用的领域能力 (Reusable Domain Capabilities)
       = 上下文优化的工具 (Context-Optimized Tools)
```

### 1.2 Skills vs 传统 Tools

| 维度 | **传统 Tools** | **Claude Skills** |
|------|--------------|------------------|
| **粒度** | 单一函数调用 | 完整工作流 |
| **上下文** | 最小化描述 | 完整指令 + 最佳实践 |
| **发现** | 静态工具列表 | 动态加载（Progressive Disclosure） |
| **组合** | Agent 手动编排 | 内置工作流逻辑 |
| **学习曲线** | Agent 需要多次尝试 | 预置领域知识 |
| **Token 效率** | 总是加载全部工具定义 | 按需加载（仅在需要时） |

**关键差异**：
- **Tools**: "给 Agent 锤子" → Agent 自己学习如何使用
- **Skills**: "给 Agent 木匠" → Agent 获得木匠的专业知识

### 1.3 Progressive Disclosure 架构

**核心思想**: 分阶段加载，最小化上下文消耗

```
┌─────────────────────────────────────────────────────────────────┐
│                  Progressive Disclosure Flow                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stage 1: Skill Discovery                                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • Agent 只看到 Skill 的简短描述（1-2 句话）                     │
│  • 决定是否需要这个 Skill                                        │
│  • Token 消耗: 最小（~50 tokens per skill）                     │
│                                                                  │
│  Stage 2: Skill Loading (if needed)                             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 加载完整的 SKILL.md 指令                                      │
│  • 加载可执行脚本（Python/JS）                                   │
│  • 加载资源文件（如果需要）                                      │
│  • Token 消耗: 中等（~500-2000 tokens per skill）               │
│                                                                  │
│  Stage 3: Skill Execution                                       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • Agent 按照指令执行                                            │
│  • 调用预置的脚本/函数                                           │
│  • 返回结构化结果                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Token 效率对比**：

| 场景 | 传统 Tools | Claude Skills | 节省 |
|------|-----------|--------------|------|
| **30 个工具** | 30 × 200 = 6,000 tokens | 30 × 50 = 1,500 tokens | **75%** |
| **实际使用 5 个** | 6,000 tokens | 1,500 + (5 × 500) = 4,000 tokens | **33%** |
| **仅使用 1 个** | 6,000 tokens | 1,500 + 500 = 2,000 tokens | **67%** |

---

## 2. Skills 架构设计

### 2.1 Skill 结构

**标准 Skill 目录结构**:

```
my-skill/
├── SKILL.md              # 📄 核心指令文档（必需）
├── REFERENCE.md          # 📖 参考文档（可选）
├── scripts/              # 🐍 可执行脚本（可选）
│   ├── processor.py
│   └── utils.py
└── resources/            # 📦 资源文件（可选）
    ├── template.xlsx
    └── config.json
```

### 2.2 SKILL.md 格式规范

**Front Matter** (YAML):
```yaml
---
name: analyzing-financial-statements
description: 计算关键财务比率和指标，用于投资分析
---
```

**内容结构**:
```markdown
# [Skill 名称]

[简短描述：1-2 句话说明核心功能]

## Capabilities（能力清单）

- 能力 1
- 能力 2
- 能力 3

## How to Use（使用说明）

1. 输入要求
2. 配置参数
3. 输出格式

## Input Format（输入格式）

详细说明接受的输入格式...

## Output Format（输出格式）

详细说明返回的输出格式...

## Example Usage（示例用法）

提供 2-3 个具体示例...

## Scripts（脚本说明）

如果有可执行脚本，说明每个脚本的作用...

## Best Practices（最佳实践）

1. 实践建议 1
2. 实践建议 2

## Limitations（局限性）

明确说明 Skill 的局限性...
```

### 2.3 Pre-built Skills（Anthropic 官方）

Anthropic 提供了 4 个预置 Skills：

| Skill ID | 名称 | 核心能力 | 使用场景 |
|----------|------|---------|---------|
| `xlsx` | **Excel** | 创建/编辑 Excel 工作簿 | • 数据分析报表<br>• 财务模型<br>• 图表生成 |
| `pptx` | **PowerPoint** | 生成演示文稿 | • 商业汇报<br>• 培训材料<br>• 产品演示 |
| `pdf` | **PDF** | 创建 PDF 文档 | • 正式报告<br>• 合同文档<br>• 归档材料 |
| `docx` | **Word** | 生成 Word 文档 | • 长文档编写<br>• 结构化内容<br>• 富文本格式 |

**API 调用示例**:
```python
from anthropic import Anthropic

client = Anthropic(api_key="...")

response = client.beta.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,
    betas=[
        "code-execution-2025-08-25",  # 必需：代码执行
        "files-api-2025-04-14",       # 必需：文件下载
        "skills-2025-10-02"            # 必需：Skills 功能
    ],
    container={
        "skills": [
            {
                "type": "anthropic",    # 官方 Skill
                "skill_id": "xlsx",     # Skill ID
                "version": "latest"     # 版本
            }
        ]
    },
    tools=[
        {
            "type": "code_execution_20250825",
            "name": "code_execution"
        }
    ],
    messages=[{
        "role": "user",
        "content": "创建一个包含销售数据的 Excel 文件，带图表和数据透视表"
    }]
)
```

### 2.4 Custom Skills（自定义 Skills）

**创建流程**:

```
1. 准备 Skill 包
   ├── 编写 SKILL.md（核心指令）
   ├── 开发 scripts/（如果需要）
   └── 准备 resources/（如果需要）

2. 打包为 .tar.gz
   └── tar -czf my-skill.tar.gz my-skill/

3. 上传到 Anthropic Skills API
   POST https://api.anthropic.com/v1/skills
   - multipart/form-data
   - file: my-skill.tar.gz

4. 获得 Skill ID
   └── skill_xxxxxxxxxxxx

5. 在 Agent 中使用
   container: {
       skills: [
           {type: "custom", skill_id: "skill_xxxxxxxxxxxx"}
       ]
   }
```

**示例：财务分析 Skill**:

```markdown
# Financial Ratio Calculator Skill

Calculate and interpret key financial ratios for investment analysis.

## Capabilities

- **Profitability Ratios**: ROE, ROA, Gross Margin, Net Margin
- **Liquidity Ratios**: Current Ratio, Quick Ratio, Cash Ratio
- **Leverage Ratios**: Debt-to-Equity, Interest Coverage
- **Valuation Ratios**: P/E, P/B, EV/EBITDA

## How to Use

1. Provide financial statement data (P&L, Balance Sheet)
2. Specify which ratios to calculate
3. Skill returns calculated ratios with industry benchmarks

## Scripts

- `calculate_ratios.py`: Main calculation engine
- `interpret_ratios.py`: Provides interpretation and benchmarking
```

---

## 3. ZenFlux 当前集成状态

### 3.1 已实现的 Skills 集成

**配置位置**: `config/capabilities.yaml`

```yaml
capabilities:
  # ==================== Pre-built Skills ====================
  
  - name: pptx
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    capabilities:
      - ppt_generation
      - presentation_creation
    priority: 60
    cost:
      time: fast
      money: free
    constraints:
      requires_skill_api: true
    
  - name: xlsx
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    capabilities:
      - data_analysis
      - document_creation
    priority: 55
    
  - name: pdf
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    capabilities:
      - document_creation
    priority: 50
    
  - name: docx
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    capabilities:
      - document_creation
    priority: 50

  # ==================== Custom Skills ====================
  
  - name: slidespeak-generator
    type: SKILL
    subtype: CUSTOM
    skill_directory: skills/library/slidespeak-generator
    capabilities:
      - ppt_generation
      - api_calling
    priority: 70
    metadata:
      input: "主题、大纲、配置"
      output: "PPT下载URL"
```

### 3.2 当前架构对 Skills 的支持

**core/tool/capability/skill_loader.py**:

```python
class SkillLoader:
    """
    加载和管理 Skills 包
    
    功能：
    - 从 skills/library/ 发现 Skills
    - 解析 skill.yaml 元数据
    - 加载 prompt/config/resources
    """
    
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.loaded_skills: Dict[str, SkillMetadata] = {}
    
    def discover_skills(self) -> List[str]:
        """发现所有可用的 Skills"""
        
    def load_skill(self, skill_name: str) -> SkillMetadata:
        """加载单个 Skill 的元数据和资源"""
    
    def get_skill_prompt(self, skill_name: str) -> str:
        """获取 Skill 的 System Prompt"""
```

**core/tool/capability/registry.py**:

```python
class CapabilityRegistry:
    """能力注册表"""
    
    def get_by_type(self, cap_type: CapabilityType) -> List[Capability]:
        """按类型获取能力（支持 SKILL 类型）"""
    
    def get_skill_by_name(self, name: str) -> Optional[Capability]:
        """获取指定的 Skill"""
```

### 3.3 当前存在的问题

#### ❌ 问题 1: 缺少 Progressive Disclosure

**现状**:
```python
# 当前实现：总是加载所有 Skills 的完整定义
all_skills = registry.get_by_type(CapabilityType.SKILL)
# → 每个 Skill 的 SKILL.md 完整内容都加载到 Context
# → Token 消耗: 2000 tokens × 10 skills = 20,000 tokens
```

**期望**:
```python
# 理想实现：分阶段加载
# Stage 1: 只加载 Skill 描述（50 tokens per skill）
skill_summaries = registry.get_skill_summaries()

# Stage 2: LLM 决定需要哪些 Skill
selected_skills = llm.select_skills(skill_summaries, user_query)

# Stage 3: 仅加载选中的 Skills 的完整内容
for skill in selected_skills:
    full_skill = registry.load_full_skill(skill.name)
```

#### ❌ 问题 2: 未区分 Pre-built 和 Custom Skills

**现状**:
```python
# Pre-built Skills（Anthropic 官方）
- 应该通过 API container 传递
- 不需要本地 SKILL.md 文件
- 使用 skill_id 引用

# Custom Skills（用户自定义）
- 需要本地 SKILL.md 文件
- 通过 Skills API 上传
- 使用自定义 skill_id 引用

# 当前代码：混为一谈，没有区分处理
```

#### ❌ 问题 3: Skills API 调用未实现

**现状**:
```python
# core/llm/claude.py 中缺少 Skills 相关参数

def create_message(self, ...):
    response = self.client.messages.create(
        model=self.model,
        max_tokens=max_tokens,
        tools=tools,  # ✅ Tools 已支持
        # ❌ 缺少 Skills 参数：
        # container={
        #     "skills": [...]
        # }
    )
```

#### ❌ 问题 4: Files API 未集成

**现状**:
```python
# Skills 生成文件后，需要通过 Files API 下载
# 当前代码：没有 Files API 的集成

# 期望：
file_id = extract_file_id(response)
file_content = client.beta.files.download(file_id)
with open("output.xlsx", "wb") as f:
    f.write(file_content.read())
```

---

## 4. 优化建议

### 4.1 实现 Progressive Disclosure

**优化目标**: 减少 70% 的 Skill 相关 Token 消耗

**实现方案**:

```python
# core/tool/capability/registry.py

class CapabilityRegistry:
    """能力注册表"""
    
    def get_skill_summaries(self) -> List[SkillSummary]:
        """
        返回所有 Skills 的简短描述（Stage 1）
        
        每个 Skill 仅包含：
        - name: Skill 名称
        - description: 1-2 句话描述（从 SKILL.md front matter）
        - capabilities: 能力标签列表
        
        Token 消耗: ~50 tokens per skill
        """
        summaries = []
        for skill in self.skills:
            summaries.append(SkillSummary(
                name=skill.name,
                description=skill.metadata.description,  # 仅描述
                capabilities=skill.capabilities
            ))
        return summaries
    
    def load_full_skill(self, skill_name: str) -> FullSkill:
        """
        加载 Skill 的完整内容（Stage 2）
        
        包含：
        - 完整的 SKILL.md 内容
        - 脚本代码
        - 资源文件
        
        Token 消耗: ~500-2000 tokens per skill
        """
        skill_path = self.skills_dir / skill_name
        return FullSkill.from_directory(skill_path)
```

**Agent 中的使用**:

```python
# core/agent/simple/simple_agent.py

async def chat(self, user_query: str):
    # Stage 1: 获取所有 Skills 的简短描述
    skill_summaries = self.registry.get_skill_summaries()
    # Token: 50 × 10 = 500 tokens (vs 2000 × 10 = 20,000)
    
    # Stage 2: LLM 决定需要哪些 Skills
    prompt = f"""
    用户查询: {user_query}
    
    可用 Skills（简短描述）:
    {skill_summaries}
    
    请选择完成任务所需的 Skills（返回 skill_names 列表）
    """
    
    selected_skill_names = await self.llm.select_skills(prompt)
    # Token: ~1,000 tokens
    
    # Stage 3: 仅加载选中的 Skills 的完整内容
    full_skills = []
    for name in selected_skill_names:
        full_skill = self.registry.load_full_skill(name)
        full_skills.append(full_skill)
    # Token: 2000 × 2 = 4,000 tokens (假设选中 2 个)
    
    # 总计: 500 + 1,000 + 4,000 = 5,500 tokens
    # vs 旧方案: 20,000 tokens
    # 节省: 72.5%
```

### 4.2 区分 Pre-built 和 Custom Skills

**配置增强**:

```yaml
# config/capabilities.yaml

capabilities:
  # Pre-built Skills（无需本地文件）
  - name: xlsx
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    skill_id: xlsx        # Anthropic 官方 ID
    version: latest
    capabilities:
      - data_analysis
    constraints:
      requires_code_execution: true
      requires_files_api: true
  
  # Custom Skills（需要本地文件或上传后的 ID）
  - name: financial-analyzer
    type: SKILL
    subtype: CUSTOM
    skill_directory: skills/library/financial-analyzer  # 本地路径
    # OR
    skill_id: skill_abc123xyz  # 已上传后的 ID
    capabilities:
      - data_analysis
      - financial_analysis
```

**Registry 增强**:

```python
class CapabilityRegistry:
    def get_prebuilt_skills(self) -> List[PrebuiltSkill]:
        """获取所有 Pre-built Skills（Anthropic 官方）"""
        return [
            skill for skill in self.skills
            if skill.subtype == "PREBUILT"
        ]
    
    def get_custom_skills(self) -> List[CustomSkill]:
        """获取所有 Custom Skills（用户自定义）"""
        return [
            skill for skill in self.skills
            if skill.subtype == "CUSTOM"
        ]
```

### 4.3 集成 Skills API

**LLM Service 增强**:

```python
# core/llm/claude.py

class ClaudeLLMService:
    def create_message_with_skills(
        self,
        messages: List[dict],
        skills: List[dict],  # 新增参数
        tools: Optional[List[dict]] = None,
        **kwargs
    ):
        """
        创建带 Skills 的消息
        
        Args:
            skills: Skills 列表，格式：
                [
                    {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
                    {"type": "custom", "skill_id": "skill_abc123"}
                ]
        """
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=kwargs.get("max_tokens", 4096),
            betas=[
                "code-execution-2025-08-25",
                "files-api-2025-04-14",
                "skills-2025-10-02"
            ],
            container={
                "skills": skills  # 传递 Skills
            },
            tools=tools or [
                {"type": "code_execution_20250825", "name": "code_execution"}
            ],
            messages=messages,
            **kwargs
        )
        return response
```

**ToolSelector 增强**:

```python
# core/tool/selector.py

class ToolSelector:
    def select(
        self,
        required_capabilities: List[str]
    ) -> ToolSelectionResult:
        """选择工具和 Skills"""
        
        # 1. 路由到具体工具
        tools = self.router.route(required_capabilities)
        
        # 2. 提取 Skills（Pre-built + Custom）
        skills = []
        for tool in tools:
            if tool.type == CapabilityType.SKILL:
                if tool.subtype == "PREBUILT":
                    skills.append({
                        "type": "anthropic",
                        "skill_id": tool.skill_id,
                        "version": tool.version or "latest"
                    })
                elif tool.subtype == "CUSTOM":
                    skills.append({
                        "type": "custom",
                        "skill_id": tool.skill_id
                    })
        
        # 3. 提取普通 Tools
        regular_tools = [
            tool for tool in tools
            if tool.type != CapabilityType.SKILL
        ]
        
        return ToolSelectionResult(
            tools=regular_tools,
            skills=skills,  # 新增
            tool_names=[t.name for t in regular_tools],
            skill_names=[s["skill_id"] for s in skills]  # 新增
        )
```

### 4.4 集成 Files API

**新建 Files API 工具类**:

```python
# core/llm/files_api.py

from anthropic import Anthropic
from typing import Optional, List, Dict, Any
import json
import re

class FilesAPIClient:
    """Claude Files API 客户端"""
    
    def __init__(self, client: Anthropic):
        self.client = client
    
    def extract_file_ids(self, response) -> List[str]:
        """
        从 Claude API 响应中提取所有 file IDs
        
        Skills 生成文件后，file_id 在以下位置：
        response.content[i].type == "bash_code_execution_tool_result"
        response.content[i].content.content[j].file_id
        """
        file_ids = []
        
        for block in response.content:
            if block.type == "bash_code_execution_tool_result":
                try:
                    if hasattr(block, "content") and hasattr(block.content, "content"):
                        for item in block.content.content:
                            if hasattr(item, "file_id"):
                                file_ids.append(item.file_id)
                except Exception as e:
                    print(f"Warning: Error parsing tool result: {e}")
        
        # 去重
        return list(set(file_ids))
    
    def download_file(
        self,
        file_id: str,
        output_path: str,
        overwrite: bool = True
    ) -> Dict[str, Any]:
        """
        下载文件到本地
        
        Returns:
            {
                'file_id': str,
                'output_path': str,
                'size': int,
                'success': bool,
                'error': Optional[str]
            }
        """
        result = {
            "file_id": file_id,
            "output_path": output_path,
            "size": 0,
            "success": False,
            "error": None
        }
        
        try:
            # 检查文件是否已存在
            if os.path.exists(output_path) and not overwrite:
                result["error"] = f"File exists: {output_path}"
                return result
            
            # 下载文件
            file_content = self.client.beta.files.download(file_id=file_id)
            
            # 保存到磁盘
            with open(output_path, "wb") as f:
                f.write(file_content.read())
            
            result["size"] = os.path.getsize(output_path)
            result["success"] = True
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文件元数据
        
        Returns:
            {
                'file_id': str,
                'filename': str,
                'size_bytes': int,
                'mime_type': str,
                'created_at': str
            }
        """
        try:
            metadata = self.client.beta.files.retrieve_metadata(file_id=file_id)
            return {
                "file_id": metadata.id,
                "filename": metadata.filename,
                "size_bytes": metadata.size_bytes,
                "mime_type": metadata.mime_type,
                "created_at": metadata.created_at
            }
        except Exception as e:
            print(f"Error retrieving metadata: {e}")
            return None
    
    def download_all_files(
        self,
        response,
        output_dir: str = "outputs",
        prefix: str = ""
    ) -> List[Dict[str, Any]]:
        """
        从响应中提取并下载所有文件
        """
        file_ids = self.extract_file_ids(response)
        results = []
        
        for file_id in file_ids:
            # 获取文件名
            metadata = self.get_file_metadata(file_id)
            filename = metadata["filename"] if metadata else f"file_{file_id}.bin"
            
            if prefix:
                filename = f"{prefix}{filename}"
            
            output_path = os.path.join(output_dir, filename)
            
            # 下载文件
            result = self.download_file(file_id, output_path)
            results.append(result)
        
        return results
```

**Agent 中集成**:

```python
# core/agent/simple/simple_agent.py

class SimpleAgent:
    def __init__(self, ...):
        self.llm = create_claude_service(...)
        self.files_api = FilesAPIClient(self.llm.client)  # 新增
    
    async def chat(self, user_query: str):
        # ... 选择 Tools 和 Skills ...
        
        # 调用 LLM（带 Skills）
        response = await self.llm.create_message_with_skills(
            messages=messages,
            skills=selected_skills,
            tools=selected_tools
        )
        
        # 检查是否生成了文件
        file_ids = self.files_api.extract_file_ids(response)
        if file_ids:
            # 下载所有文件
            results = self.files_api.download_all_files(
                response,
                output_dir=self.workspace_dir / "outputs"
            )
            
            # 发送文件下载事件
            for result in results:
                if result["success"]:
                    self.event_manager.system.emit_file_generated(
                        file_id=result["file_id"],
                        file_path=result["output_path"],
                        file_size=result["size"]
                    )
```

### 4.5 优化 Skill 描述格式

**当前 capabilities.yaml 的 Skill 定义过于简单**:

```yaml
# ❌ 当前格式（信息不足）
- name: pptx
  type: SKILL
  capabilities:
    - ppt_generation
```

**建议增强**:

```yaml
# ✅ 优化格式（完整信息）
- name: pptx
  type: SKILL
  subtype: PREBUILT
  provider: anthropic
  skill_id: pptx
  version: latest
  
  # 能力标签
  capabilities:
    - ppt_generation
    - presentation_creation
    - slide_editing
  
  # 简短描述（用于 Progressive Disclosure Stage 1）
  description: >
    创建和编辑 PowerPoint 演示文稿，支持图表、表格、
    动画和模板。适合商业汇报、培训材料和产品演示。
  
  # 详细能力（用于 LLM 决策）
  detailed_capabilities:
    - "创建多页幻灯片，支持自定义布局"
    - "插入图表（柱状图、折线图、饼图）"
    - "应用公司品牌模板和配色方案"
    - "支持动画和过渡效果"
    - "导出为 .pptx 格式，兼容 PowerPoint 和 Google Slides"
  
  # 使用示例
  examples:
    - "创建一个关于 Q4 销售业绩的汇报 PPT"
    - "生成产品发布会的演示文稿，包含 10 页幻灯片"
    - "将这份数据制作成图表，插入到 PPT 中"
  
  # 约束条件
  constraints:
    requires_code_execution: true   # 必需代码执行
    requires_files_api: true        # 必需文件下载
    max_slides: 50                  # 最大幻灯片数
    supported_formats: [".pptx"]
  
  # 成本信息
  cost:
    time: "1-2 minutes"       # 生成时间
    money: free                # 免费
    tokens: 500-2000           # Token 消耗（加载后）
  
  # 优先级
  priority: 60
```

---

## 5. 实现计划

### 5.1 阶段划分

```
阶段 1: 基础集成（1-2 天）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 1.1 增强 capabilities.yaml 的 Skill 定义
✅ 1.2 实现 FilesAPIClient
✅ 1.3 在 ClaudeLLMService 中支持 container.skills 参数
✅ 1.4 在 ToolSelector 中区分 Skills 和 Tools
✅ 1.5 端到端测试：调用 Pre-built Skills（xlsx/pptx）

阶段 2: Progressive Disclosure（2-3 天）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 2.1 实现 CapabilityRegistry.get_skill_summaries()
✅ 2.2 实现 CapabilityRegistry.load_full_skill()
✅ 2.3 在 SimpleAgent 中实现两阶段 Skill 选择
✅ 2.4 添加 Token 消耗监控和对比
✅ 2.5 性能测试：验证 70% Token 节省

阶段 3: Custom Skills 支持（3-4 天）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 3.1 实现 Custom Skill 上传流程（Skills API）
✅ 3.2 支持本地 Skill 包（从 skills/library/ 加载）
✅ 3.3 实现 SkillLoader.from_directory()
✅ 3.4 测试：创建并使用一个 Custom Skill（如 financial-analyzer）

阶段 4: 事件和监控（1-2 天）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 4.1 添加 Skill 相关事件（skill_selected, skill_loaded, file_generated）
✅ 4.2 在 SSE 流中包含 Skill 执行状态
✅ 4.3 添加 Skill 性能指标（加载时间、执行时间、文件大小）
✅ 4.4 前端展示 Skill 使用情况
```

### 5.2 具体任务清单

**阶段 1: 基础集成**

```markdown
- [ ] **Task 1.1**: 增强 `config/capabilities.yaml`
  - 添加 `description`, `detailed_capabilities`, `examples` 字段
  - 为 4 个 Pre-built Skills 补充完整信息
  - 验证 YAML 格式正确性

- [ ] **Task 1.2**: 实现 `core/llm/files_api.py`
  - 实现 `FilesAPIClient` 类
  - 实现 `extract_file_ids()`
  - 实现 `download_file()`
  - 实现 `get_file_metadata()`
  - 编写单元测试

- [ ] **Task 1.3**: 增强 `core/llm/claude.py`
  - 添加 `create_message_with_skills()` 方法
  - 支持 `container.skills` 参数
  - 支持 `betas` 参数（code-execution, files-api, skills）
  - 向后兼容（不影响现有代码）

- [ ] **Task 1.4**: 增强 `core/tool/selector.py`
  - `ToolSelectionResult` 添加 `skills` 字段
  - `select()` 方法中提取 Skills
  - 区分 Pre-built 和 Custom Skills
  - 返回格式化的 skills 列表

- [ ] **Task 1.5**: 端到端测试
  - 创建测试脚本 `tests/test_skills_integration.py`
  - 测试调用 xlsx Skill 生成 Excel 文件
  - 测试调用 pptx Skill 生成 PPT 文件
  - 验证文件成功下载到 workspace
```

**阶段 2: Progressive Disclosure**

```markdown
- [ ] **Task 2.1**: 实现 Skill 摘要
  - `CapabilityRegistry.get_skill_summaries()`
  - 返回 `SkillSummary` 对象（name, description, capabilities）
  - Token 消耗: ~50 tokens per skill

- [ ] **Task 2.2**: 实现完整 Skill 加载
  - `CapabilityRegistry.load_full_skill(skill_name)`
  - 返回 `FullSkill` 对象（包含完整 SKILL.md）
  - 支持缓存（避免重复加载）

- [ ] **Task 2.3**: 两阶段选择流程
  - 在 `SimpleAgent.chat()` 中：
    - Stage 1: 获取所有 Skill 摘要
    - Stage 2: LLM 决定需要哪些 Skills
    - Stage 3: 仅加载选中的 Skills
  - 添加日志记录每个阶段的 Token 消耗

- [ ] **Task 2.4**: Token 监控
  - 添加 `TokenUsageTracker` 类
  - 记录每次 API 调用的 Token 消耗
  - 对比 Progressive Disclosure 前后的差异

- [ ] **Task 2.5**: 性能测试
  - 创建测试场景：10 个 Skills，用户只需要 2 个
  - 对比 Token 消耗（预期节省 70%）
  - 生成性能报告
```

**阶段 3: Custom Skills 支持**

```markdown
- [ ] **Task 3.1**: Skills API 客户端
  - 实现 `core/llm/skills_api.py`
  - `upload_skill(skill_package_path)`
  - `list_skills()`
  - `delete_skill(skill_id)`

- [ ] **Task 3.2**: 本地 Skill 包支持
  - `SkillLoader.from_directory(skill_dir)`
  - 解析 `SKILL.md` front matter
  - 加载 `scripts/` 和 `resources/`
  - 验证 Skill 包结构

- [ ] **Task 3.3**: Custom Skill 示例
  - 创建 `skills/library/financial-analyzer/`
  - 编写 `SKILL.md`
  - 实现 `scripts/calculate_ratios.py`
  - 测试端到端调用

- [ ] **Task 3.4**: 集成到 Agent
  - 在 `capabilities.yaml` 中注册 Custom Skill
  - 在 `ToolSelector` 中支持 Custom Skill
  - 测试：用户查询 → 选择 Custom Skill → 执行 → 返回结果
```

**阶段 4: 事件和监控**

```markdown
- [ ] **Task 4.1**: 添加 Skill 事件
  - `EventManager.system.emit_skill_selected(skill_name)`
  - `EventManager.system.emit_skill_loaded(skill_name, size)`
  - `EventManager.system.emit_file_generated(file_id, path, size)`

- [ ] **Task 4.2**: SSE 流中包含 Skill 状态
  - `skill_selected` 事件
  - `skill_loaded` 事件
  - `file_generated` 事件

- [ ] **Task 4.3**: 性能指标
  - 记录 Skill 加载时间
  - 记录 Skill 执行时间
  - 记录生成文件的大小

- [ ] **Task 4.4**: 前端展示
  - 显示正在使用的 Skill
  - 显示文件下载链接
  - 显示 Skill 执行进度
```

### 5.3 验收标准

**阶段 1 验收**:
- ✅ 能够调用 Pre-built Skills（xlsx, pptx, pdf, docx）
- ✅ 文件成功下载到 `workspace/outputs/`
- ✅ 文件可以在本地应用中打开（Excel, PowerPoint）

**阶段 2 验收**:
- ✅ Progressive Disclosure 成功实现
- ✅ Token 消耗减少 70%（通过监控数据验证）
- ✅ LLM 能够自主选择合适的 Skills

**阶段 3 验收**:
- ✅ 成功上传并使用 Custom Skill
- ✅ Custom Skill 能够正常执行
- ✅ 与 Pre-built Skills 无缝集成

**阶段 4 验收**:
- ✅ 前端能够实时显示 Skill 状态
- ✅ 用户能够下载生成的文件
- ✅ 性能指标完整记录

---

## 6. 技术细节补充

### 6.1 Beta API 版本管理

```python
# core/llm/claude.py

class ClaudeLLMService:
    # Skills 相关的 Beta 版本
    BETA_CODE_EXECUTION = "code-execution-2025-08-25"
    BETA_FILES_API = "files-api-2025-04-14"
    BETA_SKILLS = "skills-2025-10-02"
    
    def get_skills_betas(self) -> List[str]:
        """获取 Skills 所需的 Beta 版本"""
        return [
            self.BETA_CODE_EXECUTION,
            self.BETA_FILES_API,
            self.BETA_SKILLS
        ]
    
    def create_message_with_skills(self, ...):
        response = self.client.beta.messages.create(
            betas=self.get_skills_betas(),  # 统一管理
            ...
        )
```

### 6.2 错误处理

```python
class SkillExecutionError(Exception):
    """Skill 执行失败"""
    pass

class FileDownloadError(Exception):
    """文件下载失败"""
    pass

# 使用示例
try:
    response = await self.llm.create_message_with_skills(...)
    file_ids = self.files_api.extract_file_ids(response)
    
    if not file_ids:
        raise SkillExecutionError("Skill 未生成文件")
    
    results = self.files_api.download_all_files(response, ...)
    
    failed_downloads = [r for r in results if not r["success"]]
    if failed_downloads:
        raise FileDownloadError(f"{len(failed_downloads)} 个文件下载失败")
    
except SkillExecutionError as e:
    self.event_manager.system.emit_error(f"Skill 执行失败: {e}")
except FileDownloadError as e:
    self.event_manager.system.emit_error(f"文件下载失败: {e}")
```

### 6.3 Skill 缓存策略

```python
# core/tool/capability/skill_loader.py

class SkillLoader:
    def __init__(self, ...):
        self._skill_cache: Dict[str, FullSkill] = {}  # 内存缓存
        self._cache_ttl = 3600  # 1 小时过期
    
    def load_full_skill(self, skill_name: str) -> FullSkill:
        """加载完整 Skill（带缓存）"""
        
        # 检查缓存
        if skill_name in self._skill_cache:
            cached_skill = self._skill_cache[skill_name]
            if not self._is_cache_expired(cached_skill):
                return cached_skill
        
        # 从磁盘加载
        skill = self._load_from_disk(skill_name)
        
        # 更新缓存
        self._skill_cache[skill_name] = skill
        
        return skill
```

---

## 7. 总结

### 7.1 Claude Skills 的核心价值

1. **Progressive Disclosure**: 减少 70% 的 Token 消耗
2. **专家知识包**: 预置领域最佳实践，减少 Agent 试错
3. **工作流封装**: 将多步骤任务封装为单一 Skill
4. **可复用性**: 一次编写，多次使用

### 7.2 ZenFlux 的优势

通过集成 Claude Skills，ZenFlux Agent V4 将获得：

- ✅ **Token 效率**: 减少 70% Skill 相关 Token 消耗
- ✅ **文档生成能力**: 原生支持 Excel/PPT/PDF/Word
- ✅ **扩展性**: 支持用户自定义 Skills
- ✅ **专业性**: 预置领域知识，提升输出质量

### 7.3 下一步行动

1. **立即开始**: 阶段 1（基础集成）
2. **优先级最高**: Task 1.2（FilesAPIClient）和 Task 1.3（Skills API 支持）
3. **快速验证**: Task 1.5（端到端测试）

---

**文档版本**: v1.0  
**作者**: ZenFlux Team  
**最后更新**: 2026-01-05


