"""
QoS 评估配置

根据用户 QoS 等级运行不同的评估套件：
- Free: 基础功能评估（响应速度、基本准确性）
- Basic: 标准评估（+ 工具调用、格式规范）
- Pro: 完整评估（+ 复杂推理、上下文理解）
- Enterprise: 全面评估（+ 性能压测、安全审计）

架构位置：evaluation/qos_config.py
依赖：core/context/compaction (QoSLevel)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.context.compaction import QoSLevel
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class QoSEvalConfig:
    """QoS 评估配置"""
    level: QoSLevel
    
    # 评估套件
    suites: List[str] = field(default_factory=list)
    
    # 评估参数
    trials_per_task: int = 3           # 每个任务试验次数
    timeout_seconds: int = 60          # 单任务超时
    max_concurrent: int = 5            # 最大并发数
    
    # Token 限制（用于评估时控制）
    max_input_tokens: int = 150_000    # 单次最大输入 Token
    max_output_tokens: int = 50_000    # 单次最大输出 Token
    
    # 评分阈值
    min_pass_rate: float = 0.8         # 最低通过率
    min_avg_score: float = 0.7         # 最低平均分
    
    # 可选评估项
    enable_performance_test: bool = False   # 性能压测
    enable_security_audit: bool = False     # 安全审计
    enable_stress_test: bool = False        # 压力测试


# ============================================================
# QoS 等级 → 评估配置映射
# ============================================================

QOS_EVAL_CONFIGS: Dict[QoSLevel, QoSEvalConfig] = {
    QoSLevel.FREE: QoSEvalConfig(
        level=QoSLevel.FREE,
        suites=[
            "conversation/basic",      # 基础对话
            "response/speed",          # 响应速度
        ],
        trials_per_task=1,             # 减少试验次数（成本考虑）
        timeout_seconds=30,
        max_concurrent=3,
        max_input_tokens=50_000,
        max_output_tokens=10_000,
        min_pass_rate=0.6,
        min_avg_score=0.5,
        enable_performance_test=False,
        enable_security_audit=False,
        enable_stress_test=False,
    ),
    
    QoSLevel.BASIC: QoSEvalConfig(
        level=QoSLevel.BASIC,
        suites=[
            "conversation/basic",
            "conversation/intent_understanding",
            "tools/basic_calls",       # 基础工具调用
            "format/output_structure", # 输出格式规范
        ],
        trials_per_task=2,
        timeout_seconds=45,
        max_concurrent=4,
        max_input_tokens=100_000,
        max_output_tokens=30_000,
        min_pass_rate=0.7,
        min_avg_score=0.6,
        enable_performance_test=False,
        enable_security_audit=False,
        enable_stress_test=False,
    ),
    
    QoSLevel.PRO: QoSEvalConfig(
        level=QoSLevel.PRO,
        suites=[
            "conversation/basic",
            "conversation/intent_understanding",
            "conversation/context_retention",  # 上下文保持
            "tools/basic_calls",
            "tools/complex_chains",            # 复杂工具链
            "reasoning/multi_step",            # 多步推理
            "format/output_structure",
            "coding/basic_code_generation",    # 基础代码生成
        ],
        trials_per_task=3,
        timeout_seconds=60,
        max_concurrent=5,
        max_input_tokens=150_000,
        max_output_tokens=50_000,
        min_pass_rate=0.8,
        min_avg_score=0.7,
        enable_performance_test=True,  # 启用性能测试
        enable_security_audit=False,
        enable_stress_test=False,
    ),
    
    QoSLevel.ENTERPRISE: QoSEvalConfig(
        level=QoSLevel.ENTERPRISE,
        suites=[
            "conversation/basic",
            "conversation/intent_understanding",
            "conversation/context_retention",
            "conversation/long_context",       # 长上下文
            "tools/basic_calls",
            "tools/complex_chains",
            "tools/error_recovery",            # 工具错误恢复
            "reasoning/multi_step",
            "reasoning/complex_analysis",      # 复杂分析
            "format/output_structure",
            # V11.0: 移除多智能体评估维度
            "security/input_validation",       # 输入验证
            "security/output_filtering",       # 输出过滤
        ],
        trials_per_task=5,             # 更多试验确保稳定性
        timeout_seconds=120,
        max_concurrent=10,
        max_input_tokens=200_000,
        max_output_tokens=100_000,
        min_pass_rate=0.9,
        min_avg_score=0.8,
        enable_performance_test=True,
        enable_security_audit=True,    # 启用安全审计
        enable_stress_test=True,       # 启用压力测试
    ),
}


def get_qos_eval_config(level: QoSLevel) -> QoSEvalConfig:
    """
    获取指定 QoS 等级的评估配置
    
    Args:
        level: QoS 等级
        
    Returns:
        QoSEvalConfig 配置
    """
    return QOS_EVAL_CONFIGS.get(level, QOS_EVAL_CONFIGS[QoSLevel.PRO])


def get_eval_suites_for_qos(level: QoSLevel) -> List[str]:
    """
    获取指定 QoS 等级需要运行的评估套件
    
    Args:
        level: QoS 等级
        
    Returns:
        评估套件列表
    """
    config = get_qos_eval_config(level)
    return config.suites


class QoSEvaluator:
    """
    QoS 评估器
    
    根据 QoS 等级运行相应的评估套件，生成评估报告
    """
    
    def __init__(self, qos_level: QoSLevel = QoSLevel.PRO):
        self.qos_level = qos_level
        self.config = get_qos_eval_config(qos_level)
        logger.info(
            f"✅ QoSEvaluator 初始化: level={qos_level.value}, "
            f"suites={len(self.config.suites)}, "
            f"trials={self.config.trials_per_task}"
        )
    
    def get_evaluation_plan(self) -> Dict:
        """
        获取评估计划
        
        Returns:
            评估计划字典
        """
        return {
            "qos_level": self.qos_level.value,
            "suites": self.config.suites,
            "trials_per_task": self.config.trials_per_task,
            "timeout_seconds": self.config.timeout_seconds,
            "max_concurrent": self.config.max_concurrent,
            "token_limits": {
                "max_input": self.config.max_input_tokens,
                "max_output": self.config.max_output_tokens
            },
            "thresholds": {
                "min_pass_rate": self.config.min_pass_rate,
                "min_avg_score": self.config.min_avg_score
            },
            "optional_tests": {
                "performance": self.config.enable_performance_test,
                "security": self.config.enable_security_audit,
                "stress": self.config.enable_stress_test
            }
        }
    
    def should_run_suite(self, suite_name: str) -> bool:
        """
        检查是否应该运行指定套件
        
        Args:
            suite_name: 套件名称
            
        Returns:
            是否应该运行
        """
        return suite_name in self.config.suites
    
    def validate_results(self, pass_rate: float, avg_score: float) -> Dict:
        """
        验证评估结果是否达标
        
        Args:
            pass_rate: 通过率
            avg_score: 平均分
            
        Returns:
            验证结果字典
        """
        pass_rate_ok = pass_rate >= self.config.min_pass_rate
        avg_score_ok = avg_score >= self.config.min_avg_score
        
        return {
            "passed": pass_rate_ok and avg_score_ok,
            "pass_rate": {
                "value": pass_rate,
                "threshold": self.config.min_pass_rate,
                "passed": pass_rate_ok
            },
            "avg_score": {
                "value": avg_score,
                "threshold": self.config.min_avg_score,
                "passed": avg_score_ok
            }
        }
