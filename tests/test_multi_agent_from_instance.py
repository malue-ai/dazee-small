"""
Multi-Agent 端到端验证（从实例化出发）

按照用户要求："端到端 从实例化出发"
- 使用 instance_loader.py 加载真实的 test_agent 实例
- 使用真实的配置（multi_agent.mode=auto）
- 验证完整的用户 Query → Multi-Agent → 最终输出流程

测试场景：研究 Top 5 云计算公司的 AI 战略
"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 🔧 关键修复：加载实例的环境变量（API Key 等）
from dotenv import load_dotenv
env_path = project_root / "instances" / "test_agent" / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量: {env_path}")
else:
    print(f"⚠️ 未找到环境变量文件: {env_path}")

from logger import get_logger
from scripts.instance_loader import create_agent_from_instance

logger = get_logger("test_multi_agent_from_instance")


class InstanceBasedE2EValidator:
    """从实例化出发的端到端验证器"""
    
    def __init__(self):
        self.agent = None
        self.instance_name = "test_agent"
    
    async def run_validation(self):
        """运行完整验证"""
        logger.info("=" * 60)
        logger.info("Multi-Agent 端到端验证（从实例化出发）")
        logger.info("=" * 60)
        logger.info("")
        
        try:
            # ==================== 阶段 1：加载实例 ====================
            await self._load_instance()
            
            # ==================== 阶段 2：验证配置 ====================
            await self._verify_config()
            
            # ==================== 阶段 3：执行用户 Query ====================
            await self._execute_user_query()
            
            logger.info("")
            logger.info("=" * 60)
            logger.info("✅ 所有验证通过！")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error("")
            logger.error("=" * 60)
            logger.error(f"❌ 验证失败: {e}")
            logger.error("=" * 60)
            raise
    
    async def _load_instance(self):
        """阶段 1：从 instances/test_agent/ 加载实例"""
        logger.info("【阶段 1】从 instances/test_agent/ 加载实例")
        logger.info("")
        
        try:
            # 使用 instance_loader.py 加载实例
            self.agent = await create_agent_from_instance(
                instance_name=self.instance_name,
                force_refresh=False  # 使用配置文件中的所有配置
            )
            
            logger.info(f"   ✅ 实例加载成功: {self.instance_name}")
            logger.info(f"      - Agent类型: {type(self.agent).__name__}")
            logger.info(f"      - 模型: {self.agent.model}")
            logger.info(f"      - Max Turns: {self.agent.max_turns}")
            
            # 验证 Schema 加载
            if hasattr(self.agent, 'schema') and self.agent.schema:
                logger.info(f"      - Schema: 已加载")
                
                # 检查 multi_agent 配置
                if hasattr(self.agent.schema, 'multi_agent'):
                    ma_config = self.agent.schema.multi_agent
                    logger.info(f"      - Multi-Agent 模式: {ma_config.mode.value if hasattr(ma_config, 'mode') else 'unknown'}")
                else:
                    logger.warning(f"      - Multi-Agent 配置: 未找到")
            
        except Exception as e:
            logger.error(f"   ❌ 实例加载失败: {e}", exc_info=True)
            raise RuntimeError(f"无法加载实例 {self.instance_name}: {e}")
    
    async def _verify_config(self):
        """阶段 2：验证 multi_agent 配置"""
        logger.info("")
        logger.info("【阶段 2】验证 multi_agent 配置")
        logger.info("")
        
        # 检查 Agent Schema
        if not hasattr(self.agent, 'schema') or not self.agent.schema:
            logger.error("   ❌ Agent Schema 未加载")
            raise RuntimeError("Agent Schema 未加载，无法验证 multi_agent 配置")
        
        # 检查 multi_agent 配置
        if not hasattr(self.agent.schema, 'multi_agent'):
            logger.error("   ❌ multi_agent 配置未加载")
            raise RuntimeError("multi_agent 配置未找到（检查 config.yaml）")
        
        ma_config = self.agent.schema.multi_agent
        
        logger.info(f"   ✅ multi_agent 配置已加载:")
        logger.info(f"      - mode: {ma_config.mode.value if hasattr(ma_config, 'mode') else 'unknown'}")
        logger.info(f"      - max_parallel_workers: {ma_config.max_parallel_workers}")
        logger.info(f"      - execution_strategy: {ma_config.execution_strategy.value if hasattr(ma_config.execution_strategy, 'value') else ma_config.execution_strategy}")
        logger.info(f"      - enable_checkpointing: {ma_config.enable_checkpointing}")
        logger.info(f"      - max_retries: {ma_config.max_retries}")
        
        # 检查 Workers 配置
        if hasattr(ma_config, 'workers') and ma_config.workers:
            logger.info(f"      - Workers 配置: {len(ma_config.workers)} 个")
            for worker_name, worker_config in ma_config.workers.items():
                # worker_config 可能是 dict 或 WorkerConfig 对象
                if isinstance(worker_config, dict):
                    enabled = worker_config.get('enabled', False)
                else:
                    enabled = getattr(worker_config, 'enabled', False)
                status = "✅ 启用" if enabled else "❌ 禁用"
                logger.info(f"        • {worker_name}: {status}")
        else:
            logger.warning(f"      - Workers 配置: 未找到")
        
        # 🆕 V6.0: 不再使用硬编码关键词，改用 LLM Few-shot 判断
        logger.info(f"      - 触发逻辑: Prompt-First（LLM 意图分析）")
    
    async def _execute_user_query(self):
        """阶段 3：执行用户 Query（验证 Multi-Agent 流程）"""
        logger.info("")
        logger.info("【阶段 3】执行用户 Query（高标准严要求）")
        logger.info("")
        
        # 🚨 高标准严要求：选择一个会触发 multi_agent 的 query
        user_query = "研究 Top 5 云计算公司（AWS、Azure、GCP、阿里云、腾讯云）的 AI 战略，生成对比分析报告"
        session_id = "test_session_from_instance"
        
        logger.info(f"   用户查询: {user_query}")
        logger.info(f"   会话 ID: {session_id}")
        logger.info("")
        
        # 🆕 V6.0: 验证意图分析（Prompt-First 原则）
        logger.info("   🔍 验证意图分析（Prompt-First）...")
        if hasattr(self.agent, 'intent_analyzer') and self.agent.intent_analyzer:
            try:
                intent_result = await self.agent.intent_analyzer.analyze(user_query)
                logger.info(f"      ✅ 意图分析完成:")
                logger.info(f"         - task_type: {intent_result.task_type.value}")
                logger.info(f"         - complexity: {intent_result.complexity.value}")
                logger.info(f"         - needs_plan: {intent_result.needs_plan}")
                logger.info(f"         - needs_multi_agent: {intent_result.needs_multi_agent}")
                logger.info(f"         - skip_memory: {intent_result.skip_memory_retrieval}")
                
                # 🚨 关键验证：Query 应该触发 Multi-Agent
                if not intent_result.needs_multi_agent:
                    logger.warning(f"      ⚠️ 警告：意图分析认为不需要 Multi-Agent，但此 Query 设计上应该触发！")
                else:
                    logger.info(f"      ✅ 意图分析正确识别需要 Multi-Agent")
            except Exception as e:
                logger.error(f"      ❌ 意图分析失败: {e}")
        
        logger.info("")
        logger.info("   开始执行 Agent.chat()...")
        logger.info("   " + "-" * 58)
        logger.info("")
        
        event_count = 0
        final_output = []
        error_occurred = False
        error_message = None
        
        multi_agent_triggered = False
        
        try:
            # 流式执行 Agent
            async for event in self.agent.chat(
                messages=[{"role": "user", "content": user_query}],
                session_id=session_id
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                data = event.get("data", {})
                
                # 记录关键事件
                if event_type == "message_start":
                    logger.info(f"   📨 消息开始")
                
                elif event_type == "content_delta":
                    # 累积最终输出
                    delta = data.get("delta", "")
                    if isinstance(delta, str):
                        final_output.append(delta)
                    elif isinstance(delta, dict):
                        text = delta.get("text", "")
                        if text:
                            final_output.append(text)
                
                elif event_type == "message_stop":
                    logger.info(f"   ✅ 消息结束")
                
                elif event_type == "error":
                    error = data.get("error", {})
                    error_message = error.get("message", "未知错误")
                    logger.error(f"   ❌ 错误: {error_message}")
                    error_occurred = True
                
                # 🔍 检测是否触发了 Multi-Agent
                elif "multi_agent" in event_type or "orchestrator" in event_type:
                    multi_agent_triggered = True
                    logger.info(f"   🔧 Multi-Agent 事件: {event_type}")
                
                elif event_type == "phase_start":
                    phase = data.get("phase")
                    logger.info(f"   ▶️  阶段: {phase}")
                    multi_agent_triggered = True
                
                elif event_type == "decomposition_complete":
                    sub_tasks_count = data.get("sub_tasks_count", 0)
                    logger.info(f"   ✅ 任务分解: {sub_tasks_count} 个子任务")
                    multi_agent_triggered = True
            
            # 展示最终输出
            logger.info("")
            logger.info("=" * 60)
            logger.info("📤 最终输出给用户的结果：")
            logger.info("=" * 60)
            
            final_output_str = "".join(final_output).strip()
            
            if final_output_str:
                # 限制输出长度
                output_preview = final_output_str[:500]
                if len(final_output_str) > 500:
                    output_preview += "\n... (输出已截断，实际更长) ..."
                logger.info(output_preview)
                
                logger.info("=" * 60)
                
                # 🚨 高标准严要求：验证输出质量
                logger.info("")
                logger.info("   📊 输出质量验证（高标准严要求）：")
                
                quality_checks = {
                    "包含关键词'AWS'或'亚马逊'": ("AWS" in final_output_str or "亚马逊" in final_output_str or "Amazon" in final_output_str),
                    "包含关键词'Azure'或'微软'": ("Azure" in final_output_str or "微软" in final_output_str or "Microsoft" in final_output_str),
                    "包含关键词'GCP'或'Google'": ("GCP" in final_output_str or "Google" in final_output_str or "谷歌" in final_output_str),
                    "包含关键词'阿里云'": ("阿里云" in final_output_str or "Aliyun" in final_output_str or "Alibaba" in final_output_str),
                    "包含关键词'腾讯云'": ("腾讯云" in final_output_str or "Tencent" in final_output_str),
                    "包含关键词'AI'或'人工智能'": ("AI" in final_output_str or "人工智能" in final_output_str or "机器学习" in final_output_str or "大模型" in final_output_str),
                    "输出长度 > 100字符": len(final_output_str) > 100,
                    "输出长度 > 500字符": len(final_output_str) > 500
                }
                
                passed_checks = sum(quality_checks.values())
                total_checks = len(quality_checks)
                
                for check_name, passed in quality_checks.items():
                    status = "✅" if passed else "❌"
                    logger.info(f"      {status} {check_name}")
                
                quality_score = (passed_checks * 100) // total_checks
                logger.info(f"\n   📊 质量评分: {passed_checks}/{total_checks} ({quality_score}%)")
                
                # 检查是否触发了 Multi-Agent
                logger.info("")
                if multi_agent_triggered:
                    logger.info(f"   ✅ Multi-Agent 已触发（符合预期）")
                else:
                    logger.warning(f"   ⚠️  Multi-Agent 未触发（可能使用了 SimpleAgent）")
                    logger.warning(f"       可能原因：")
                    logger.warning(f"       1. mode=disabled（强制禁用）")
                    logger.warning(f"       2. mode=auto 但 LLM 意图分析认为不需要 Multi-Agent")
                    logger.warning(f"       3. ChatService 路由逻辑未正确使用 intent.needs_multi_agent")
                    logger.warning(f"       4. 意图识别提示词的 Few-shot 示例需要调整")
                
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
                logger.error(f"   ❌ Agent 未产生任何输出！")
                logger.error(f"   ❌ 共收到 {event_count} 个事件，但没有最终结果")
                logger.error(f"   ❌ 这不符合高标准严要求！")
                
                # 🚨 不妥协！抛出错误
                if error_occurred:
                    raise RuntimeError(f"Agent 执行失败: {error_message}")
                else:
                    raise RuntimeError(
                        "Agent 未产生任何输出\n"
                        "可能原因：\n"
                        "1. LLM API Key 未配置或无效\n"
                        "2. SimpleAgent/MultiAgentOrchestrator 内部错误\n"
                        "3. 事件流异常中断\n"
                        "\n请检查环境配置和日志"
                    )
            
            # 验证
            logger.info("")
            logger.info(f"   ✅ 端到端执行完成，共收到 {event_count} 个事件")
            
        except Exception as e:
            logger.error(f"   ❌ 执行失败: {e}", exc_info=True)
            raise


async def main():
    """主函数"""
    validator = InstanceBasedE2EValidator()
    await validator.run_validation()


if __name__ == "__main__":
    asyncio.run(main())
