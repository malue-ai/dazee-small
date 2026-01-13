"""
Multi-Agent 配置扩展

扩展 instances/xxx/config.yaml 支持 Multi-Agent 配置

向后兼容：
- 如果没有 multi_agent 配置，使用默认值
- 不影响现有的 SimpleAgent 行为
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


class MultiAgentMode(str, Enum):
    """Multi-Agent 模式"""
    DISABLED = "disabled"           # 禁用，使用 SimpleAgent
    AUTO = "auto"                   # 自动判断（基于任务复杂度）
    ENABLED = "enabled"             # 启用 Multi-Agent


@dataclass
class WorkerConfig:
    """Worker 配置"""
    specialization: str
    enabled: bool = True
    max_instances: int = 3
    timeout_seconds: int = 600
    custom_prompt: Optional[str] = None  # 自定义提示词（覆盖 LLM 生成）


@dataclass
class MultiAgentConfig:
    """
    Multi-Agent 配置
    
    在 config.yaml 中的位置：
    
    ```yaml
    multi_agent:
      mode: "auto"
      max_parallel_workers: 5
      execution_strategy: "auto"
      enable_checkpointing: true
      workers:
        research:
          enabled: true
          max_instances: 3
        document:
          enabled: true
        code:
          enabled: true
    ```
    """
    # 基本配置
    # 🆕 V6.0.1: 默认禁用 Multi-Agent，待充分验证后再启用
    mode: MultiAgentMode = MultiAgentMode.DISABLED
    max_parallel_workers: int = 5
    execution_strategy: str = "auto"  # auto | parallel | sequential
    
    # 容错配置
    enable_checkpointing: bool = True
    checkpoint_interval: int = 1
    max_retries: int = 3
    
    # 超时配置
    task_timeout_seconds: int = 3600      # 总任务超时
    worker_timeout_seconds: int = 600     # 单 Worker 超时
    
    # Worker 配置
    workers: Dict[str, WorkerConfig] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiAgentConfig":
        """从字典创建配置"""
        if not data:
            return cls()  # 返回默认配置
        
        # 解析 workers
        workers = {}
        workers_data = data.get("workers", {})
        for spec, worker_data in workers_data.items():
            if isinstance(worker_data, dict):
                workers[spec] = WorkerConfig(
                    specialization=spec,
                    enabled=worker_data.get("enabled", True),
                    max_instances=worker_data.get("max_instances", 3),
                    timeout_seconds=worker_data.get("timeout_seconds", 600),
                    custom_prompt=worker_data.get("custom_prompt")
                )
            else:
                workers[spec] = WorkerConfig(
                    specialization=spec,
                    enabled=bool(worker_data)
                )
        
        return cls(
            mode=MultiAgentMode(data.get("mode", "auto")),
            max_parallel_workers=data.get("max_parallel_workers", 5),
            execution_strategy=data.get("execution_strategy", "auto"),
            enable_checkpointing=data.get("enable_checkpointing", True),
            checkpoint_interval=data.get("checkpoint_interval", 1),
            max_retries=data.get("max_retries", 3),
            task_timeout_seconds=data.get("task_timeout_seconds", 3600),
            worker_timeout_seconds=data.get("worker_timeout_seconds", 600),
            workers=workers
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "mode": self.mode.value,
            "max_parallel_workers": self.max_parallel_workers,
            "execution_strategy": self.execution_strategy,
            "enable_checkpointing": self.enable_checkpointing,
            "checkpoint_interval": self.checkpoint_interval,
            "max_retries": self.max_retries,
            "task_timeout_seconds": self.task_timeout_seconds,
            "worker_timeout_seconds": self.worker_timeout_seconds,
            "workers": {
                spec: {
                    "enabled": worker.enabled,
                    "max_instances": worker.max_instances,
                    "timeout_seconds": worker.timeout_seconds,
                    "custom_prompt": worker.custom_prompt
                }
                for spec, worker in self.workers.items()
            }
        }


def load_multi_agent_config(config_data: Dict[str, Any]) -> MultiAgentConfig:
    """
    从 config.yaml 数据加载 Multi-Agent 配置
    
    向后兼容：如果没有 multi_agent 字段，返回默认配置
    """
    multi_agent_data = config_data.get("multi_agent", {})
    return MultiAgentConfig.from_dict(multi_agent_data)


# ==================== 配置模板 ====================

MULTI_AGENT_CONFIG_TEMPLATE = """
# Multi-Agent 配置（V6.0）
# 
# 控制复杂任务的多 Agent 协作行为
#
# mode 选项：
#   - disabled: 禁用 Multi-Agent，始终使用 SimpleAgent
#   - auto: 自动判断（基于任务复杂度和关键词）
#   - enabled: 始终使用 Multi-Agent
#
multi_agent:
  mode: "auto"                       # disabled | auto | enabled
  max_parallel_workers: 5            # 最大并行 Worker 数
  execution_strategy: "auto"         # auto | parallel | sequential
  
  # 容错配置
  enable_checkpointing: true         # 启用检查点（支持任务恢复）
  max_retries: 3                     # 最大重试次数
  
  # 超时配置
  task_timeout_seconds: 3600         # 总任务超时（秒）
  worker_timeout_seconds: 600        # 单 Worker 超时（秒）
  
  # Worker 配置
  # 每种类型的 Worker 可以单独配置
  # 如果不配置，使用 LLM 自动生成的提示词
  workers:
    research:
      enabled: true
      max_instances: 3
      # custom_prompt: "自定义提示词..."  # 可选，覆盖 LLM 生成
    
    document:
      enabled: true
      max_instances: 2
    
    data_analysis:
      enabled: true
      max_instances: 2
    
    code:
      enabled: true
      max_instances: 3
  
  # 自动触发配置（mode=auto 时生效）
  auto_trigger_keywords:
    - "研究"
    - "分析"
    - "对比"
    - "调研"
    - "重构"
    - "测试"
    - "报告"
    - "PPT"
  auto_trigger_min_complexity: "complex"  # simple | medium | complex
"""
