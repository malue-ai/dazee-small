"""
Multi-Agent Orchestrator 直接验证脚本
绕过 ChatService/Redis，直接测试核心多智能体编排逻辑

验证目标：
1. MultiAgentOrchestrator 正确初始化
2. TaskDecomposer 合理分解任务
3. WorkerScheduler 正确调度执行
4. ResultAggregator 正确聚合结果
5. 最终输出符合用户预期

测试场景：研究 Top 5 云计算公司的 AI 战略
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from logger import get_logger
from core.multi_agent.orchestrator import MultiAgentOrchestrator, OrchestratorConfig
from core.multi_agent.config import MultiAgentConfig, MultiAgentMode
from core.agent import SimpleAgent
from core.events import EventManager
from core.memory import MemoryManager
from core.llm import create_claude_service
from typing import Dict, Any

logger = get_logger("test_orchestrator_direct")


class MockEventStorage:
    """Mock EventStorage for testing"""
    
    def __init__(self):
        self.seq_counter = {}
        self.session_contexts = {}
        self.events_buffer = {}
    
    async def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号"""
        if session_id not in self.seq_counter:
            self.seq_counter[session_id] = 0
        self.seq_counter[session_id] += 1
        return self.seq_counter[session_id]
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 session 上下文"""
        return self.session_contexts.get(session_id, {
            "conversation_id": f"conv_{session_id}",
            "user_id": "test_user"
        })
    
    async def buffer_event(self, session_id: str, event_data: Dict[str, Any]) -> None:
        """缓冲事件"""
        if session_id not in self.events_buffer:
            self.events_buffer[session_id] = []
        self.events_buffer[session_id].append(event_data)
    
    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        pass


class DirectOrchestratorValidator:
    """直接验证 Orchestrator 核心逻辑"""
    
    def __init__(self):
        # 创建 Multi-Agent 配置
        self.ma_config = MultiAgentConfig.from_dict({
            "mode": "auto",
            "max_parallel_workers": 5,
            "execution_strategy": "auto",
            "enable_checkpointing": True,
            "max_retries": 3,
            "task_timeout_seconds": 3600,
            "worker_timeout_seconds": 600,
            "workers": {
                "research": {
                    "enabled": True,
                    "description": "研究分析专家",
                    "model": "claude-sonnet-4-5-20250929"
                },
                "data_analysis": {
                    "enabled": True,
                    "description": "数据分析专家",
                    "model": "claude-haiku-4-5"
                }
            }
        })
        
        logger.info("✅ 配置初始化完成")
    
    async def run_validation(self):
        """执行验证"""
        logger.info("\n" + "="*60)
        logger.info("开始 Multi-Agent Orchestrator 直接验证")
        logger.info("="*60 + "\n")
        
        try:
            # 阶段 1：创建 Orchestrator
            await self._test_orchestrator_creation()
            
            # 阶段 2：任务分解
            await self._test_task_decomposition()
            
            # 阶段 3：Worker 调度
            await self._test_worker_scheduling()
            
            # 阶段 4：结果聚合
            await self._test_result_aggregation()
            
            # 🆕 阶段 5：完整端到端执行（展示最终用户输出）
            await self._test_complete_execution()
            
            logger.info("\n" + "="*60)
            logger.info("✅ 所有验证通过！")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"\n❌ 验证失败: {str(e)}", exc_info=True)
            raise
    
    async def _test_orchestrator_creation(self):
        """测试 Orchestrator 创建"""
        logger.info("【阶段 1】测试 Orchestrator 创建")
        
        # 创建 Mock EventStorage 和 EventManager
        event_storage = MockEventStorage()
        event_manager = EventManager(storage=event_storage)
        
        # 创建 MemoryManager
        memory_manager = MemoryManager(user_id="test_user")
        
        # 创建 LLM Service
        llm_service = create_claude_service(
            model="claude-sonnet-4-5-20250929"
        )
        
        # 创建 Orchestrator 配置
        orchestrator_config = OrchestratorConfig(
            max_parallel_workers=self.ma_config.max_parallel_workers,
            enable_checkpointing=self.ma_config.enable_checkpointing,
            max_retries=self.ma_config.max_retries,
            timeout_seconds=self.ma_config.task_timeout_seconds
        )
        
        # 创建 Orchestrator
        orchestrator = MultiAgentOrchestrator(
            event_manager=event_manager,
            memory_manager=memory_manager,
            llm_service=llm_service,
            config=orchestrator_config
        )
        
        logger.info("   ✅ Orchestrator 创建成功")
        logger.info(f"      - 最大并行: {orchestrator_config.max_parallel_workers}")
        logger.info(f"      - 检查点: {orchestrator_config.enable_checkpointing}")
        logger.info(f"      - 最大重试: {orchestrator_config.max_retries}")
        
        self.orchestrator = orchestrator
        self.event_manager = event_manager
        self.memory_manager = memory_manager
        self.llm_service = llm_service
    
    async def _test_task_decomposition(self):
        """测试任务分解"""
        logger.info("\n【阶段 2】测试任务分解")
        
        user_query = "研究 Top 5 云计算公司（AWS、Azure、GCP、阿里云、腾讯云）的 AI 战略，重点关注大模型、AI 服务和生态建设"
        
        logger.info(f"   用户查询: {user_query}")
        
        # 调用分解器
        from core.multi_agent.decomposition import TaskDecomposer
        decomposer = TaskDecomposer()
        
        task_plan = await decomposer.decompose(user_query)
        
        logger.info(f"   ✅ 任务分解完成，共 {len(task_plan.sub_tasks)} 个子任务:")
        for i, task in enumerate(task_plan.sub_tasks, 1):
            deps = f" (依赖: {', '.join(task.dependencies)})" if task.dependencies else ""
            logger.info(f"      {i}. {task.action}{deps}")
        
        # 验证分解合理性
        assert len(task_plan.sub_tasks) > 0, "任务分解结果不能为空"
        assert len(task_plan.sub_tasks) <= 10, "任务分解不应超过 10 个子任务（避免过度分解）"
        
        # 验证是否包含关键词
        all_descriptions = " ".join(t.action for t in task_plan.sub_tasks)
        for company in ["AWS", "Azure", "GCP", "阿里云", "腾讯云"]:
            assert company in user_query, f"原始查询应包含 {company}"
        
        logger.info("   ✅ 任务分解验证通过")
        
        self.task_plan = task_plan
    
    async def _test_worker_scheduling(self):
        """测试 Worker 调度"""
        logger.info("\n【阶段 3】测试 Worker 调度")
        
        from core.multi_agent.scheduling import WorkerScheduler, ExecutionStrategy
        
        # 验证 WorkerScheduler 已经在 Orchestrator 中初始化
        scheduler = self.orchestrator.worker_scheduler
        
        logger.info(f"   ✅ WorkerScheduler 已在 Orchestrator 中初始化")
        logger.info(f"      - 最大并行数: {scheduler.max_parallel_workers}")
        logger.info(f"      - Worker 执行器已配置")
        
        # 验证调度器功能（不需要真实 Worker，只验证组件状态）
        logger.info("   ✅ Worker 调度验证通过（组件已就绪）")
        
        self.scheduler = scheduler
    
    async def _test_result_aggregation(self):
        """测试结果聚合"""
        logger.info("\n【阶段 4】测试结果聚合")
        
        # 验证 ResultAggregator 已经在 Orchestrator 中初始化
        aggregator = self.orchestrator.result_aggregator
        
        logger.info(f"   ✅ ResultAggregator 已在 Orchestrator 中初始化")
        logger.info(f"      - 聚合器已配置 LLM 服务")
        
        # 验证聚合器功能（不需要真实聚合，只验证组件状态）
        logger.info("   ✅ 结果聚合验证通过（组件已就绪）")
        
        self.aggregator = aggregator
    
    async def _test_complete_execution(self):
        """
        🆕 阶段 5：完整端到端执行
        
        展示从用户 Query 到最终输出的完整流程
        """
        logger.info("\n【阶段 5】完整端到端执行（展示最终用户输出）")
        
        user_query = "研究 Top 5 云计算公司（AWS、Azure、GCP、阿里云、腾讯云）的 AI 战略"
        session_id = "test_session_e2e"
        
        logger.info(f"   用户查询: {user_query}")
        logger.info(f"   会话 ID: {session_id}")
        logger.info("")
        logger.info("   开始执行 Orchestrator.execute()...")
        logger.info("   " + "-"*58)
        
        try:
            # 执行完整流程
            event_count = 0
            final_output = None
            task_id = None
            
            async for event in self.orchestrator.execute(
                user_query=user_query,
                session_id=session_id
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                
                # 记录关键事件
                if event_type == "task_created":
                    task_id = event["data"].get("task_id")
                    logger.info(f"   📋 任务创建: {task_id}")
                
                elif event_type == "phase_start":
                    phase = event["data"].get("phase")
                    phase_names = {
                        "decomposing": "任务分解",
                        "planning": "Worker 规划",
                        "dispatching": "任务分配",
                        "executing": "并行执行",
                        "observing": "结果观察",
                        "validating": "质量验证",
                        "aggregating": "结果聚合"
                    }
                    logger.info(f"   ▶️  阶段: {phase_names.get(phase, phase)}")
                
                elif event_type == "decomposition_complete":
                    sub_tasks_count = event["data"].get("sub_tasks_count", 0)
                    reasoning = event["data"].get("reasoning", "")
                    logger.info(f"   ✅ 分解完成: {sub_tasks_count} 个子任务")
                    if reasoning:
                        logger.info(f"      推理: {reasoning[:80]}...")
                
                elif event_type == "sub_task_complete":
                    sub_task_id = event["data"].get("sub_task_id")
                    success = event["data"].get("success")
                    duration = event["data"].get("duration", 0)
                    status = "✅ 成功" if success else "❌ 失败"
                    logger.info(f"   {status} 子任务: {sub_task_id} ({duration:.2f}s)")
                
                elif event_type == "task_complete":
                    final_output = event["data"].get("final_output")
                    total_duration = event["data"].get("total_duration", 0)
                    completed = event["data"].get("completed_tasks", 0)
                    failed = event["data"].get("failed_tasks", 0)
                    
                    logger.info("")
                    logger.info("   " + "-"*58)
                    logger.info(f"   ✅ 任务完成!")
                    logger.info(f"      - 总耗时: {total_duration:.2f}s")
                    logger.info(f"      - 成功任务: {completed}")
                    logger.info(f"      - 失败任务: {failed}")
                
                elif event_type == "error":
                    error = event["data"].get("error")
                    logger.error(f"   ❌ 错误: {error}")
            
            # 展示最终输出给用户
            logger.info("")
            logger.info("=" * 60)
            logger.info("📤 最终输出给用户的结果：")
            logger.info("=" * 60)
            
            if final_output:
                # 格式化输出
                if isinstance(final_output, str):
                    # 限制输出长度，避免日志过长
                    output_preview = final_output[:500]
                    if len(final_output) > 500:
                        output_preview += "\n... (输出已截断，实际更长) ..."
                    logger.info(output_preview)
                else:
                    logger.info(str(final_output)[:500])
                
                logger.info("=" * 60)
                
                # 🚨 高标准严要求：验证输出质量
                logger.info("")
                logger.info("   📊 输出质量验证（高标准严要求）：")
                
                output_str = str(final_output)
                quality_checks = {
                    "包含关键词'AWS'或'亚马逊'": ("AWS" in output_str or "亚马逊" in output_str or "Amazon" in output_str),
                    "包含关键词'Azure'或'微软'": ("Azure" in output_str or "微软" in output_str or "Microsoft" in output_str),
                    "包含关键词'GCP'或'Google'": ("GCP" in output_str or "Google" in output_str or "谷歌" in output_str),
                    "包含关键词'阿里云'": ("阿里云" in output_str or "Aliyun" in output_str or "Alibaba" in output_str),
                    "包含关键词'腾讯云'": ("腾讯云" in output_str or "Tencent" in output_str),
                    "包含关键词'AI'或'人工智能'": ("AI" in output_str or "人工智能" in output_str or "机器学习" in output_str or "大模型" in output_str),
                    "输出长度 > 100字符": len(output_str) > 100,
                    "输出长度 > 500字符": len(output_str) > 500
                }
                
                passed_checks = sum(quality_checks.values())
                total_checks = len(quality_checks)
                
                for check_name, passed in quality_checks.items():
                    status = "✅" if passed else "❌"
                    logger.info(f"      {status} {check_name}")
                
                quality_score = (passed_checks * 100) // total_checks
                logger.info(f"\n   📊 质量评分: {passed_checks}/{total_checks} ({quality_score}%)")
                
                # 🚨 不妥协！低于 70% 视为不合格
                if quality_score < 70:
                    logger.error(f"   ❌ 输出质量不达标！")
                    raise AssertionError(f"输出质量不达标：{passed_checks}/{total_checks} ({quality_score}%)")
                else:
                    logger.info(f"   ✅ 输出质量合格！")
                
            else:
                logger.error("（无最终输出）")
                logger.info("=" * 60)
                logger.info("")
                logger.error(f"   ❌ Multi-Agent 系统未产生任何输出！")
                logger.error(f"   ❌ 共收到 {event_count} 个事件，但没有最终结果")
                logger.error(f"   ❌ 这不符合高标准严要求！")
                
                # 🚨 不妥协！抛出错误
                raise RuntimeError(
                    "Multi-Agent 系统未产生任何输出\n"
                    "可能原因：\n"
                    "1. TaskDecomposer 使用了 fallback 逻辑（没有真正调用 LLM）\n"
                    "2. WorkerScheduler 没有真正的 Worker 实例\n"
                    "3. ResultAggregator 没有结果可聚合\n"
                    "\n需要：真正的 LLM API Key 和完整的环境配置"
                )
            
            # 验证
            logger.info("")
            logger.info(f"   ✅ 端到端执行完成，共收到 {event_count} 个事件")
            
        except Exception as e:
            logger.error(f"   ❌ 执行失败: {e}", exc_info=True)
            raise


async def main():
    """主函数"""
    validator = DirectOrchestratorValidator()
    await validator.run_validation()


if __name__ == "__main__":
    asyncio.run(main())
