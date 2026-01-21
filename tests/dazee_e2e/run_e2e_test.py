#!/usr/bin/env python3
"""
Dazee E2E 测试运行入口

执行完整测试流程并生成验证报告
"""

import asyncio
import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import pytest

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

RUN_DAZEE_E2E = os.getenv("RUN_DAZEE_E2E", "false").lower() == "true"
if not RUN_DAZEE_E2E:
    pytest.skip("未启用 RUN_DAZEE_E2E，跳过 Dazee E2E 测试", allow_module_level=True)

from logger import get_logger
try:
    # 作为包内测试执行
    from .test_full_pipeline import run_pipeline
    from .validators import validate_pipeline_results
except ImportError:
    # 作为脚本直接运行
    from test_full_pipeline import run_pipeline
    from validators import validate_pipeline_results

logger = get_logger("dazee.e2e.runner")


class DazeeE2ETestRunner:
    """Dazee E2E 测试运行器"""
    
    def __init__(self, output_dir: Path = None):
        """
        初始化运行器
        
        Args:
            output_dir: 报告输出目录
        """
        self.output_dir = output_dir or (project_root / "logs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.start_time = None
        self.end_time = None
        self.results = None
        self.validation_results = None
        
        logger.info(f"[E2E Runner] 初始化，报告目录: {self.output_dir}")
    
    async def run(self) -> Dict[str, Any]:
        """
        运行完整测试
        
        Returns:
            测试结果和验证结果
        """
        self.start_time = datetime.now()
        logger.info("\n" + "=" * 80)
        logger.info("Dazee E2E 端到端验证测试")
        logger.info("=" * 80)
        logger.info(f"开始时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"报告输出: {self.output_dir}")
        logger.info("=" * 80 + "\n")
        
        try:
            # 步骤 1: 运行流程
            logger.info("【步骤 1/3】运行完整流程...")
            self.results = await run_pipeline()
            logger.info("✓ 流程执行完成\n")
            
            # 步骤 2: 验证结果
            logger.info("【步骤 2/3】验证结果...")
            self.validation_results = validate_pipeline_results(self.results)
            logger.info("✓ 验证完成\n")
            
            # 步骤 3: 生成报告
            logger.info("【步骤 3/3】生成报告...")
            self.end_time = datetime.now()  # 设置结束时间（在生成报告前）
            report_path = self._generate_report()
            logger.info(f"✓ 报告已生成: {report_path}\n")
            
            self._print_final_summary()
            
            return {
                "results": self.results,
                "validation": self.validation_results,
                "report_path": report_path
            }
            
        except Exception as e:
            logger.error(f"测试执行失败: {e}", exc_info=True)
            raise
    
    def _generate_report(self) -> Path:
        """
        生成 Markdown 报告
        
        Returns:
            报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"dazee_e2e_report_{timestamp}.md"
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._build_report_content())
        
        logger.info(f"报告已保存: {report_path}")
        return report_path
    
    def _build_report_content(self) -> str:
        """构建报告内容"""
        lines = []
        
        # 标题
        lines.append("# Dazee E2E 端到端验证报告\n")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"**测试用户**: {self.results['metadata']['user_name']} ({self.results['metadata']['role']})\n")
        lines.append(f"**测试周期**: {self.results['metadata']['test_period']['duration_days']} 天\n")
        lines.append("---\n\n")
        
        # 执行摘要
        lines.append("## 执行摘要\n")
        total_passed = sum(1 for r in self.validation_results.values() if r.passed)
        total_checkpoints = len(self.validation_results)
        overall_status = "✅ 通过" if total_passed == total_checkpoints else "⚠️ 部分失败"
        
        lines.append(f"**总体状态**: {overall_status}\n")
        lines.append(f"**通过检查点**: {total_passed}/{total_checkpoints}\n")
        lines.append(f"**总耗时**: {(self.end_time - self.start_time).total_seconds():.2f} 秒\n")
        lines.append(f"**LLM 调用次数**: {sum(self.results['stats']['llm_calls'].values())} 次\n")
        lines.append(f"**错误数量**: {len(self.results['stats']['errors'])}\n\n")
        
        # 验证结果详情
        lines.append("## 验证结果详情\n")
        
        for checkpoint_id, result in self.validation_results.items():
            status_icon = "✅" if result.passed else "❌"
            lines.append(f"### {status_icon} {result.checkpoint}\n")
            lines.append(f"**准确率**: {result.get_accuracy():.1f}%\n")
            lines.append(f"**得分**: {result.score:.1f}/{result.max_score}\n\n")
            
            # 检查项详情
            if result.details:
                lines.append("| 检查项 | 状态 | 预期 | 实际 |\n")
                lines.append("|--------|------|------|------|\n")
                for detail in result.details:
                    status = "✓" if detail["passed"] else "✗"
                    lines.append(f"| {detail['name']} | {status} | {detail['expected']} | {detail['actual']} |\n")
                lines.append("\n")
            
            # 错误信息
            if result.errors:
                lines.append("**错误信息**:\n")
                for error in result.errors:
                    lines.append(f"- {error}\n")
                lines.append("\n")
        
        # 流程执行详情
        lines.append("## 流程执行详情\n")
        
        lines.append(f"### 阶段 1: 碎片提取\n")
        lines.append(f"- **碎片数量**: {len(self.results['fragments'])} 个\n")
        lines.append(f"- **LLM 调用**: {self.results['stats']['llm_calls']['extraction']} 次\n")
        lines.append(f"- **耗时**: {self.results['stats']['execution_time'].get('stage1_extraction', 0):.2f} 秒\n\n")
        
        lines.append(f"### 阶段 2: 行为分析\n")
        if self.results['behavior_pattern']:
            bp = self.results['behavior_pattern']
            lines.append(f"- **推断角色**: {bp.inferred_role} (置信度: {bp.role_confidence:.0%})\n")
            lines.append(f"- **常规任务**: {len(bp.routine_tasks)} 个\n")
            lines.append(f"- **协作者**: {len(bp.collaborators)} 人\n")
        lines.append(f"- **LLM 调用**: {self.results['stats']['llm_calls']['analysis']} 次\n")
        lines.append(f"- **耗时**: {self.results['stats']['execution_time'].get('stage2_analysis', 0):.2f} 秒\n\n")
        
        lines.append(f"### 阶段 3: 计划管理\n")
        lines.append(f"- **识别计划**: {len(self.results['plans'])} 个\n")
        if self.results['plans']:
            lines.append("- **计划列表**:\n")
            for plan in self.results['plans']:
                lines.append(f"  - {plan.title} (优先级: {plan.priority}, 进度: {plan.progress:.0%})\n")
        lines.append(f"- **LLM 调用**: {self.results['stats']['llm_calls']['planning']} 次\n")
        lines.append(f"- **耗时**: {self.results['stats']['execution_time'].get('stage3_planning', 0):.2f} 秒\n\n")
        
        lines.append(f"### 阶段 4: 提醒调度\n")
        lines.append(f"- **创建提醒**: {len(self.results['reminders'])} 个\n")
        if self.results['reminders']:
            lines.append("- **提醒列表**:\n")
            for reminder in self.results['reminders']:
                lines.append(f"  - {reminder.message} @ {reminder.time.strftime('%m-%d %H:%M')}\n")
        lines.append(f"- **耗时**: {self.results['stats']['execution_time'].get('stage4_reminder', 0):.2f} 秒\n\n")
        
        lines.append(f"### 阶段 5: 汇报生成\n")
        lines.append(f"- **日报**: {len(self.results['reports']['daily'])} 篇\n")
        lines.append(f"- **周报**: {'已生成' if self.results['reports']['weekly'] else '未生成'}\n")
        lines.append(f"- **耗时**: {self.results['stats']['execution_time'].get('stage5_reporting', 0):.2f} 秒\n\n")
        
        # 汇报示例
        if self.results['reports']['weekly']:
            lines.append("## 汇报示例\n")
            lines.append("### 每周洞察\n")
            lines.append("```\n")
            lines.append(self.results['reports']['weekly'][:2000])  # 截取前2000字符
            if len(self.results['reports']['weekly']) > 2000:
                lines.append("\n... (内容过长，已截断)")
            lines.append("\n```\n\n")
        
        # LLM 调用统计
        lines.append("## LLM 调用统计\n")
        lines.append("| 阶段 | 调用次数 |\n")
        lines.append("|------|----------|\n")
        for stage, count in self.results['stats']['llm_calls'].items():
            lines.append(f"| {stage} | {count} |\n")
        lines.append(f"| **总计** | **{sum(self.results['stats']['llm_calls'].values())}** |\n\n")
        
        # 错误日志
        if self.results['stats']['errors']:
            lines.append("## 错误日志\n")
            for i, error in enumerate(self.results['stats']['errors'], 1):
                lines.append(f"{i}. {error}\n")
            lines.append("\n")
        
        # 审计信息
        lines.append("## 审计信息\n")
        lines.append(f"- **测试数据**: 真实 LLM 语义理解提取\n")
        lines.append(f"- **向量存储**: Tencent VectorDB\n")
        lines.append(f"- **LLM 模型**: Claude Haiku (fragment_extractor profile)\n")
        lines.append(f"- **开始时间**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"- **结束时间**: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"- **测试环境**: {sys.platform}\n")
        lines.append(f"- **Python 版本**: {sys.version.split()[0]}\n\n")
        
        lines.append("---\n")
        lines.append("*本报告由 Dazee E2E 测试自动生成*\n")
        
        return "".join(lines)
    
    def _print_final_summary(self):
        """打印最终摘要"""
        total_passed = sum(1 for r in self.validation_results.values() if r.passed)
        total_checkpoints = len(self.validation_results)
        
        logger.info("\n" + "=" * 80)
        logger.info("测试完成！")
        logger.info("=" * 80)
        
        if total_passed == total_checkpoints:
            logger.info("✅ 所有检查点通过！")
        else:
            logger.warning(f"⚠️  {total_checkpoints - total_passed} 个检查点失败")
        
        logger.info(f"通过率: {total_passed}/{total_checkpoints} ({total_passed/total_checkpoints*100:.1f}%)")
        logger.info(f"总耗时: {(self.end_time - self.start_time).total_seconds():.2f} 秒")
        logger.info(f"LLM 调用: {sum(self.results['stats']['llm_calls'].values())} 次")
        logger.info("=" * 80 + "\n")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="运行 Dazee E2E 端到端验证测试")
    parser.add_argument(
        "--output-dir",
        type=str,
        help="报告输出目录（默认: logs/）"
    )
    
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir) if args.output_dir else None
    runner = DazeeE2ETestRunner(output_dir=output_dir)
    
    try:
        results = await runner.run()
        
        # 检查是否所有检查点通过
        all_passed = all(r.passed for r in results["validation"].values())
        sys.exit(0 if all_passed else 1)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
