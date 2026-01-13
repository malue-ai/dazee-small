"""
提示词结果输出管理器 - PromptResultsWriter

🆕 V5.5: 面向运营的可视化输出

设计原则：
1. 将 LLM 生成的场景化提示词输出到 prompt_results/ 目录
2. 运营人员可以直接查看和编辑
3. 支持检测源文件变化，动态更新
4. 保护运营手动编辑的文件

目录结构：
instances/{instance_name}/
├── prompt.md                    # 原始系统提示词（运营配置）
├── config.yaml                  # Agent 配置
└── prompt_results/              # 生成结果目录
    ├── README.md                # 使用说明
    ├── agent_schema.yaml        # AgentSchema（可编辑）
    ├── intent_prompt.md         # 意图识别专用提示词
    ├── simple_prompt.md         # 简单任务提示词
    ├── medium_prompt.md         # 中等任务提示词
    ├── complex_prompt.md        # 复杂任务提示词
    └── _metadata.json           # 元数据（hash, 时间戳）
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List

import yaml

from logger import get_logger

logger = get_logger("prompt_results_writer")


# ============================================================
# 数据结构
# ============================================================

@dataclass
class PromptResultsMetadata:
    """
    提示词结果元数据
    
    用于检测源文件变化和运营手动编辑
    """
    version: str = "1.0"
    generated_at: str = ""
    
    # 源文件哈希（用于检测 prompt.md / config.yaml 变化）
    source_hashes: Dict[str, str] = field(default_factory=dict)
    
    # 生成结果哈希（用于检测运营手动编辑）
    result_hashes: Dict[str, str] = field(default_factory=dict)
    
    # 标记为运营手动编辑的文件（不会被自动覆盖）
    manually_edited: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptResultsMetadata":
        return cls(
            version=data.get("version", "1.0"),
            generated_at=data.get("generated_at", ""),
            source_hashes=data.get("source_hashes", {}),
            result_hashes=data.get("result_hashes", {}),
            manually_edited=data.get("manually_edited", [])
        )


@dataclass
class PromptResults:
    """
    提示词生成结果
    
    包含 AgentSchema 和各场景化提示词
    """
    # AgentSchema（YAML 格式）
    agent_schema: Dict[str, Any] = field(default_factory=dict)
    
    # 场景化提示词
    intent_prompt: str = ""
    simple_prompt: str = ""
    medium_prompt: str = ""
    complex_prompt: str = ""


# ============================================================
# README 模板
# ============================================================

README_TEMPLATE = """# 生成的系统提示词

本目录包含由 LLM 根据 `prompt.md` 自动生成的场景化系统提示词。

## 文件说明

| 文件 | 用途 | 可编辑 |
|------|------|--------|
| agent_schema.yaml | Agent 配置（组件、工具、参数） | ✅ 是 |
| intent_prompt.md | 意图识别专用提示词 | ✅ 是 |
| simple_prompt.md | 简单任务处理提示词 | ✅ 是 |
| medium_prompt.md | 中等任务处理提示词 | ✅ 是 |
| complex_prompt.md | 复杂任务处理提示词 | ✅ 是 |

## 运营编辑指南

1. **可以直接编辑**：修改任意 `.md` 或 `.yaml` 文件
2. **修改后自动保护**：系统会检测您的手动修改，下次更新时不会覆盖
3. **强制重新生成**：删除 `_metadata.json` 或在命令行使用 `--force-refresh`

## 更新策略

- 修改 `prompt.md` 后，**未标记为"手动编辑"的文件**会自动更新
- 您手动编辑的文件会被保护，不会被覆盖
- 如需全部重新生成，删除本目录或使用 `--force-refresh`

## 生成时间

{generated_at}
"""


# ============================================================
# 主类
# ============================================================

class PromptResultsWriter:
    """
    提示词结果输出管理器
    
    职责：
    1. 将 LLM 生成的结果写入 prompt_results/ 目录
    2. 检测源文件变化
    3. 检测运营手动编辑
    4. 加载现有结果（优先使用运营手动编辑的版本）
    """
    
    # 结果文件名映射
    RESULT_FILES = {
        "agent_schema": "agent_schema.yaml",
        "intent_prompt": "intent_prompt.md",
        "simple_prompt": "simple_prompt.md",
        "medium_prompt": "medium_prompt.md",
        "complex_prompt": "complex_prompt.md",
    }
    
    def __init__(self, instance_path: Path):
        """
        初始化
        
        Args:
            instance_path: 实例目录路径（如 instances/test_agent/）
        """
        self.instance_path = Path(instance_path)
        self.results_dir = self.instance_path / "prompt_results"
        self.metadata_path = self.results_dir / "_metadata.json"
        
        # 源文件路径
        self.prompt_path = self.instance_path / "prompt.md"
        self.config_path = self.instance_path / "config.yaml"
    
    # ============================================================
    # 公共方法
    # ============================================================
    
    def write_all(self, results: PromptResults) -> bool:
        """
        写入所有生成结果
        
        Args:
            results: 生成的提示词结果
            
        Returns:
            是否写入成功
        """
        try:
            # 确保目录存在
            self.results_dir.mkdir(parents=True, exist_ok=True)
            
            # 加载现有元数据（用于检测手动编辑）
            existing_metadata = self._load_metadata()
            manually_edited = existing_metadata.manually_edited if existing_metadata else []
            
            # 写入各文件
            result_hashes = {}
            
            # 1. AgentSchema (YAML)
            if "agent_schema" not in manually_edited:
                schema_path = self.results_dir / self.RESULT_FILES["agent_schema"]
                schema_content = yaml.dump(
                    results.agent_schema,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False
                )
                schema_path.write_text(schema_content, encoding="utf-8")
                result_hashes["agent_schema"] = self._compute_hash(schema_content)
                logger.info(f"   📄 写入 {self.RESULT_FILES['agent_schema']}")
            else:
                logger.info(f"   ⏭️ 跳过 {self.RESULT_FILES['agent_schema']}（运营手动编辑）")
            
            # 2. 场景化提示词
            prompt_fields = [
                ("intent_prompt", results.intent_prompt),
                ("simple_prompt", results.simple_prompt),
                ("medium_prompt", results.medium_prompt),
                ("complex_prompt", results.complex_prompt),
            ]
            
            for field_name, content in prompt_fields:
                if field_name not in manually_edited:
                    file_path = self.results_dir / self.RESULT_FILES[field_name]
                    file_path.write_text(content, encoding="utf-8")
                    result_hashes[field_name] = self._compute_hash(content)
                    logger.info(f"   📄 写入 {self.RESULT_FILES[field_name]}")
                else:
                    logger.info(f"   ⏭️ 跳过 {self.RESULT_FILES[field_name]}（运营手动编辑）")
            
            # 3. 写入 README
            readme_path = self.results_dir / "README.md"
            readme_content = README_TEMPLATE.format(
                generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            readme_path.write_text(readme_content, encoding="utf-8")
            
            # 4. 写入元数据
            metadata = PromptResultsMetadata(
                version="1.0",
                generated_at=datetime.now().isoformat(),
                source_hashes={
                    "prompt.md": self._get_source_hash(self.prompt_path),
                    "config.yaml": self._get_source_hash(self.config_path),
                },
                result_hashes=result_hashes,
                manually_edited=manually_edited,
            )
            self._save_metadata(metadata)
            
            logger.info(f"✅ 已写入 prompt_results/ 目录: {self.results_dir}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 写入 prompt_results 失败: {e}")
            return False
    
    def should_regenerate(self) -> Dict[str, bool]:
        """
        检查哪些文件需要重新生成
        
        Returns:
            字典，键为文件名，值为是否需要重新生成
        """
        result = {
            "agent_schema": True,
            "intent_prompt": True,
            "simple_prompt": True,
            "medium_prompt": True,
            "complex_prompt": True,
        }
        
        # 如果目录不存在，全部需要生成
        if not self.results_dir.exists():
            logger.info("   📁 prompt_results/ 目录不存在，需要全部生成")
            return result
        
        # 加载元数据
        metadata = self._load_metadata()
        if not metadata:
            logger.info("   📋 元数据不存在，需要全部生成")
            return result
        
        # 检查源文件是否变化
        current_prompt_hash = self._get_source_hash(self.prompt_path)
        current_config_hash = self._get_source_hash(self.config_path)
        
        prompt_changed = current_prompt_hash != metadata.source_hashes.get("prompt.md")
        config_changed = current_config_hash != metadata.source_hashes.get("config.yaml")
        
        if prompt_changed:
            logger.info("   🔄 prompt.md 已变化，需要重新生成")
        if config_changed:
            logger.info("   🔄 config.yaml 已变化，需要重新生成 agent_schema")
        
        # 检测运营手动编辑
        self._detect_manual_edits(metadata)
        
        # 根据变化情况决定哪些需要重新生成
        for file_key in result.keys():
            if file_key in metadata.manually_edited:
                # 运营手动编辑的文件不重新生成
                result[file_key] = False
                logger.info(f"   🛡️ {file_key} 被运营手动编辑，跳过重新生成")
            elif file_key == "agent_schema":
                # agent_schema 在 prompt 或 config 变化时重新生成
                result[file_key] = prompt_changed or config_changed
            else:
                # 其他提示词只在 prompt 变化时重新生成
                result[file_key] = prompt_changed
        
        return result
    
    def load_existing(self) -> Optional[PromptResults]:
        """
        加载现有结果（优先使用运营手动编辑的版本）
        
        Returns:
            已存在的结果，如果不存在返回 None
        """
        if not self.results_dir.exists():
            return None
        
        try:
            results = PromptResults()
            
            # 加载 AgentSchema
            schema_path = self.results_dir / self.RESULT_FILES["agent_schema"]
            if schema_path.exists():
                results.agent_schema = yaml.safe_load(
                    schema_path.read_text(encoding="utf-8")
                ) or {}
            
            # 加载场景化提示词
            for field_name in ["intent_prompt", "simple_prompt", "medium_prompt", "complex_prompt"]:
                file_path = self.results_dir / self.RESULT_FILES[field_name]
                if file_path.exists():
                    setattr(results, field_name, file_path.read_text(encoding="utf-8"))
            
            return results
            
        except Exception as e:
            logger.warning(f"⚠️ 加载现有结果失败: {e}")
            return None
    
    def is_valid(self) -> bool:
        """
        检查现有结果是否有效（所有必需文件都存在）
        
        Returns:
            是否有效
        """
        if not self.results_dir.exists():
            return False
        
        for file_name in self.RESULT_FILES.values():
            if not (self.results_dir / file_name).exists():
                return False
        
        return True
    
    def get_manually_edited_files(self) -> List[str]:
        """
        获取被运营手动编辑的文件列表
        
        Returns:
            文件键名列表
        """
        metadata = self._load_metadata()
        return metadata.manually_edited if metadata else []
    
    def clear(self) -> bool:
        """
        清除所有生成结果
        
        Returns:
            是否成功
        """
        import shutil
        
        if self.results_dir.exists():
            try:
                shutil.rmtree(self.results_dir)
                logger.info(f"🗑️ 已清除 prompt_results/ 目录")
                return True
            except Exception as e:
                logger.error(f"❌ 清除失败: {e}")
                return False
        return True
    
    # ============================================================
    # 私有方法
    # ============================================================
    
    def _compute_hash(self, content: str) -> str:
        """计算内容的哈希值"""
        return hashlib.md5(content.encode("utf-8")).hexdigest()
    
    def _get_source_hash(self, path: Path) -> str:
        """获取源文件的哈希值"""
        if not path.exists():
            return ""
        return self._compute_hash(path.read_text(encoding="utf-8"))
    
    def _load_metadata(self) -> Optional[PromptResultsMetadata]:
        """加载元数据"""
        if not self.metadata_path.exists():
            return None
        
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            return PromptResultsMetadata.from_dict(data)
        except Exception as e:
            logger.warning(f"⚠️ 加载元数据失败: {e}")
            return None
    
    def _save_metadata(self, metadata: PromptResultsMetadata) -> bool:
        """保存元数据"""
        try:
            self.metadata_path.write_text(
                json.dumps(metadata.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            return True
        except Exception as e:
            logger.error(f"❌ 保存元数据失败: {e}")
            return False
    
    def _detect_manual_edits(self, metadata: PromptResultsMetadata) -> None:
        """
        检测运营手动编辑
        
        如果文件内容与记录的哈希不一致，说明被手动编辑了
        """
        for file_key, file_name in self.RESULT_FILES.items():
            file_path = self.results_dir / file_name
            
            if not file_path.exists():
                continue
            
            # 跳过已经标记的
            if file_key in metadata.manually_edited:
                continue
            
            # 计算当前哈希
            current_content = file_path.read_text(encoding="utf-8")
            current_hash = self._compute_hash(current_content)
            
            # 与记录的哈希比较
            recorded_hash = metadata.result_hashes.get(file_key, "")
            
            if current_hash != recorded_hash and recorded_hash:
                # 哈希不一致，说明被手动编辑了
                metadata.manually_edited.append(file_key)
                logger.info(f"   ✏️ 检测到 {file_name} 被运营手动编辑")
                
                # 更新元数据
                self._save_metadata(metadata)


# ============================================================
# 便捷函数
# ============================================================

def create_prompt_results_writer(instance_path: str) -> PromptResultsWriter:
    """
    创建 PromptResultsWriter 实例
    
    Args:
        instance_path: 实例目录路径
        
    Returns:
        PromptResultsWriter 实例
    """
    return PromptResultsWriter(Path(instance_path))
