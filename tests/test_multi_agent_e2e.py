"""
Multi-Agent 端到端验证脚本

验证目标：
1. ChatService 正确路由到 MultiAgentOrchestrator
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
from services.chat_service import ChatService
from services.session_service import get_session_service
from core.multi_agent.config import MultiAgentConfig
from utils.message_utils import extract_text_from_message

logger = get_logger("test_multi_agent_e2e")


class E2EValidator:
    """端到端验证器"""
    
    def __init__(self):
        # 创建 Multi-Agent 配置
        self.ma_config = MultiAgentConfig.from_dict({
            "mode": "auto",
            "max_parallel_workers": 5,
            "execution_strategy": "auto",
            "auto_trigger_keywords": ["研究", "分析", "对比", "调研", "报告"],
            "auto_trigger_min_complexity": "complex",
            "workers": {
                "research": {"enabled": True, "max_instances": 3},
                "document": {"enabled": True, "max_instances": 2}
            }
        })
        
        # 创建 ChatService（注入 multi_agent_config）
        self.chat_service = ChatService(
            session_service=get_session_service(),
            multi_agent_config=self.ma_config
        )
        
        # 验证结果
        self.validation_results = {
            "route_decision": None,  # 路由决策
            "task_decomposition": None,  # 任务分解
            "worker_execution": None,  # Worker 执行
            "result_aggregation": None,  # 结果聚合
            "final_output": None,  # 最终输出
            "errors": []  # 错误列表
        }
    
    async def validate(self):
        """执行完整验证"""
        logger.info("=" * 60)
        logger.info("🧪 Multi-Agent 端到端验证")
        logger.info("=" * 60)
        
        # 测试 Query
        test_query = "研究 Top 5 云计算公司的 AI 战略，并生成分析报告"
        user_id = "test_user"
        
        logger.info(f"\n📋 测试 Query: {test_query}")
        logger.info(f"👤 用户 ID: {user_id}\n")
        
        try:
            # ==================== 阶段 1: 路由决策验证 ====================
            logger.info("【阶段 1】验证路由决策")
            await self._validate_route_decision(test_query)
            
            # ==================== 阶段 2: 完整流程验证 ====================
            logger.info("\n【阶段 2】执行完整流程")
            await self._validate_full_pipeline(test_query, user_id)
            
            # ==================== 阶段 3: 输出验证 ====================
            logger.info("\n【阶段 3】验证输出质量")
            self._validate_output_quality()
            
            # ==================== 生成验证报告 ====================
            self._generate_report()
            
        except Exception as e:
            logger.error(f"❌ 验证失败: {e}", exc_info=True)
            self.validation_results["errors"].append(str(e))
            self._generate_report()
            raise
    
    async def _validate_route_decision(self, query: str):
        """验证路由决策"""
        try:
            # 模拟意图分析
            complexity = "complex"  # 研究任务 → 复杂度 complex
            
            # 测试 should_use_multi_agent
            should_use_ma = self.ma_config.should_use_multi_agent(
                user_query=query,
                complexity=complexity
            )
            
            logger.info(f"   复杂度: {complexity}")
            logger.info(f"   Multi-Agent 模式: {self.ma_config.mode.value}")
            logger.info(f"   路由决策: {'MultiAgentOrchestrator' if should_use_ma else 'SimpleAgent'}")
            
            # 验证结果
            expected = True  # 期望使用 Multi-Agent
            if should_use_ma == expected:
                logger.info("   ✅ 路由决策正确")
                self.validation_results["route_decision"] = "passed"
            else:
                logger.error(f"   ❌ 路由决策错误: 期望 {expected}, 实际 {should_use_ma}")
                self.validation_results["route_decision"] = "failed"
                self.validation_results["errors"].append(
                    f"路由决策错误: 期望使用 Multi-Agent，但决策使用 SimpleAgent"
                )
        
        except Exception as e:
            logger.error(f"   ❌ 路由决策验证失败: {e}")
            self.validation_results["route_decision"] = "error"
            self.validation_results["errors"].append(f"路由决策验证错误: {str(e)}")
    
    async def _validate_full_pipeline(self, query: str, user_id: str):
        """验证完整流程"""
        try:
            # 收集事件
            events_collected = []
            phases_detected = set()
            subtasks_detected = []
            final_output_received = False
            
            # 流式调用
            logger.info("   开始流式执行...")
            event_stream = await self.chat_service.chat(
                message=query,
                user_id=user_id,
                stream=True
            )
            async for event in event_stream:
                event_type = event.get("type", "")
                events_collected.append(event_type)
                
                # 检测关键事件
                if event_type == "content_start":
                    block_type = event.get("data", {}).get("block_type")
                    if block_type == "thinking":
                        logger.info(f"   🧠 思考中...")
                
                elif event_type == "content_delta":
                    delta = event.get("data", {}).get("delta", "")
                    if "阶段:" in delta:
                        phase = delta.replace("阶段:", "").strip()
                        phases_detected.add(phase)
                        logger.info(f"   📍 检测到阶段: {phase}")
                    
                    # 检测子任务
                    if "##" in delta:
                        subtask_id = delta.split("##")[1].split("\n")[0].strip()
                        if subtask_id not in subtasks_detected:
                            subtasks_detected.append(subtask_id)
                            logger.info(f"   🔧 检测到子任务: {subtask_id}")
                
                elif event_type == "content_stop":
                    pass
                
                elif event_type == "session_end":
                    status = event.get("data", {}).get("status")
                    logger.info(f"   🏁 会话结束: {status}")
                    final_output_received = True
            
            # 验证流程完整性
            logger.info(f"\n   📊 流程统计:")
            logger.info(f"      事件总数: {len(events_collected)}")
            logger.info(f"      检测到的阶段: {phases_detected}")
            logger.info(f"      检测到的子任务: {len(subtasks_detected)} 个")
            
            # 验证是否使用了 Multi-Agent
            if phases_detected:
                logger.info("   ✅ 检测到 Multi-Agent 执行阶段")
                self.validation_results["task_decomposition"] = "passed"
            else:
                logger.warning("   ⚠️ 未检测到 Multi-Agent 执行阶段（可能使用了 SimpleAgent）")
                self.validation_results["task_decomposition"] = "warning"
            
            # 验证子任务数量
            if len(subtasks_detected) >= 2:
                logger.info(f"   ✅ 任务分解合理（{len(subtasks_detected)} 个子任务）")
                self.validation_results["worker_execution"] = "passed"
            elif len(subtasks_detected) > 0:
                logger.warning(f"   ⚠️ 子任务数量较少（{len(subtasks_detected)} 个）")
                self.validation_results["worker_execution"] = "warning"
            else:
                logger.error("   ❌ 未检测到子任务执行")
                self.validation_results["worker_execution"] = "failed"
            
            # 验证最终输出
            if final_output_received:
                logger.info("   ✅ 流程完整结束")
                self.validation_results["result_aggregation"] = "passed"
            else:
                logger.error("   ❌ 流程未正常结束")
                self.validation_results["result_aggregation"] = "failed"
        
        except Exception as e:
            logger.error(f"   ❌ 完整流程验证失败: {e}", exc_info=True)
            self.validation_results["errors"].append(f"完整流程验证错误: {str(e)}")
    
    def _validate_output_quality(self):
        """验证输出质量"""
        # TODO: 验证最终输出是否符合用户预期
        # 目前只能通过人工检查
        logger.info("   ℹ️ 输出质量需要人工检查")
        self.validation_results["final_output"] = "manual_check"
    
    def _generate_report(self):
        """生成验证报告"""
        logger.info("\n" + "=" * 60)
        logger.info("📋 验证报告")
        logger.info("=" * 60)
        
        # 计算通过率
        results = self.validation_results
        total_checks = 4  # 路由决策、任务分解、Worker 执行、结果聚合
        passed_checks = sum(1 for v in [
            results["route_decision"],
            results["task_decomposition"],
            results["worker_execution"],
            results["result_aggregation"]
        ] if v == "passed")
        
        logger.info(f"\n✅ 通过: {passed_checks}/{total_checks}")
        
        # 详细结果
        logger.info("\n详细结果:")
        logger.info(f"   路由决策: {results['route_decision'] or 'N/A'}")
        logger.info(f"   任务分解: {results['task_decomposition'] or 'N/A'}")
        logger.info(f"   Worker 执行: {results['worker_execution'] or 'N/A'}")
        logger.info(f"   结果聚合: {results['result_aggregation'] or 'N/A'}")
        logger.info(f"   最终输出: {results['final_output'] or 'N/A'}")
        
        # 错误信息
        if results["errors"]:
            logger.error(f"\n❌ 错误 ({len(results['errors'])}):")
            for i, error in enumerate(results["errors"], 1):
                logger.error(f"   {i}. {error}")
        
        # 总结
        if passed_checks == total_checks and not results["errors"]:
            logger.info("\n" + "=" * 60)
            logger.info("🎉 验证通过！Multi-Agent 系统运行正常")
            logger.info("=" * 60)
        elif passed_checks >= total_checks // 2:
            logger.warning("\n" + "=" * 60)
            logger.warning("⚠️ 部分验证通过，存在一些问题需要修复")
            logger.warning("=" * 60)
        else:
            logger.error("\n" + "=" * 60)
            logger.error("❌ 验证失败！需要修复关键问题")
            logger.error("=" * 60)


async def main():
    """主函数"""
    validator = E2EValidator()
    await validator.validate()


if __name__ == "__main__":
    asyncio.run(main())
