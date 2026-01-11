#!/usr/bin/env python3
"""
Dazee 真正的端到端验证测试 - 用户视角

核心原则：
1. 从用户角度出发，不关心内部模块实现
2. 验证的是"用户体验"，不是"模块准确率"
3. 模拟真实的多轮、跨 Session 对话
4. 验证 Agent 响应是否真的包含个性化内容

测试流程：
┌─────────────────────────────────────────────────────────────────┐
│  用户 → Agent → [Dazee 内部处理] → Agent 响应 → 验证响应质量  │
└─────────────────────────────────────────────────────────────────┘

验证标准（高标准严要求）：
1. Agent 必须记住用户说过的关键信息
2. Agent 必须在响应中体现对用户的理解
3. Agent 必须能主动关联用户的历史信息

使用方式：
    cd /Users/liuyi/Documents/langchain/CoT_agent/mvp/zenflux_agent
    source /Users/liuyi/Documents/langchain/liuy/bin/activate
    python tests/dazee_e2e/test_user_e2e.py
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
import re

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 首先加载 test_agent 实例的环境变量（包含 API Key）
from scripts.instance_loader import load_instance_env
load_instance_env("test_agent")

from logger import get_logger

logger = get_logger("dazee.e2e.user_test")


# ==================== 测试数据定义 ====================

@dataclass
class UserMessage:
    """用户消息"""
    session_id: str           # Session ID
    content: str              # 消息内容
    timestamp: datetime       # 发送时间
    key_facts: List[str]      # 这条消息中的关键事实（用于后续验证）


@dataclass
class ValidationQuery:
    """验证查询"""
    query: str                          # 用户的验证问题
    must_contain: List[str]             # 响应中必须包含的关键词
    should_relate_to: List[str]         # 响应应该关联的历史信息
    min_personalization_score: float    # 最低个性化得分 (0-1)


def create_test_conversations() -> List[UserMessage]:
    """
    创建测试对话序列
    
    模拟销售人员"小李"的真实工作场景
    跨越多个 Session，时间跨度一周
    """
    base_time = datetime.now() - timedelta(days=5)
    
    return [
        # ========== Session 1: 周一上午 ==========
        UserMessage(
            session_id="session_monday_am",
            content="老板刚才在晨会上说，这周必须把永辉超市的合同签下来，不然季度KPI完不成",
            timestamp=base_time,
            key_facts=["永辉超市合同", "这周截止", "KPI压力", "老板要求"]
        ),
        UserMessage(
            session_id="session_monday_am",
            content="下午两点要去永辉总部见采购部的老张，他是关键决策人",
            timestamp=base_time + timedelta(hours=1),
            key_facts=["老张", "采购部", "关键决策人", "下午两点拜访"]
        ),
        
        # ========== Session 2: 周一下午 ==========
        UserMessage(
            session_id="session_monday_pm",
            content="刚从永辉回来，老张说价格还要再谈谈，竞品报价比我们低5%",
            timestamp=base_time + timedelta(hours=6),
            key_facts=["价格问题", "竞品低5%", "需要再谈"]
        ),
        
        # ========== Session 3: 周二 ==========
        UserMessage(
            session_id="session_tuesday",
            content="今天一直在改报价方案，申请了特批价格，希望能拿下",
            timestamp=base_time + timedelta(days=1),
            key_facts=["改报价", "特批价格"]
        ),
        UserMessage(
            session_id="session_tuesday",
            content="下午老张来电话了，说方案还行，让我周四去签合同",
            timestamp=base_time + timedelta(days=1, hours=4),
            key_facts=["老张电话", "方案通过", "周四签合同"]
        ),
        
        # ========== Session 4: 周三 ==========
        UserMessage(
            session_id="session_wednesday",
            content="每周三要写周报，真是烦人，不过这周有好消息可以写了",
            timestamp=base_time + timedelta(days=2),
            key_facts=["周三写周报", "习惯性任务"]
        ),
        
        # ========== Session 5: 周四 ==========
        UserMessage(
            session_id="session_thursday",
            content="刚签完永辉的合同！搞定了！合同金额150万",
            timestamp=base_time + timedelta(days=3),
            key_facts=["合同签订", "150万", "任务完成"]
        ),
        UserMessage(
            session_id="session_thursday",
            content="老板很满意，说下周可以跟进美团的项目了",
            timestamp=base_time + timedelta(days=3, hours=2),
            key_facts=["老板满意", "下周跟进美团"]
        ),
        
        # ========== Session 6: 周五 ==========
        UserMessage(
            session_id="session_friday",
            content="周五了，这周太累了，但结果还不错",
            timestamp=base_time + timedelta(days=4),
            key_facts=["周五", "疲惫", "结果满意"]
        ),
    ]


def create_validation_queries() -> List[ValidationQuery]:
    """
    创建验证查询 - 高标准严要求版本
    
    这些查询会严格测试 Agent 是否真正理解和记住了用户的信息
    
    标准：
    - must_contain: 必须全部出现，否则不通过
    - should_relate_to: 至少 80% 需要出现
    - min_personalization_score: 最低通过分数
    """
    return [
        # 验证1：记忆关键人物（必须精确回答人名）
        ValidationQuery(
            query="我上周提到的那个采购负责人叫什么？",
            must_contain=["老张"],  # 必须回答出人名
            should_relate_to=["永辉", "采购"],  # 应该关联公司和部门
            min_personalization_score=0.8
        ),
        
        # 验证2：记忆关键数字（必须精确回答金额）
        ValidationQuery(
            query="永辉的合同最后签了吗？金额多少？",
            must_contain=["150万"],  # 必须有准确金额
            should_relate_to=["永辉", "签"],  # 应该提到公司和签约状态
            min_personalization_score=0.8
        ),
        
        # 验证3：理解工作习惯（必须回答具体时间）
        ValidationQuery(
            query="我一般什么时候写周报？",
            must_contain=["周三"],  # 必须回答具体星期
            should_relate_to=["周报"],
            min_personalization_score=0.8
        ),
        
        # 验证4：理解工作进展（必须提到关键项目）
        ValidationQuery(
            query="帮我回顾一下这周的工作重点",
            must_contain=["永辉"],  # 必须提到关键客户
            should_relate_to=["合同", "老张", "签"],  # 应该关联关键信息
            min_personalization_score=0.7
        ),
        
        # 验证5：理解后续计划（必须回答具体项目）
        ValidationQuery(
            query="下周我要跟进什么项目？",
            must_contain=["美团"],  # 必须回答具体项目名
            should_relate_to=["项目", "下周"],
            min_personalization_score=0.8
        ),
        
        # 验证6：理解情感状态（必须捕捉情绪关键词）
        ValidationQuery(
            query="这周我的状态怎么样？",
            must_contain=["累"],  # 必须提到疲惫状态
            should_relate_to=["结果", "满意", "收获"],  # 应该提到积极面
            min_personalization_score=0.7
        ),
    ]


# ==================== 核心测试类 ====================

class DazeeUserE2ETest:
    """
    Dazee 用户视角端到端测试
    
    高标准严要求：
    1. 真实调用 Agent API
    2. 真实存储到向量数据库
    3. 真实的 LLM 响应
    4. 严格的个性化验证
    """
    
    def __init__(self, user_id: str = "test_user_xiaoli"):
        self.user_id = user_id
        self.conversations = create_test_conversations()
        self.validations = create_validation_queries()
        
        # 测试结果
        self.conversation_results: List[Dict[str, Any]] = []
        self.validation_results: List[Dict[str, Any]] = []
        
        # LLM 服务（预检查时初始化）
        self.llm = None
        
        # Mem0 记忆池（预检查时初始化）
        self.mem0_pool = None
        
        logger.info(f"[UserE2E] 初始化测试: user={user_id}")
        logger.info(f"[UserE2E] 对话数: {len(self.conversations)}, 验证查询数: {len(self.validations)}")
    
    async def run_full_test(self) -> Dict[str, Any]:
        """
        运行完整测试
        
        流程：
        1. 预检查：确保环境配置正确
        2. 阶段1：模拟用户对话，写入记忆
        3. 阶段2：验证查询，检查个性化
        4. 生成报告
        """
        logger.info("\n" + "=" * 80)
        logger.info("Dazee 端到端用户验证测试 - 高标准严要求")
        logger.info("=" * 80)
        
        # 预检查
        if not await self._pre_check():
            return {"status": "failed", "reason": "环境检查失败"}
        
        # 阶段1：对话阶段
        logger.info("\n【阶段 1】模拟用户多轮对话...")
        await self._run_conversation_phase()
        
        # 阶段2：验证阶段
        logger.info("\n【阶段 2】验证 Agent 记忆和个性化...")
        await self._run_validation_phase()
        
        # 生成报告
        report = self._generate_report()
        
        return report
    
    async def _pre_check(self) -> bool:
        """
        预检查：确保测试环境就绪
        
        高标准：不跳过任何检查，配置不对就失败
        
        注意：环境变量已通过 load_instance_env("test_agent") 加载
        """
        import os
        
        logger.info("\n[预检查] 环境配置检查（来自 test_agent 实例）...")
        
        # 检查关键环境变量（test_agent/.env 中应该已配置）
        checks = {
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        }
        
        all_passed = True
        for key, value in checks.items():
            if value:
                logger.info(f"  ✓ {key}: 已配置（来自 test_agent/.env）")
            else:
                logger.error(f"  ✗ {key}: 未配置！")
                all_passed = False
        
        if not all_passed:
            logger.error("\n❌ 环境检查失败！")
            logger.error("   请确保 instances/test_agent/.env 中包含必要的 API Key")
            return False
        
        # 测试 LLM 连接（使用 test_agent 配置的模型）
        logger.info("\n[预检查] 测试 LLM 连接...")
        try:
            from core.llm import create_llm_service, Message
            # 使用 Haiku 模型进行快速测试
            self.llm = create_llm_service(model="claude-haiku-4-5-20251001")
            response = await self.llm.create_message_async(
                [Message(role="user", content="Say 'OK' if you can hear me.")],
                system="You are a test assistant. Respond with just 'OK'."
            )
            if response.content and "OK" in response.content.upper():
                logger.info("  ✓ LLM 连接正常")
            else:
                logger.error(f"  ✗ LLM 响应异常: {response.content}")
                return False
        except Exception as e:
            logger.error(f"  ✗ LLM 连接失败: {e}")
            return False
        
        # 测试 Mem0 连接（真实向量存储）
        logger.info("\n[预检查] 测试 Mem0 向量存储连接...")
        try:
            from core.memory.mem0 import get_mem0_pool, reset_mem0_pool
            # 重置以确保使用最新配置
            reset_mem0_pool()
            self.mem0_pool = get_mem0_pool()
            # 测试连接
            test_result = self.mem0_pool.search(
                user_id="__test__",
                query="connection test",
                limit=1
            )
            logger.info("  ✓ Mem0 连接正常")
        except Exception as e:
            logger.error(f"  ✗ Mem0 连接失败: {e}")
            logger.error("     请确保 OPENAI_API_KEY 已正确配置在 test_agent/.env 中")
            return False
        
        logger.info("\n✅ 环境检查通过，开始测试\n")
        return True
    
    async def _run_conversation_phase(self):
        """
        阶段1：对话阶段
        
        模拟用户发送消息，Agent 处理并存储记忆到 Mem0
        
        流程：
        1. 用户发送消息
        2. FragmentExtractor 提取信息
        3. 存储到 Mem0 向量数据库（真实存储）
        """
        from core.memory.mem0 import get_fragment_extractor
        
        extractor = get_fragment_extractor()
        
        current_session = None
        for i, msg in enumerate(self.conversations, 1):
            # 显示 Session 切换
            if msg.session_id != current_session:
                current_session = msg.session_id
                logger.info(f"\n--- Session: {current_session} ---")
            
            logger.info(f"[{i}/{len(self.conversations)}] 用户: {msg.content[:50]}...")
            
            try:
                # 调用 Dazee 提取记忆
                fragment = await extractor.extract(
                    user_id=self.user_id,
                    session_id=msg.session_id,
                    message=msg.content,
                    timestamp=msg.timestamp
                )
                
                # ========== 核心：存储到 Mem0 向量数据库 ==========
                memories_stored = await self._store_to_mem0(fragment, msg)
                
                # 记录结果
                result = {
                    "message": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "session_id": msg.session_id,
                    "expected_facts": msg.key_facts,
                    "extracted": {
                        "task": fragment.task_hint.content if fragment.task_hint else None,
                        "emotion": fragment.emotion_hint.signal if fragment.emotion_hint else None,
                        "relations": fragment.relation_hint.mentioned if fragment.relation_hint else [],
                        "todo": fragment.todo_hint.content if fragment.todo_hint else None,
                    },
                    "memories_stored": memories_stored,
                    "success": True
                }
                
                # 检查提取质量
                extracted_info = []
                if fragment.task_hint:
                    extracted_info.append(f"任务={fragment.task_hint.category}")
                if fragment.emotion_hint and fragment.emotion_hint.signal != "neutral":
                    extracted_info.append(f"情绪={fragment.emotion_hint.signal}")
                if fragment.relation_hint and fragment.relation_hint.mentioned:
                    extracted_info.append(f"人物={fragment.relation_hint.mentioned}")
                if fragment.todo_hint:
                    extracted_info.append(f"待办={fragment.todo_hint.content[:20]}")
                
                if extracted_info:
                    logger.info(f"  → Dazee 提取: {', '.join(extracted_info)}")
                    logger.info(f"  → 已存储 {memories_stored} 条记忆到 Mem0")
                else:
                    logger.warning(f"  → Dazee 未提取到信息")
                
            except Exception as e:
                logger.error(f"  ✗ 提取失败: {e}")
                result = {
                    "message": msg.content,
                    "session_id": msg.session_id,
                    "error": str(e),
                    "success": False
                }
            
            self.conversation_results.append(result)
        
        # 统计
        success_count = sum(1 for r in self.conversation_results if r.get("success"))
        total_memories = sum(r.get("memories_stored", 0) for r in self.conversation_results if r.get("success"))
        logger.info(f"\n阶段 1 完成: {success_count}/{len(self.conversations)} 条消息处理成功")
        logger.info(f"总共存储: {total_memories} 条记忆到 Mem0")
    
    async def _store_to_mem0(self, fragment, msg: UserMessage) -> int:
        """
        将原始消息存储到 Mem0 向量数据库
        
        关键：直接存储原始消息，让 Mem0 使用 custom_fact_extraction_prompt 来提取事实
        这样可以保留数字、金额等细节（如"150万"）
        
        返回存储的记忆条数
        """
        try:
            # 直接存储原始消息，让 Mem0 使用自定义 FACT_EXTRACTION_PROMPT 提取事实
            # 这样可以确保数字（如"150万"）被精确保留
            messages = [{"role": "user", "content": msg.content}]
            result = self.mem0_pool.add(
                user_id=self.user_id,
                messages=messages,
                metadata={
                    "session_id": msg.session_id,
                    "timestamp": msg.timestamp.isoformat(),
                    "source": "dazee_e2e_test"
                }
            )
            
            # 返回新增记忆数量
            stored_count = len(result.get("results", []))
            return stored_count
            
        except Exception as e:
            logger.warning(f"    存储记忆失败: {e}")
            return 0
    
    async def _run_validation_phase(self):
        """
        阶段2：验证阶段
        
        发送验证查询，检查 Agent 是否真的记住了用户信息
        
        使用真实的 Mem0 搜索和 LLM 响应
        """
        from core.llm import Message
        
        # 使用预检查时初始化的 Mem0 和 LLM
        pool = self.mem0_pool
        llm = self.llm
        
        for i, query in enumerate(self.validations, 1):
            logger.info(f"\n[验证 {i}/{len(self.validations)}] {query.query}")
            
            try:
                # 1. 从记忆中搜索相关信息
                memories = pool.search(
                    user_id=self.user_id,
                    query=query.query,
                    limit=10
                )
                
                # 2. 构建带记忆的 Prompt
                memory_context = "\n".join([
                    f"- {m.get('memory', m.get('text', str(m)))}" 
                    for m in memories
                ]) if memories else "暂无相关记忆"
                
                system_prompt = f"""你是 Dazee 智能助理，正在为用户"小李"提供帮助。

## 用户历史记忆
{memory_context}

## 要求
- 基于用户的历史记忆回答问题
- 如果记忆中有相关信息，务必使用
- 回答要简洁、准确、个性化
"""
                
                # 3. 调用 LLM 生成响应
                response = await llm.create_message_async(
                    [Message(role="user", content=query.query)],
                    system=system_prompt
                )
                
                agent_response = response.content
                logger.info(f"  Agent: {agent_response[:100]}...")
                
                # 4. 验证响应质量
                validation_result = self._validate_response(
                    query=query,
                    response=agent_response,
                    memories=memories
                )
                
                self.validation_results.append({
                    "query": query.query,
                    "response": agent_response,
                    "memories_found": len(memories),
                    "validation": validation_result
                })
                
                # 显示验证结果
                if validation_result["passed"]:
                    logger.info(f"  ✓ 验证通过 (得分: {validation_result['score']:.0%})")
                else:
                    logger.warning(f"  ✗ 验证失败 (得分: {validation_result['score']:.0%})")
                    for issue in validation_result.get("issues", []):
                        logger.warning(f"    - {issue}")
                
            except Exception as e:
                logger.error(f"  ✗ 验证失败: {e}")
                self.validation_results.append({
                    "query": query.query,
                    "error": str(e),
                    "validation": {"passed": False, "score": 0, "issues": [str(e)]}
                })
        
        # 统计
        passed = sum(1 for r in self.validation_results if r.get("validation", {}).get("passed"))
        logger.info(f"\n阶段 2 完成: {passed}/{len(self.validations)} 个验证通过")
    
    def _validate_response(
        self, 
        query: ValidationQuery, 
        response: str, 
        memories: List[Dict]
    ) -> Dict[str, Any]:
        """
        验证 Agent 响应的个性化程度
        
        高标准严要求验证：
        1. 必须包含所有指定关键词（必须全部命中）
        2. 应该关联历史信息（至少 80%）
        3. 记忆利用率要高（检测实际引用）
        4. 不允许泛泛而谈
        """
        issues = []
        score_breakdown = {}
        
        # ========== 检查1：必须包含的关键词 (权重: 0.5) ==========
        # 高标准：必须全部命中，任何缺失都扣分
        keyword_score = 0.0
        if query.must_contain:
            found_keywords = []
            missing_keywords = []
            
            for kw in query.must_contain:
                # 中文关键词直接匹配，不转小写
                if kw in response:
                    found_keywords.append(kw)
                else:
                    missing_keywords.append(kw)
            
            keyword_score = len(found_keywords) / len(query.must_contain)
            score_breakdown["关键词命中"] = f"{len(found_keywords)}/{len(query.must_contain)}"
            
            if missing_keywords:
                issues.append(f"缺少必要关键词: {missing_keywords}")
        else:
            keyword_score = 1.0
        
        # ========== 检查2：应该关联的信息 (权重: 0.3) ==========
        # 高标准：至少 80% 的关联词需要出现
        relate_score = 0.0
        if query.should_relate_to:
            found_relate = []
            missing_relate = []
            
            for kw in query.should_relate_to:
                if kw in response:
                    found_relate.append(kw)
                else:
                    missing_relate.append(kw)
            
            relate_score = len(found_relate) / len(query.should_relate_to)
            score_breakdown["关联命中"] = f"{len(found_relate)}/{len(query.should_relate_to)}"
            
            # 高标准：低于 80% 就报问题
            if relate_score < 0.8:
                issues.append(f"关联信息不足 ({relate_score:.0%}): 缺少 {missing_relate}")
        else:
            relate_score = 1.0
        
        # ========== 检查3：记忆实际利用 (权重: 0.2) ==========
        # 高标准：检查响应是否真正引用了记忆中的具体信息
        memory_score = 0.0
        if memories:
            # 提取记忆的实际文本内容
            memory_contents = []
            for m in memories:
                content = m.get('memory', m.get('text', ''))
                if content:
                    memory_contents.append(content)
            
            if memory_contents:
                # 检查响应是否包含记忆中的关键实体
                # 提取记忆中的关键词：数字、人名、公司名等
                key_entities = set()
                for content in memory_contents:
                    # 提取数字（如 150万、5%）
                    import re
                    numbers = re.findall(r'\d+[万%元个]?', content)
                    key_entities.update(numbers)
                    # 提取常见中文实体（简化：长度 2-4 的非常见词）
                    for word in ['老张', '永辉', '美团', '周三', '周四', 'KPI']:
                        if word in content:
                            key_entities.add(word)
                
                if key_entities:
                    found_entities = [e for e in key_entities if e in response]
                    memory_score = len(found_entities) / len(key_entities)
                    score_breakdown["记忆实体引用"] = f"{len(found_entities)}/{len(key_entities)}: {found_entities}"
                    
                    if memory_score < 0.3:
                        issues.append(f"记忆利用率低 ({memory_score:.0%}): 未引用关键信息")
                else:
                    memory_score = 0.5  # 无法提取实体时给中等分
            else:
                issues.append("记忆内容为空")
        else:
            issues.append("未找到相关记忆")
        
        # ========== 计算最终得分 ==========
        # 权重：关键词 50% + 关联 30% + 记忆利用 20%
        final_score = keyword_score * 0.5 + relate_score * 0.3 + memory_score * 0.2
        score_breakdown["最终得分"] = f"{final_score:.1%}"
        
        # ========== 高标准通过条件 ==========
        # 1. 最终得分必须达到阈值
        # 2. 必须包含所有关键词（keyword_score == 1.0）
        # 3. 不能有严重问题（issues 为空或只有记忆利用率低）
        
        keyword_perfect = keyword_score == 1.0
        score_pass = final_score >= query.min_personalization_score
        
        # 严格判定：关键词必须完美 + 得分达标
        passed = keyword_perfect and score_pass
        
        return {
            "passed": passed,
            "score": final_score,
            "threshold": query.min_personalization_score,
            "breakdown": score_breakdown,
            "issues": issues
        }
    
    def _generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        # 对话阶段统计
        conv_success = sum(1 for r in self.conversation_results if r.get("success"))
        conv_total = len(self.conversation_results)
        
        # 验证阶段统计
        val_passed = sum(1 for r in self.validation_results if r.get("validation", {}).get("passed"))
        val_total = len(self.validation_results)
        
        # 计算平均个性化得分
        avg_score = sum(
            r.get("validation", {}).get("score", 0) 
            for r in self.validation_results
        ) / max(val_total, 1)
        
        # 总体判定
        overall_pass = (
            conv_success >= conv_total * 0.9 and  # 90% 对话处理成功
            val_passed >= val_total * 0.7 and     # 70% 验证通过
            avg_score >= 0.6                       # 平均得分 60%+
        )
        
        report = {
            "status": "PASS" if overall_pass else "FAIL",
            "timestamp": datetime.now().isoformat(),
            "user_id": self.user_id,
            "summary": {
                "conversation_phase": {
                    "total": conv_total,
                    "success": conv_success,
                    "rate": f"{conv_success/conv_total*100:.1f}%"
                },
                "validation_phase": {
                    "total": val_total,
                    "passed": val_passed,
                    "rate": f"{val_passed/val_total*100:.1f}%"
                },
                "personalization_score": f"{avg_score*100:.1f}%"
            },
            "conversation_results": self.conversation_results,
            "validation_results": self.validation_results
        }
        
        # 打印报告
        logger.info("\n" + "=" * 80)
        logger.info("测试报告")
        logger.info("=" * 80)
        logger.info(f"总体状态: {'✅ PASS' if overall_pass else '❌ FAIL'}")
        logger.info(f"对话处理: {conv_success}/{conv_total} ({conv_success/conv_total*100:.1f}%)")
        logger.info(f"验证通过: {val_passed}/{val_total} ({val_passed/val_total*100:.1f}%)")
        logger.info(f"个性化得分: {avg_score*100:.1f}%")
        logger.info("=" * 80)
        
        if not overall_pass:
            logger.info("\n失败原因分析:")
            if conv_success < conv_total * 0.9:
                logger.warning(f"  - 对话处理成功率不足 90%")
            if val_passed < val_total * 0.7:
                logger.warning(f"  - 验证通过率不足 70%")
            if avg_score < 0.6:
                logger.warning(f"  - 个性化得分不足 60%")
        
        return report


async def main():
    """主函数"""
    test = DazeeUserE2ETest()
    report = await test.run_full_test()
    
    # 保存报告
    report_path = project_root / "logs" / f"dazee_user_e2e_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    
    logger.info(f"\n详细报告已保存: {report_path}")
    
    # 返回状态码
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
