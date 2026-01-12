"""
SkillWorker - Claude Skills Worker

将 Claude Skills 作为专业 Worker

Claude Skills 是预定义的专业能力模块，包含：
- System Prompt：专业角色定义
- Few-shot Examples：示例引导
- Output Schema：结构化输出约束
- Tool Definitions：专用工具

参考：https://platform.claude.com/docs/en/build-with-claude/prompt-engineering

优势：
1. 高度专业化：针对特定任务优化的 prompt engineering
2. 可复用：一次开发，多处使用
3. 质量保证：Few-shot 示例确保输出质量
4. 结构化输出：Schema 约束确保格式一致
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class SkillWorker(BaseWorker):
    """
    Skill Worker - 使用 Claude Skills 执行专业任务
    
    Claude Skills 是一种高级的 prompt engineering 模式，
    将专业知识封装为可复用的能力模块。
    
    Skill 目录结构：
        skills/library/pptx-generator/
        ├── SKILL.md          # Skill 定义（包含 system prompt、examples）
        ├── schema.json       # 输出 Schema（可选）
        └── tools/            # 专用工具定义（可选）
    
    Example:
        worker = SkillWorker(
            name="pptx-generator",
            skill_path=Path("skills/library/pptx-generator"),
            specialization="document_creation"
        )
        
        result = await worker.execute(WorkerInput(
            task_id="task-1",
            action="创建一个关于 AI 趋势的 PPT"
        ))
    
    配置示例 (worker_registry.yaml):
        workers:
          - name: pptx-worker
            type: skill
            specialization: document_creation
            skill_id: pptx-generator
            # 或指定路径
            skill_path: "skills/library/pptx-generator"
    """
    
    def __init__(
        self,
        name: str,
        skill_id: str = None,
        skill_path: Path = None,
        skills_base_dir: Path = None,
        specialization: str = "general",
        model: str = "claude-sonnet-4-5-20250929",
        max_turns: int = 10,
        config: Optional[Dict[str, Any]] = None
    ):
        # 扩展 WorkerType
        super().__init__(
            name=name,
            worker_type=WorkerType.AGENT,  # 底层还是 Agent，但使用 Skill
            specialization=specialization,
            config=config
        )
        
        self.skill_id = skill_id or name
        self.model = model
        self.max_turns = max_turns
        
        # 解析 Skill 路径
        self.skill_path = self._resolve_skill_path(skill_path, skills_base_dir)
        
        # 加载 Skill 定义
        self.skill_definition = self._load_skill_definition()
        
        self._agent = None
        
        logger.info(f"SkillWorker 初始化: {name} (Skill: {self.skill_id})")
    
    def _resolve_skill_path(self, skill_path: Path, base_dir: Path) -> Path:
        """解析 Skill 路径"""
        if skill_path and skill_path.exists():
            return skill_path
        
        # 默认搜索路径
        search_paths = [
            Path("skills/library") / self.skill_id,
            Path("skills/custom_claude_skills") / self.skill_id,
        ]
        
        if base_dir:
            search_paths.insert(0, base_dir / self.skill_id)
        
        for path in search_paths:
            if path.exists():
                return path
        
        raise ValueError(f"Skill '{self.skill_id}' 未找到，搜索路径: {search_paths}")
    
    def _load_skill_definition(self) -> Dict[str, Any]:
        """
        加载 Skill 定义
        
        解析 SKILL.md 文件，提取：
        - system_prompt：系统提示词
        - examples：Few-shot 示例
        - output_schema：输出 Schema
        - tools：专用工具定义
        """
        skill_file = self.skill_path / "SKILL.md"
        if not skill_file.exists():
            raise ValueError(f"Skill 定义文件不存在: {skill_file}")
        
        skill_content = skill_file.read_text(encoding="utf-8")
        
        # 解析 SKILL.md 结构
        definition = {
            "raw_content": skill_content,
            "system_prompt": self._extract_system_prompt(skill_content),
            "examples": self._extract_examples(skill_content),
            "output_schema": self._load_output_schema(),
            "tools": self._load_skill_tools(),
        }
        
        logger.debug(f"Skill '{self.skill_id}' 定义加载完成")
        return definition
    
    def _extract_system_prompt(self, content: str) -> str:
        """
        从 SKILL.md 提取系统提示词
        
        SKILL.md 格式通常是整个文件作为 system prompt
        """
        # 移除可能的 frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                content = parts[2].strip()
        
        return content
    
    def _extract_examples(self, content: str) -> List[Dict]:
        """
        从 SKILL.md 提取 Few-shot 示例
        
        查找 <example> 标签
        """
        import re
        examples = []
        
        # 匹配 <example>...</example> 块
        pattern = r'<example>(.*?)</example>'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            examples.append({"content": match.strip()})
        
        return examples
    
    def _load_output_schema(self) -> Optional[Dict]:
        """加载输出 Schema"""
        schema_file = self.skill_path / "schema.json"
        if schema_file.exists():
            return json.loads(schema_file.read_text(encoding="utf-8"))
        return None
    
    def _load_skill_tools(self) -> List[Dict]:
        """加载 Skill 专用工具"""
        tools_dir = self.skill_path / "tools"
        if not tools_dir.exists():
            return []
        
        tools = []
        for tool_file in tools_dir.glob("*.json"):
            try:
                tool_def = json.loads(tool_file.read_text(encoding="utf-8"))
                tools.append(tool_def)
            except Exception as e:
                logger.warning(f"加载工具定义失败: {tool_file} - {e}")
        
        return tools
    
    def _get_or_create_agent(self):
        """获取或创建使用 Skill 的 Agent"""
        if self._agent is None:
            from core.agent import SimpleAgent
            
            # 构建增强的 system prompt
            system_prompt = self._build_skill_system_prompt()
            
            self._agent = SimpleAgent(
                model=self.model,
                max_turns=self.max_turns,
                system_prompt=system_prompt
            )
            
            logger.info(f"SkillWorker '{self.name}' 创建 Agent (Skill: {self.skill_id})")
        
        return self._agent
    
    def _build_skill_system_prompt(self) -> str:
        """
        构建基于 Skill 的系统提示词
        
        结合 Skill 定义和 Claude 4.5 最佳实践
        """
        parts = [self.skill_definition["system_prompt"]]
        
        # 添加输出 Schema 约束
        if self.skill_definition.get("output_schema"):
            schema_str = json.dumps(self.skill_definition["output_schema"], indent=2, ensure_ascii=False)
            parts.append(f"\n\n## Output Schema\n请确保输出符合以下 Schema：\n```json\n{schema_str}\n```")
        
        return "\n".join(parts)
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        使用 Skill 执行任务
        """
        start_time = datetime.now()
        
        try:
            agent = self._get_or_create_agent()
            
            # 构建任务上下文（包含依赖结果）
            task_context = self._build_task_context(input)
            
            logger.info(f"SkillWorker '{self.name}' 执行任务 (Skill: {self.skill_id}): {input.action[:50]}...")
            
            # 执行 Agent
            final_response = ""
            artifacts = []
            
            async for event in agent.chat(
                user_input=task_context,
                session_id=f"skill-worker-{self.name}-{input.task_id}"
            ):
                if event.get("type") == "content_delta":
                    delta = event.get("data", {}).get("delta", "")
                    if isinstance(delta, str):
                        final_response += delta
                
                if event.get("type") == "artifact":
                    artifacts.append(event.get("data", {}))
            
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"SkillWorker '{self.name}' 完成，耗时 {duration:.1f}s")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.COMPLETED,
                result=final_response,
                artifacts=artifacts,
                duration=duration,
                metadata={
                    "skill_id": self.skill_id,
                    "model": self.model,
                    "worker_type": "skill"
                }
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"SkillWorker '{self.name}' 执行失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    def _build_task_context(self, input: WorkerInput) -> str:
        """构建任务上下文"""
        parts = [input.action]
        
        if input.dependencies_results:
            parts.append("\n\n## 前置任务结果\n")
            for task_id, result in input.dependencies_results.items():
                parts.append(f"### {task_id}\n{result}\n")
        
        if input.context:
            parts.append("\n\n## 上下文信息\n")
            for key, value in input.context.items():
                parts.append(f"- {key}: {value}")
        
        return "\n".join(parts)
    
    async def health_check(self) -> bool:
        """健康检查"""
        return self.skill_path.exists() and (self.skill_path / "SKILL.md").exists()
    
    def get_skill_info(self) -> Dict[str, Any]:
        """获取 Skill 信息"""
        return {
            "skill_id": self.skill_id,
            "skill_path": str(self.skill_path),
            "has_schema": self.skill_definition.get("output_schema") is not None,
            "tools_count": len(self.skill_definition.get("tools", [])),
            "examples_count": len(self.skill_definition.get("examples", [])),
        }
