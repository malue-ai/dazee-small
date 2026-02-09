"""
快速验证所有模块导入是否正常
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def verify_imports():
    """验证所有关键模块的导入"""
    errors = []
    
    print("🔍 验证评估系统模块导入...")
    print()
    
    # 1. 数据模型
    try:
        from evaluation.models import (
            Task, Trial, Transcript, Outcome, GradeResult,
            EvaluationSuite, EvaluationReport, GraderType
        )
        print("✅ evaluation.models - 数据模型导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.models: {e}")
        print(f"❌ evaluation.models: {e}")
    
    # 2. 评分器
    try:
        from evaluation.graders.code_based import CodeBasedGraders
        print("✅ evaluation.graders.code_based - Code-based Graders 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.graders.code_based: {e}")
        print(f"❌ evaluation.graders.code_based: {e}")
    
    try:
        from evaluation.graders.model_based import ModelBasedGraders
        print("✅ evaluation.graders.model_based - Model-based Graders 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.graders.model_based: {e}")
        print(f"❌ evaluation.graders.model_based: {e}")
    
    try:
        from evaluation.graders.human import HumanGraders
        print("✅ evaluation.graders.human - Human Graders 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.graders.human: {e}")
        print(f"❌ evaluation.graders.human: {e}")
    
    # 3. 评估引擎
    try:
        from evaluation.harness import EvaluationHarness
        print("✅ evaluation.harness - Evaluation Harness 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.harness: {e}")
        print(f"❌ evaluation.harness: {e}")
    
    # 4. 指标计算
    try:
        from evaluation.metrics import MetricsCalculator, format_metric_summary
        print("✅ evaluation.metrics - Metrics Calculator 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.metrics: {e}")
        print(f"❌ evaluation.metrics: {e}")
    
    # 5. 校准工作流
    try:
        from evaluation.calibration import CalibrationWorkflow
        print("✅ evaluation.calibration - Calibration Workflow 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.calibration: {e}")
        print(f"❌ evaluation.calibration: {e}")
    
    # 6. 看板
    try:
        from evaluation.dashboard import EvaluationDashboard
        print("✅ evaluation.dashboard - Dashboard 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.dashboard: {e}")
        print(f"❌ evaluation.dashboard: {e}")
    
    # 7. 告警
    try:
        from evaluation.alerts import AlertManager, AlertSeverity
        print("✅ evaluation.alerts - Alert Manager 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.alerts: {e}")
        print(f"❌ evaluation.alerts: {e}")
    
    # 8. CI/CD 集成
    try:
        from evaluation.ci_integration import CIEvaluationRunner
        print("✅ evaluation.ci_integration - CI Integration 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.ci_integration: {e}")
        print(f"❌ evaluation.ci_integration: {e}")
    
    # 9. QoS 配置
    try:
        from evaluation.qos_config import QOS_EVAL_CONFIGS, QoSLevel
        print("✅ evaluation.qos_config - QoS Config 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.qos_config: {e}")
        print(f"❌ evaluation.qos_config: {e}")
    
    # 10. 失败案例转换
    try:
        from evaluation.case_converter import FailureCaseConverter
        print("✅ evaluation.case_converter - Case Converter 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.case_converter: {e}")
        print(f"❌ evaluation.case_converter: {e}")
    
    # 11. 案例复审
    try:
        from evaluation.case_reviewer import CaseReviewer
        print("✅ evaluation.case_reviewer - Case Reviewer 导入成功")
    except Exception as e:
        errors.append(f"❌ evaluation.case_reviewer: {e}")
        print(f"❌ evaluation.case_reviewer: {e}")
    
    print()
    print("=" * 80)
    
    if errors:
        print(f"❌ 发现 {len(errors)} 个导入错误:")
        for error in errors:
            print(f"   {error}")
        return False
    else:
        print("✅ 所有模块导入成功！")
        return True

if __name__ == "__main__":
    success = verify_imports()
    sys.exit(0 if success else 1)
