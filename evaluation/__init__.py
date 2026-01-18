"""
ZenFlux Agent 评估系统

基于 Anthropic 的 AI Agent 评估方法论设计。

参考：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

核心概念：
- Task（任务）：单个测试用例，包含输入和成功标准
- Trial（试验）：对同一Task的一次执行（因模型随机性需多次运行）
- Transcript（转录）：完整执行记录（LLM调用、工具调用、推理过程）
- Outcome（结果）：环境中的最终状态（ground truth）
- Grader（评分器）：评分逻辑，分为Code/Model/Human三层
- Evaluation Suite（评估套件）：一组相关Task，测试特定能力

三层评分器设计：
1. Code-based Graders - 快速、便宜、客观（优先使用）
2. Model-based Graders - 灵活、处理主观任务（补充使用）
3. Human Graders - 黄金标准（定期校准）

使用方式：
    from evaluation import EvaluationHarness, CodeBasedGraders
    
    # 初始化评估工具
    harness = EvaluationHarness()
    
    # 加载评估套件
    suite = harness.load_suite("conversation/intent_understanding.yaml")
    
    # 运行评估
    report = await harness.run_suite(suite)
    
    # 输出报告
    print(report.to_summary())
"""

__version__ = "0.1.0"

# 延迟导入，避免循环依赖
def __getattr__(name):
    if name in _LAZY_IMPORTS:
        return _LAZY_IMPORTS[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def _import_models():
    from evaluation.models import (
        Task,
        Trial,
        Transcript,
        Outcome,
        GradeResult,
        EvaluationSuite,
        EvaluationReport,
        TokenUsage,
        ToolCall,
        Message,
    )
    return {
        "Task": Task,
        "Trial": Trial,
        "Transcript": Transcript,
        "Outcome": Outcome,
        "GradeResult": GradeResult,
        "EvaluationSuite": EvaluationSuite,
        "EvaluationReport": EvaluationReport,
        "TokenUsage": TokenUsage,
        "ToolCall": ToolCall,
        "Message": Message,
    }

def _import_graders():
    from evaluation.graders.code_based import CodeBasedGraders
    from evaluation.graders.model_based import ModelBasedGraders
    from evaluation.graders.human import HumanGraders
    return {
        "CodeBasedGraders": CodeBasedGraders,
        "ModelBasedGraders": ModelBasedGraders,
        "HumanGraders": HumanGraders,
    }

def _import_harness():
    from evaluation.harness import EvaluationHarness
    return {"EvaluationHarness": EvaluationHarness}

def _import_qos():
    from evaluation.qos_config import (
        QoSEvalConfig,
        QoSEvaluator,
        get_qos_eval_config,
        get_eval_suites_for_qos,
    )
    return {
        "QoSEvalConfig": QoSEvalConfig,
        "QoSEvaluator": QoSEvaluator,
        "get_qos_eval_config": get_qos_eval_config,
        "get_eval_suites_for_qos": get_eval_suites_for_qos,
    }

_LAZY_IMPORTS = {
    # Models
    "Task": lambda: _import_models()["Task"],
    "Trial": lambda: _import_models()["Trial"],
    "Transcript": lambda: _import_models()["Transcript"],
    "Outcome": lambda: _import_models()["Outcome"],
    "GradeResult": lambda: _import_models()["GradeResult"],
    "EvaluationSuite": lambda: _import_models()["EvaluationSuite"],
    "EvaluationReport": lambda: _import_models()["EvaluationReport"],
    "TokenUsage": lambda: _import_models()["TokenUsage"],
    "ToolCall": lambda: _import_models()["ToolCall"],
    "Message": lambda: _import_models()["Message"],
    # Graders
    "CodeBasedGraders": lambda: _import_graders()["CodeBasedGraders"],
    "ModelBasedGraders": lambda: _import_graders()["ModelBasedGraders"],
    "HumanGraders": lambda: _import_graders()["HumanGraders"],
    # Harness
    "EvaluationHarness": lambda: _import_harness()["EvaluationHarness"],
    # QoS
    "QoSEvalConfig": lambda: _import_qos()["QoSEvalConfig"],
    "QoSEvaluator": lambda: _import_qos()["QoSEvaluator"],
    "get_qos_eval_config": lambda: _import_qos()["get_qos_eval_config"],
    "get_eval_suites_for_qos": lambda: _import_qos()["get_eval_suites_for_qos"],
}

__all__ = [
    # Models
    "Task",
    "Trial",
    "Transcript",
    "Outcome",
    "GradeResult",
    "EvaluationSuite",
    "EvaluationReport",
    "TokenUsage",
    "ToolCall",
    "Message",
    # Graders
    "CodeBasedGraders",
    "ModelBasedGraders",
    "HumanGraders",
    # Harness
    "EvaluationHarness",
    # QoS
    "QoSEvalConfig",
    "QoSEvaluator",
    "get_qos_eval_config",
    "get_eval_suites_for_qos",
]
