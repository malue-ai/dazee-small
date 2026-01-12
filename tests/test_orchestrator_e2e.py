"""
Multi-Agent Orchestrator 端到端验证（直接入口）

验证策略：
- 直接实例化 MultiAgentOrchestrator（跳过 ChatService/Session/Redis）
- 从 instance 加载真实的 workers_config
- 验证完整的任务分解 → 并行调度 → 结果聚合流程
- 验证最终输出质量（不妥协）

优点：
- 无外部依赖（Redis）
- 专注验证 Multi-Agent 核心逻辑
- 快速反馈
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
from dotenv import load_dotenv
env_path = project_root / "instances" / "test_agent" / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量: {env_path}")
else:
    print(f"⚠️ 未找到环境变量文件: {env_path}")

from logger import get_logger
from scripts.instance_loader import load_workers_config
from core.multi_agent import MultiAgentOrchestrator
from core.events import EventManager
from core.memory import create_memory_manager
from core.llm import create_llm_service
from typing import Dict, Any

logger = get_logger("test_orchestrator_e2e")


class MockEventStorage:
    """内存版 EventStorage（用于测试，不依赖 Redis）"""
    
    def __init__(self):
        self.session_seqs: Dict[str, int] = {}
        self.session_contexts: Dict[str, Dict[str, Any]] = {}
        self.events_buffer: Dict[str, list] = {}
    
    async def generate_session_seq(self, session_id: str) -> int:
        """生成 session 内的事件序号"""
        if session_id not in self.session_seqs:
            self.session_seqs[session_id] = 0
        self.session_seqs[session_id] += 1
        return self.session_seqs[session_id]
    
    async def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """获取 session 上下文"""
        return self.session_contexts.get(session_id, {
            "conversation_id": "mock_conversation_id",
            "user_id": "mock_user_id"
        })
    
    async def buffer_event(self, session_id: str, event_data: Dict[str, Any]) -> None:
        """缓冲事件"""
        if session_id not in self.events_buffer:
            self.events_buffer[session_id] = []
        self.events_buffer[session_id].append(event_data)
    
    async def update_heartbeat(self, session_id: str) -> None:
        """更新心跳"""
        pass  # Mock 实现，无需实际操作


class OrchestratorE2EValidator:
    """Orchestrator 端到端验证器（直接入口）"""
    
    def __init__(self):
        self.instance_name = "test_agent"
        self.orchestrator = None
        self.workers_config = None
    
    async def run_validation(self):
        """运行完整验证"""
        logger.info("=" * 80)
        logger.info("Multi-Agent Orchestrator 端到端验证（直接入口，不依赖 Redis）")
        logger.info("=" * 80)
        logger.info("")
        
        try:
            # ==================== 阶段 1：加载配置 ====================
            await self._load_config()
            
            # ==================== 阶段 2：初始化 Orchestrator ====================
            await self._init_orchestrator()
            
            # ==================== 阶段 3：执行用户 Query ====================
            await self._execute_user_query()
            
            logger.info("")
            logger.info("=" * 80)
            logger.info("✅ 所有验证通过！Multi-Agent 核心逻辑正常工作")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error("")
            logger.error("=" * 80)
            logger.error(f"❌ 验证失败: {e}")
            logger.error("=" * 80)
            raise
    
    async def _load_config(self):
        """阶段 1：加载 Workers 配置"""
        logger.info("【阶段 1】加载 Workers 配置")
        logger.info("")
        
        try:
            # 使用 instance_loader 加载 Workers 配置
            self.workers_config = load_workers_config(self.instance_name)
            
            if not self.workers_config:
                logger.warning("   ⚠️ 未找到 Workers 配置，将使用默认配置")
                self.workers_config = []
            else:
                logger.info(f"   ✅ Workers 配置加载成功: {len(self.workers_config)} 个")
                
                for worker_cfg in self.workers_config:
                    enabled = getattr(worker_cfg, 'enabled', False)
                    status = "✅ 启用" if enabled else "❌ 禁用"
                    logger.info(f"      • {worker_cfg.name} ({worker_cfg.specialization}): {status}")
                    
                    # 检查系统提示词是否已加载
                    if enabled and hasattr(worker_cfg, 'system_prompt') and worker_cfg.system_prompt:
                        prompt_preview = worker_cfg.system_prompt[:100].replace('\n', ' ')
                        logger.info(f"        提示词预览: {prompt_preview}...")
        
        except Exception as e:
            logger.error(f"   ❌ 加载配置失败: {e}", exc_info=True)
            raise RuntimeError(f"无法加载 Workers 配置: {e}")
    
    async def _init_orchestrator(self):
        """阶段 2：初始化 MultiAgentOrchestrator"""
        logger.info("")
        logger.info("【阶段 2】初始化 MultiAgentOrchestrator")
        logger.info("")
        
        try:
            # 创建必要的组件
            mock_storage = MockEventStorage()
            event_manager = EventManager(storage=mock_storage)
            memory_manager = create_memory_manager()
            llm_service = create_llm_service(
                provider="claude",  # 修复：使用正确的 LLMProvider 枚举值
                model="claude-sonnet-4-5-20250929"
            )
            
            # 创建 Orchestrator（传入 Workers 配置）
            self.orchestrator = MultiAgentOrchestrator(
                event_manager=event_manager,
                memory_manager=memory_manager,
                llm_service=llm_service,
                config=None,  # 使用默认配置
                prompt_cache=None,
                workers_config=self.workers_config  # 🆕 传入预加载的 Workers 配置
            )
            
            logger.info("   ✅ MultiAgentOrchestrator 初始化完成")
            logger.info("      - FSM Engine: 已就绪")
            logger.info("      - TaskDecomposer: 已就绪")
            logger.info("      - WorkerScheduler: 已就绪")
            logger.info("      - ResultAggregator: 已就绪")
            logger.info(f"      - Workers Config: {len(self.workers_config)} 个")
        
        except Exception as e:
            logger.error(f"   ❌ 初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"无法初始化 Orchestrator: {e}")
    
    async def _execute_user_query(self):
        """阶段 3：执行用户 Query（验证完整流程）"""
        logger.info("")
        logger.info("【阶段 3】执行用户 Query（高标准严要求）")
        logger.info("")
        
        # 测试 Query：应该触发 Multi-Agent（多个独立研究任务）
        user_query = "研究 Top 5 云计算公司（AWS、Azure、GCP、阿里云、腾讯云）的 AI 战略，生成对比分析报告"
        session_id = "test_orchestrator_e2e_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        
        logger.info(f"   用户查询: {user_query}")
        logger.info(f"   会话 ID: {session_id}")
        logger.info("")
        logger.info("   开始执行 Orchestrator.execute()...")
        logger.info("   " + "-" * 78)
        logger.info("")
        
        event_count = 0
        final_output = []
        error_occurred = False
        error_message = None
        
        # 关键阶段标志
        task_created = False
        decomposition_complete = False
        execution_started = False
        aggregation_complete = False
        
        sub_tasks_count = 0
        
        try:
            # 流式执行 Orchestrator
            async for event in self.orchestrator.execute(
                user_query=user_query,
                session_id=session_id,
                context={}
            ):
                event_count += 1
                event_type = event.get("type", "unknown")
                data = event.get("data", {})
                
                # 记录关键事件
                if event_type == "task_created":
                    task_created = True
                    task_id = data.get("task_id", "N/A")
                    logger.info(f"   📋 任务创建: {task_id}")
                
                elif event_type == "phase_start":
                    phase = data.get("phase", "unknown")
                    logger.info(f"   ▶️  阶段开始: {phase}")
                    
                    if phase == "decomposition":
                        pass  # 任务分解阶段
                    elif phase == "execution":
                        execution_started = True
                    elif phase == "aggregation":
                        pass  # 结果聚合阶段
                
                elif event_type == "decomposition_complete":
                    decomposition_complete = True
                    sub_tasks_count = data.get("sub_tasks_count", 0)
                    logger.info(f"   ✅ 任务分解完成: {sub_tasks_count} 个子任务")
                    
                    # 显示子任务列表
                    sub_tasks = data.get("sub_tasks", [])
                    if sub_tasks:
                        for i, sub_task in enumerate(sub_tasks, 1):
                            if isinstance(sub_task, dict):
                                action = sub_task.get("action", "N/A")
                                specialization = sub_task.get("specialization", "N/A")
                            else:
                                action = getattr(sub_task, 'action', 'N/A')
                                specialization = getattr(sub_task, 'specialization', 'N/A')
                            logger.info(f"      {i}. {action} [{specialization}]")
                
                elif event_type == "sub_task_start":
                    sub_task_id = data.get("sub_task_id", "N/A")
                    action = data.get("action", "N/A")
                    logger.info(f"   🔧 子任务开始: {sub_task_id} - {action}")
                
                elif event_type == "sub_task_complete":
                    sub_task_id = data.get("sub_task_id", "N/A")
                    logger.info(f"   ✅ 子任务完成: {sub_task_id}")
                
                elif event_type == "aggregation_complete":
                    aggregation_complete = True
                    logger.info(f"   ✅ 结果聚合完成")
                    
                    # 提取最终输出
                    final_result = data.get("final_output", "")
                    if isinstance(final_result, str):
                        final_output.append(final_result)
                    elif isinstance(final_result, dict):
                        # 可能是结构化输出
                        output_text = final_result.get("text", "") or final_result.get("output", "")
                        if output_text:
                            final_output.append(output_text)
                
                elif event_type == "content_delta":
                    # 累积输出
                    delta = data.get("delta", "")
                    if isinstance(delta, str):
                        final_output.append(delta)
                    elif isinstance(delta, dict):
                        text = delta.get("text", "")
                        if text:
                            final_output.append(text)
                
                elif event_type == "error":
                    error = data.get("error", {})
                    error_message = error.get("message", "未知错误")
                    logger.error(f"   ❌ 错误: {error_message}")
                    error_occurred = True
            
            # ==================== 验证结果 ====================
            logger.info("")
            logger.info("=" * 80)
            logger.info("📊 执行结果验证")
            logger.info("=" * 80)
            logger.info("")
            
            # 1. 验证关键阶段是否都执行了
            logger.info("   1️⃣ 关键阶段验证:")
            checks = {
                "任务创建": task_created,
                "任务分解": decomposition_complete,
                "任务执行": execution_started,
                "结果聚合": aggregation_complete,
            }
            
            all_phases_passed = True
            for phase_name, passed in checks.items():
                status = "✅" if passed else "❌"
                logger.info(f"      {status} {phase_name}")
                if not passed:
                    all_phases_passed = False
            
            if not all_phases_passed:
                raise AssertionError("关键阶段未全部执行，Multi-Agent 流程不完整")
            
            # 2. 验证子任务数量
            logger.info("")
            logger.info("   2️⃣ 子任务验证:")
            logger.info(f"      - 子任务数量: {sub_tasks_count}")
            
            if sub_tasks_count == 0:
                logger.warning("      ⚠️ 未产生任何子任务（可能任务未被分解）")
            elif sub_tasks_count >= 3:
                logger.info(f"      ✅ 子任务数量合理（>= 3，适合并行）")
            else:
                logger.info(f"      ⚠️ 子任务数量较少（< 3，并行效果有限）")
            
            # 3. 验证最终输出
            logger.info("")
            logger.info("   3️⃣ 最终输出验证:")
            
            final_output_str = "".join(final_output).strip()
            
            if not final_output_str:
                logger.error("      ❌ 无最终输出")
                logger.error(f"      ❌ 共收到 {event_count} 个事件，但没有生成输出")
                
                if error_occurred:
                    raise RuntimeError(f"Orchestrator 执行失败: {error_message}")
                else:
                    raise RuntimeError(
                        "Orchestrator 未产生任何输出\n"
                        "可能原因：\n"
                        "1. TaskDecomposer 分解失败\n"
                        "2. WorkerScheduler 调度失败\n"
                        "3. ResultAggregator 聚合失败\n"
                        "4. LLM API Key 无效或网络问题\n"
                        "\n请检查日志和环境配置"
                    )
            
            # 输出预览
            output_preview = final_output_str[:500]
            if len(final_output_str) > 500:
                output_preview += "\n... (输出已截断，实际更长) ..."
            
            logger.info(f"      - 输出长度: {len(final_output_str)} 字符")
            logger.info(f"      - 输出预览:")
            logger.info("")
            logger.info("      " + "-" * 70)
            for line in output_preview.split('\n'):
                logger.info(f"      {line}")
            logger.info("      " + "-" * 70)
            logger.info("")
            
            # 4. 输出质量验证（高标准严要求）
            logger.info("   4️⃣ 输出质量验证（高标准严要求）:")
            
            quality_checks = {
                "包含'AWS'或'亚马逊'": ("AWS" in final_output_str or "亚马逊" in final_output_str or "Amazon" in final_output_str),
                "包含'Azure'或'微软'": ("Azure" in final_output_str or "微软" in final_output_str or "Microsoft" in final_output_str),
                "包含'GCP'或'Google'": ("GCP" in final_output_str or "Google" in final_output_str or "谷歌" in final_output_str),
                "包含'阿里云'": ("阿里云" in final_output_str or "Aliyun" in final_output_str or "Alibaba" in final_output_str),
                "包含'腾讯云'": ("腾讯云" in final_output_str or "Tencent" in final_output_str),
                "包含'AI'或'人工智能'": ("AI" in final_output_str or "人工智能" in final_output_str or "机器学习" in final_output_str or "大模型" in final_output_str),
                "输出长度 > 200字符": len(final_output_str) > 200,
                "输出长度 > 500字符": len(final_output_str) > 500,
            }
            
            passed_checks = sum(quality_checks.values())
            total_checks = len(quality_checks)
            
            for check_name, passed in quality_checks.items():
                status = "✅" if passed else "❌"
                logger.info(f"      {status} {check_name}")
            
            quality_score = (passed_checks * 100) // total_checks
            logger.info(f"\n      📊 质量评分: {passed_checks}/{total_checks} ({quality_score}%)")
            
            # 🚨 不妥协！低于 70% 视为不合格
            if quality_score < 70:
                logger.error(f"      ❌ 输出质量不达标！")
                raise AssertionError(f"输出质量不达标：{passed_checks}/{total_checks} ({quality_score}%)")
            else:
                logger.info(f"      ✅ 输出质量合格！")
            
            # 5. 事件流验证
            logger.info("")
            logger.info("   5️⃣ 事件流验证:")
            logger.info(f"      - 总事件数: {event_count}")
            
            if event_count < 5:
                logger.warning(f"      ⚠️ 事件数量较少（< 5），可能流程不完整")
            else:
                logger.info(f"      ✅ 事件流正常")
            
            logger.info("")
            logger.info("   ✅ 所有验证项通过！")
        
        except Exception as e:
            logger.error(f"   ❌ 执行失败: {e}", exc_info=True)
            raise


async def main():
    """主函数"""
    validator = OrchestratorE2EValidator()
    await validator.run_validation()


if __name__ == "__main__":
    asyncio.run(main())
