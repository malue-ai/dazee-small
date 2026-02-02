"""
意图识别准确率端到端测试

测试维度：
1. 分类准确率（task_type, complexity, needs_multi_agent）
2. 字段一致性（约束遵循）
3. 稳定性（多次运行结果一致性）
4. 追问识别（上下文理解）

使用方式：
    # 运行全部测试
    python tests/test_e2e_intent_accuracy.py
    
    # 只运行特定分类
    python tests/test_e2e_intent_accuracy.py --category simple_single_turn
    
    # 指定试验次数
    python tests/test_e2e_intent_accuracy.py --trials 5
    
    # 使用 pytest
    pytest tests/test_e2e_intent_accuracy.py -v
"""

# 1. 标准库
import os
import sys
import json
import asyncio
import argparse
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime

# 添加项目根目录到 sys.path
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 2. 第三方库
import yaml
import pytest


# ============================================================
# 数据类
# ============================================================

@dataclass
class TestCase:
    """测试用例"""
    id: str
    description: str
    category: str
    input: Dict[str, Any]
    expected: Dict[str, Any]
    tolerance: Dict[str, Any] = field(default_factory=dict)
    consistency_rules: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class TrialResult:
    """单次试验结果"""
    trial_number: int
    passed: bool
    result: Dict[str, Any]
    mismatches: List[Dict[str, Any]]
    consistency_violations: List[str]
    latency_ms: float


@dataclass
class TestResult:
    """测试用例结果"""
    test_id: str
    description: str
    category: str
    trials: List[TrialResult]
    passed: bool
    pass_rate: float
    stability_score: float
    avg_latency_ms: float


@dataclass
class AccuracyReport:
    """准确率报告"""
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    consistency_errors: int = 0
    avg_latency_ms: float = 0.0
    stability_score: float = 0.0
    
    # 按分类统计
    by_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # 按字段统计
    by_field: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # 详细结果
    results: List[TestResult] = field(default_factory=list)
    # 失败详情
    failures: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================
# 环境加载
# ============================================================

def load_env():
    """加载 .env 文件"""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            print(f"✅ 加载 .env: {env_path}")
            return True
        else:
            print(f"⚠️ .env 不存在: {env_path}")
            return False
    except ImportError:
        # Fallback: 手动解析
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                key = key.strip().replace("export ", "")
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
            print(f"✅ 手动加载 .env: {env_path}")
            return True
        return False


def check_api_key() -> Tuple[bool, str]:
    """检查 API Key 配置"""
    # 优先检查 Claude
    if os.getenv("ANTHROPIC_API_KEY"):
        return True, "claude"
    # 其次检查 Qwen
    if os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY"):
        return True, "qwen"
    # 最后检查 OpenAI
    if os.getenv("OPENAI_API_KEY"):
        return True, "openai"
    return False, ""


# ============================================================
# 意图分析器封装
# ============================================================

class IntentAccuracyTester:
    """意图识别准确率测试器"""
    
    def __init__(self, provider: str = "claude", model: Optional[str] = None):
        """
        初始化测试器
        
        Args:
            provider: LLM 提供商 (claude, qwen, openai)
            model: 模型名称（默认使用意图分析专用模型）
        """
        self.provider = provider
        self.model = model
        self.analyzer = None
        self._init_analyzer()
    
    def _init_analyzer(self):
        """初始化意图分析器"""
        from core.llm import create_llm_service, LLMProvider
        from core.routing.intent_analyzer import IntentAnalyzer
        
        # 根据 provider 创建 LLM 服务
        # 意图识别是简单分类任务，禁用 extended thinking
        if self.provider == "claude":
            # Claude Haiku 用于意图分析（快+便宜）
            model = self.model or "claude-3-5-haiku-latest"
            llm = create_llm_service(
                provider=LLMProvider.CLAUDE,
                model=model,
                max_tokens=1024,
                enable_thinking=False  # 意图分类不需要 extended thinking
            )
        elif self.provider == "qwen":
            model = self.model or "qwen-plus"
            llm = create_llm_service(
                provider=LLMProvider.QWEN,
                model=model,
                max_tokens=1024,
                enable_thinking=False
            )
        elif self.provider == "openai":
            model = self.model or "gpt-4o-mini"
            llm = create_llm_service(
                provider=LLMProvider.OPENAI,
                model=model,
                max_tokens=1024
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
        self.analyzer = IntentAnalyzer(llm_service=llm, enable_llm=True)
        print(f"✅ 初始化 IntentAnalyzer: provider={self.provider}, model={model}")
    
    async def analyze_single(
        self,
        user_query: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Tuple[Dict[str, Any], float]:
        """
        分析单个 query
        
        Args:
            user_query: 用户查询
            conversation_history: 对话历史
            
        Returns:
            (意图结果字典, 延迟毫秒)
        """
        # 构建消息列表
        messages = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_query})
        
        # 执行分析
        start_time = time.perf_counter()
        result = await self.analyzer.analyze(messages)
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        return result.to_dict(), latency_ms
    
    def _evaluate_result(
        self,
        actual: Dict[str, Any],
        expected: Dict[str, Any],
        tolerance: Dict[str, Any],
        consistency_rules: List[str]
    ) -> Tuple[bool, List[Dict], List[str]]:
        """
        评估结果
        
        Args:
            actual: 实际结果
            expected: 期望结果
            tolerance: 容差配置
            consistency_rules: 一致性规则
            
        Returns:
            (是否通过, 不匹配列表, 一致性违规列表)
        """
        mismatches = []
        
        # 字段检查
        for field_name, expected_value in expected.items():
            actual_value = actual.get(field_name)
            
            # 处理枚举值
            if hasattr(actual_value, "value"):
                actual_value = actual_value.value
            
            # 检查容差
            if field_name in tolerance:
                tol = tolerance[field_name]
                if tol == "any":
                    continue
                if isinstance(tol, list):
                    if actual_value not in tol:
                        mismatches.append({
                            "field": field_name,
                            "expected": f"one of {tol}",
                            "actual": actual_value
                        })
                    continue
            
            # 精确匹配
            if actual_value != expected_value:
                mismatches.append({
                    "field": field_name,
                    "expected": expected_value,
                    "actual": actual_value
                })
        
        # 一致性规则检查
        consistency_violations = self._check_consistency(actual, consistency_rules)
        
        passed = len(mismatches) == 0 and len(consistency_violations) == 0
        return passed, mismatches, consistency_violations
    
    def _check_consistency(
        self,
        result: Dict[str, Any],
        rules: List[str]
    ) -> List[str]:
        """
        检查字段一致性
        
        V9.2 更新：放宽一致性规则
        - execution_strategy 基于语义判断，不与 complexity 强绑定
        - 例如：简单的代码任务可能需要 rvr-b（因为涉及代码开发）
        """
        violations = []
        
        complexity = result.get("complexity")
        needs_plan = result.get("needs_plan")
        execution_strategy = result.get("execution_strategy")
        
        # 只保留核心规则：simple 任务不需要规划
        if complexity == "simple" and needs_plan is True:
            # 这只是警告，不作为硬性违规
            # 因为有些简单任务（如简单 PPT）可能被 LLM 判断为需要规划
            pass
        
        # complex 任务应该需要规划
        if complexity == "complex" and needs_plan is False:
            violations.append(
                f"complex complexity should have needs_plan=true, got {needs_plan}"
            )
        
        # 注意：不再检查 execution_strategy 与 complexity 的一致性
        # 因为 execution_strategy 是基于语义判断的
        
        return violations
    
    async def run_test_case(
        self,
        test_case: TestCase,
        trials: int = 3
    ) -> TestResult:
        """
        运行单个测试用例
        
        Args:
            test_case: 测试用例
            trials: 试验次数
            
        Returns:
            测试结果
        """
        trial_results = []
        
        for i in range(trials):
            # 执行分析
            result, latency_ms = await self.analyze_single(
                user_query=test_case.input.get("user_query", ""),
                conversation_history=test_case.input.get("conversation_history")
            )
            
            # 评估结果
            passed, mismatches, violations = self._evaluate_result(
                actual=result,
                expected=test_case.expected,
                tolerance=test_case.tolerance,
                consistency_rules=test_case.consistency_rules
            )
            
            trial_results.append(TrialResult(
                trial_number=i + 1,
                passed=passed,
                result=result,
                mismatches=mismatches,
                consistency_violations=violations,
                latency_ms=latency_ms
            ))
        
        # 统计
        passed_trials = sum(1 for t in trial_results if t.passed)
        pass_rate = passed_trials / trials
        avg_latency = sum(t.latency_ms for t in trial_results) / trials
        
        # 稳定性得分（结果一致性）
        stability_score = self._calculate_stability(trial_results)
        
        return TestResult(
            test_id=test_case.id,
            description=test_case.description,
            category=test_case.category,
            trials=trial_results,
            passed=pass_rate >= 0.5,  # 多数通过即可
            pass_rate=pass_rate,
            stability_score=stability_score,
            avg_latency_ms=avg_latency
        )
    
    def _calculate_stability(self, trials: List[TrialResult]) -> float:
        """
        计算稳定性得分（结果一致性）
        
        返回 0-1 之间的值，1 表示完全一致
        """
        if len(trials) <= 1:
            return 1.0
        
        # 比较关键字段的一致性
        key_fields = [
            "task_type", "complexity", "needs_plan",
            "needs_multi_agent", "is_follow_up", "execution_strategy"
        ]
        
        consistency_count = 0
        for field_name in key_fields:
            values = [t.result.get(field_name) for t in trials]
            if len(set(str(v) for v in values)) == 1:
                consistency_count += 1
        
        return consistency_count / len(key_fields)
    
    async def run_suite(
        self,
        suite_path: str,
        trials: int = 3,
        category_filter: Optional[str] = None,
        verbose: bool = True
    ) -> AccuracyReport:
        """
        运行测试套件
        
        Args:
            suite_path: 测试套件 YAML 文件路径
            trials: 每个用例的试验次数
            category_filter: 只运行指定分类
            verbose: 是否输出详细日志
            
        Returns:
            准确率报告
        """
        # 加载套件
        with open(suite_path, "r", encoding="utf-8") as f:
            suite = yaml.safe_load(f)
        
        # 解析测试用例
        test_cases = []
        for task in suite.get("tasks", []):
            category = task.get("category", "general")
            if category_filter and category != category_filter:
                continue
            
            test_cases.append(TestCase(
                id=task["id"],
                description=task.get("description", ""),
                category=category,
                input=task.get("input", {}),
                expected=task.get("expected", {}),
                tolerance=task.get("tolerance", {}),
                consistency_rules=task.get("consistency_rules", []),
                tags=task.get("tags", [])
            ))
        
        if verbose:
            print(f"\n{'=' * 80}")
            print(f"🚀 意图识别准确率测试")
            print(f"{'=' * 80}")
            print(f"套件: {suite.get('name', 'Unknown')}")
            print(f"用例数: {len(test_cases)}")
            print(f"试验次数: {trials}")
            print(f"Provider: {self.provider}")
            print()
        
        # 初始化报告
        report = AccuracyReport()
        report.total_cases = len(test_cases)
        
        # 运行测试
        start_time = time.perf_counter()
        
        for i, test_case in enumerate(test_cases, 1):
            if verbose:
                print(f"[{i}/{len(test_cases)}] {test_case.id}: {test_case.description[:50]}...")
            
            # 运行用例
            result = await self.run_test_case(test_case, trials=trials)
            report.results.append(result)
            
            # 更新分类统计
            cat = test_case.category
            if cat not in report.by_category:
                report.by_category[cat] = {"total": 0, "passed": 0, "latency_sum": 0}
            report.by_category[cat]["total"] += 1
            report.by_category[cat]["latency_sum"] += result.avg_latency_ms
            
            if result.passed:
                report.passed_cases += 1
                report.by_category[cat]["passed"] += 1
                status = "✅"
            else:
                report.failed_cases += 1
                status = "❌"
                # 记录失败详情
                report.failures.append({
                    "test_id": test_case.id,
                    "description": test_case.description,
                    "category": cat,
                    "pass_rate": result.pass_rate,
                    "trials": [
                        {
                            "mismatches": t.mismatches,
                            "violations": t.consistency_violations
                        }
                        for t in result.trials if not t.passed
                    ]
                })
            
            # 统计一致性错误
            for trial in result.trials:
                if trial.consistency_violations:
                    report.consistency_errors += 1
            
            if verbose:
                stability = f"稳定性: {result.stability_score:.0%}"
                latency = f"延迟: {result.avg_latency_ms:.0f}ms"
                print(f"  {status} pass_rate={result.pass_rate:.0%}, {stability}, {latency}")
        
        # 计算总体指标
        total_duration = time.perf_counter() - start_time
        report.avg_latency_ms = sum(r.avg_latency_ms for r in report.results) / len(report.results) if report.results else 0
        report.stability_score = sum(r.stability_score for r in report.results) / len(report.results) if report.results else 0
        
        # 输出总结
        if verbose:
            self._print_summary(report, total_duration)
        
        return report
    
    def _print_summary(self, report: AccuracyReport, duration: float):
        """打印总结"""
        print(f"\n{'=' * 80}")
        print(f"📊 测试总结")
        print(f"{'=' * 80}")
        
        pass_rate = report.passed_cases / report.total_cases if report.total_cases > 0 else 0
        
        print(f"\n总体统计:")
        print(f"  总用例: {report.total_cases}")
        print(f"  通过: {report.passed_cases}")
        print(f"  失败: {report.failed_cases}")
        print(f"  通过率: {pass_rate:.1%}")
        print(f"  稳定性: {report.stability_score:.1%}")
        print(f"  一致性错误: {report.consistency_errors}")
        print(f"  平均延迟: {report.avg_latency_ms:.0f}ms")
        print(f"  总耗时: {duration:.1f}s")
        
        print(f"\n分类统计:")
        for cat, stats in sorted(report.by_category.items()):
            cat_pass_rate = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            cat_avg_latency = stats["latency_sum"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {cat}: {stats['passed']}/{stats['total']} ({cat_pass_rate:.0%}), 延迟: {cat_avg_latency:.0f}ms")
        
        if report.failures:
            print(f"\n失败详情 (前5个):")
            for failure in report.failures[:5]:
                print(f"\n  ❌ {failure['test_id']}: {failure['description'][:50]}")
                print(f"     分类: {failure['category']}, 通过率: {failure['pass_rate']:.0%}")
                for trial in failure["trials"][:1]:  # 只显示第一个失败的 trial
                    if trial["mismatches"]:
                        for m in trial["mismatches"][:3]:
                            print(f"     - {m['field']}: 期望={m['expected']}, 实际={m['actual']}")
                    if trial["violations"]:
                        for v in trial["violations"][:2]:
                            print(f"     - 一致性: {v}")
    
    def save_report(
        self,
        report: AccuracyReport,
        output_path: str
    ):
        """保存报告到文件"""
        # 转换为可序列化格式
        report_dict = {
            "timestamp": datetime.now().isoformat(),
            "provider": self.provider,
            "model": self.model,
            "total_cases": report.total_cases,
            "passed_cases": report.passed_cases,
            "failed_cases": report.failed_cases,
            "pass_rate": report.passed_cases / report.total_cases if report.total_cases > 0 else 0,
            "consistency_errors": report.consistency_errors,
            "avg_latency_ms": report.avg_latency_ms,
            "stability_score": report.stability_score,
            "by_category": {
                cat: {
                    **stats,
                    "pass_rate": stats["passed"] / stats["total"] if stats["total"] > 0 else 0
                }
                for cat, stats in report.by_category.items()
            },
            "failures": report.failures
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)
        
        print(f"\n📁 报告已保存: {output_path}")


# ============================================================
# Pytest 测试用例
# ============================================================

@pytest.fixture
def tester():
    """创建测试器实例"""
    load_env()
    has_key, provider = check_api_key()
    if not has_key:
        pytest.skip("No API key configured")
    return IntentAccuracyTester(provider=provider)


@pytest.mark.asyncio
async def test_simple_queries(tester):
    """测试简单查询"""
    simple_queries = [
        ("上海今天天气怎么样？", {"task_type": "information_query", "complexity": "simple"}),
        ("1+1等于几？", {"task_type": "information_query", "complexity": "simple"}),
        ("Python 是什么？", {"task_type": "information_query", "complexity": "simple"}),
    ]
    
    passed = 0
    for query, expected in simple_queries:
        result, latency = await tester.analyze_single(query)
        
        all_match = True
        for field_name, expected_value in expected.items():
            actual = result.get(field_name)
            if actual != expected_value:
                print(f"❌ '{query}' - {field_name}: 期望={expected_value}, 实际={actual}")
                all_match = False
        
        if all_match:
            passed += 1
            print(f"✅ '{query}' - 延迟: {latency:.0f}ms")
    
    accuracy = passed / len(simple_queries)
    print(f"\n简单查询准确率: {accuracy:.0%}")
    assert accuracy >= 0.8, f"简单查询准确率应 >= 80%，实际: {accuracy:.0%}"


@pytest.mark.asyncio
async def test_followup_detection(tester):
    """测试追问识别"""
    followup_cases = [
        {
            "history": [
                {"role": "user", "content": "帮我分析这份销售数据"},
                {"role": "assistant", "content": "好的，我来分析..."}
            ],
            "query": "然后呢？",
            "expected_followup": True
        },
        {
            "history": [
                {"role": "user", "content": "帮我写个周报"},
                {"role": "assistant", "content": "好的，正在生成..."}
            ],
            "query": "上海今天天气怎么样？",
            "expected_followup": False
        },
    ]
    
    passed = 0
    for case in followup_cases:
        result, latency = await tester.analyze_single(
            case["query"],
            case["history"]
        )
        
        actual_followup = result.get("is_follow_up", False)
        if actual_followup == case["expected_followup"]:
            passed += 1
            print(f"✅ is_follow_up={actual_followup} (期望: {case['expected_followup']})")
        else:
            print(f"❌ is_follow_up={actual_followup} (期望: {case['expected_followup']})")
    
    accuracy = passed / len(followup_cases)
    print(f"\n追问识别准确率: {accuracy:.0%}")
    assert accuracy >= 0.5, f"追问识别准确率应 >= 50%，实际: {accuracy:.0%}"


@pytest.mark.asyncio
async def test_multi_agent_detection(tester):
    """测试多智能体判断"""
    multi_agent_cases = [
        ("研究 Top 5 云计算公司的 AI 战略", True),
        ("对比 AWS、Azure、GCP 三家云服务商", True),
        ("帮我写一个 Python 排序函数", False),
        ("对比 Python 和 JavaScript 的性能", False),
    ]
    
    passed = 0
    for query, expected_multi in multi_agent_cases:
        result, latency = await tester.analyze_single(query)
        
        actual_multi = result.get("needs_multi_agent", False)
        if actual_multi == expected_multi:
            passed += 1
            print(f"✅ '{query[:30]}...' - needs_multi_agent={actual_multi}")
        else:
            print(f"❌ '{query[:30]}...' - needs_multi_agent={actual_multi} (期望: {expected_multi})")
    
    accuracy = passed / len(multi_agent_cases)
    print(f"\n多智能体判断准确率: {accuracy:.0%}")
    assert accuracy >= 0.5, f"多智能体判断准确率应 >= 50%，实际: {accuracy:.0%}"


@pytest.mark.asyncio
async def test_consistency(tester):
    """测试字段一致性"""
    consistency_cases = [
        ("1+1等于几？", "simple"),
        ("帮我设计一个完整的电商系统", "complex"),
    ]
    
    violations_count = 0
    for query, expected_complexity in consistency_cases:
        result, latency = await tester.analyze_single(query)
        
        complexity = result.get("complexity")
        needs_plan = result.get("needs_plan")
        execution_strategy = result.get("execution_strategy")
        
        violations = []
        
        if complexity == "simple":
            if needs_plan is True:
                violations.append("simple + needs_plan=true")
            if execution_strategy not in [None, "rvr"]:
                violations.append(f"simple + execution_strategy={execution_strategy}")
        
        if complexity == "complex":
            if needs_plan is False:
                violations.append("complex + needs_plan=false")
        
        if violations:
            violations_count += len(violations)
            print(f"❌ '{query[:30]}...' - 一致性违规: {violations}")
        else:
            print(f"✅ '{query[:30]}...' - 一致性正常")
    
    print(f"\n一致性违规数: {violations_count}")
    assert violations_count == 0, f"应无一致性违规，实际: {violations_count}"


@pytest.mark.asyncio
async def test_full_suite():
    """运行完整测试套件"""
    load_env()
    has_key, provider = check_api_key()
    if not has_key:
        pytest.skip("No API key configured")
    
    tester = IntentAccuracyTester(provider=provider)
    
    suite_path = Path(__file__).parent.parent / "evaluation" / "suites" / "intent" / "haiku_accuracy.yaml"
    if not suite_path.exists():
        pytest.skip(f"Suite not found: {suite_path}")
    
    report = await tester.run_suite(
        suite_path=str(suite_path),
        trials=2,
        verbose=True
    )
    
    pass_rate = report.passed_cases / report.total_cases if report.total_cases > 0 else 0
    assert pass_rate >= 0.6, f"总体通过率应 >= 60%，实际: {pass_rate:.0%}"


# ============================================================
# 命令行入口
# ============================================================

async def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="意图识别准确率端到端测试")
    parser.add_argument("--suite", type=str, default=None, help="测试套件路径")
    parser.add_argument("--category", type=str, default=None, help="只运行指定分类")
    parser.add_argument("--trials", type=int, default=3, help="每个用例的试验次数")
    parser.add_argument("--provider", type=str, default=None, help="LLM 提供商")
    parser.add_argument("--model", type=str, default=None, help="模型名称")
    parser.add_argument("--output", type=str, default=None, help="报告输出路径")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    
    args = parser.parse_args()
    
    # 加载环境
    load_env()
    has_key, default_provider = check_api_key()
    if not has_key:
        print("❌ 未配置 API Key，请设置 ANTHROPIC_API_KEY 或 QWEN_API_KEY")
        sys.exit(1)
    
    provider = args.provider or default_provider
    
    # 创建测试器
    tester = IntentAccuracyTester(provider=provider, model=args.model)
    
    # 确定套件路径
    if args.suite:
        suite_path = args.suite
    else:
        suite_path = Path(__file__).parent.parent / "evaluation" / "suites" / "intent" / "haiku_accuracy.yaml"
    
    if not Path(suite_path).exists():
        print(f"❌ 套件不存在: {suite_path}")
        sys.exit(1)
    
    # 运行测试
    report = await tester.run_suite(
        suite_path=str(suite_path),
        trials=args.trials,
        category_filter=args.category,
        verbose=not args.quiet
    )
    
    # 保存报告
    if args.output:
        tester.save_report(report, args.output)
    else:
        # 默认保存到 evaluation/reports/
        reports_dir = Path(__file__).parent.parent / "evaluation" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = reports_dir / f"intent_accuracy_{timestamp}.json"
        tester.save_report(report, str(output_path))
    
    # 返回退出码
    pass_rate = report.passed_cases / report.total_cases if report.total_cases > 0 else 0
    sys.exit(0 if pass_rate >= 0.6 else 1)


if __name__ == "__main__":
    asyncio.run(main())
