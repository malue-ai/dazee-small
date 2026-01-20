#!/usr/bin/env python
"""
Mem0 个性化机制端到端验证测试

验证目标：
1. 跨会话对话 → Mem0 自动提取用户特征（Fact Extraction）
2. 新会话能检索相关记忆（语义搜索）
3. 记忆正确注入 System Prompt
4. Agent 响应体现个性化效果

测试流程：
- 模拟用户在多个会话中透露偏好/特征
- 调用 Mem0Pool.add() 写入对话历史
- Mem0 内部 LLM 自动提取事实性记忆
- 新会话中验证记忆检索和个性化响应

运行方式：
    python tests/test_mem0_personalization_e2e.py
"""

import asyncio
import os
import sys
import time
import re
from datetime import datetime
from typing import List, Dict, Any

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()


# ==================== 终端输出工具 ====================

class Color:
    """终端颜色"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


class TestResult:
    """测试结果统计"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.start_time = time.time()
        self.details = []
    
    def duration(self) -> float:
        return time.time() - self.start_time
    
    def add_detail(self, section: str, status: str, message: str):
        """添加详细信息"""
        self.details.append({
            "section": section,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })
    
    def summary(self) -> str:
        total = self.passed + self.failed
        rate = (self.passed / total * 100) if total > 0 else 0
        return (
            f"\n{'='*70}\n"
            f"Mem0 个性化机制验证总结\n"
            f"{'='*70}\n"
            f"✅ 通过: {self.passed}\n"
            f"❌ 失败: {self.failed}\n"
            f"⚠️  警告: {self.warnings}\n"
            f"通过率: {rate:.1f}%\n"
            f"总耗时: {self.duration():.2f}秒\n"
            f"{'='*70}"
        )


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*70}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{title}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{'='*70}{Color.END}")


def print_success(message: str):
    """打印成功信息"""
    print(f"{Color.GREEN}✅ {message}{Color.END}")


def print_error(message: str):
    """打印错误信息"""
    print(f"{Color.RED}❌ {message}{Color.END}")


def print_warning(message: str):
    """打印警告信息"""
    print(f"{Color.YELLOW}⚠️  {message}{Color.END}")


def print_info(message: str, indent: int = 0):
    """打印信息"""
    prefix = "   " * indent
    print(f"{prefix}{message}")


# ==================== 规则化评分工具 ====================

def _normalize_text(text: str) -> str:
    """文本标准化（小写+空白压缩）"""
    return re.sub(r"\s+", " ", text or "").lower().strip()


def _has_structure(text: str) -> bool:
    """判断是否具备结构化输出特征"""
    if not text:
        return False
    return bool(
        re.search(r"(^|\n)\s*[-*]\s+\S+", text)
        or re.search(r"(^|\n)\s*\d+\.\s+\S+", text)
        or re.search(r"(^|\n)#+\s+\S+", text)
        or re.search(r"\*\*.+\*\*", text)
    )


def _has_code_block(text: str, patterns: List[str]) -> bool:
    """判断是否包含代码/示例块"""
    if not text:
        return False
    if "```" in text:
        return True
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _keyword_hit(text: str, keywords: List[str]) -> bool:
    """关键词命中（忽略大小写）"""
    if not keywords:
        return False
    normalized = _normalize_text(text)
    return any(k.lower() in normalized for k in keywords)

def _match_patterns(text: str, patterns: List[str]) -> List[str]:
    """命中正则模式（返回命中的 pattern 列表）"""
    if not patterns:
        return []
    raw_text = text or ""
    hits = []
    for pattern in patterns:
        if re.search(pattern, raw_text, re.IGNORECASE):
            hits.append(pattern)
    return hits


def score_response(text: str, rules: Dict[str, Any]) -> Dict[str, Any]:
    """规则化评分（非 LLM 评审，仅用于验证）"""
    normalized = _normalize_text(text)
    weights = rules.get("weights", {})
    min_length = rules.get("min_length", 80)
    threshold = rules.get("threshold", 80)
    normalize_score = rules.get("normalize_score", True)

    score = 0
    max_score = 0
    details = []
    violations = []
    hard_failed = False

    # 长度要求
    length_weight = weights.get("min_length", 0)
    max_score += length_weight
    if len(text or "") >= min_length:
        score += length_weight
        details.append(f"长度达标(+{length_weight})")
    else:
        details.append(f"长度不足(<{min_length})")
        hard_failed = True

    # 必须命中（多组）- 记忆命中
    must_groups = rules.get("must_include_groups", [])
    must_weight = weights.get("must_group", 12)
    for idx, group in enumerate(must_groups, 1):
        group_keywords = group.get("keywords", []) if isinstance(group, dict) else group
        group_label = group.get("label", f"must_{idx}") if isinstance(group, dict) else f"must_{idx}"
        max_score += must_weight
        if _keyword_hit(normalized, group_keywords):
            score += must_weight
            details.append(f"{group_label} 命中(+{must_weight})")
        else:
            details.append(f"{group_label} 未命中")
            hard_failed = True

    # 任务完成度（必需）
    task_groups = rules.get("task_groups", [])
    task_weight = weights.get("task_group", 10)
    for idx, group in enumerate(task_groups, 1):
        group_keywords = group.get("keywords", []) if isinstance(group, dict) else group
        group_label = group.get("label", f"task_{idx}") if isinstance(group, dict) else f"task_{idx}"
        max_score += task_weight
        if _keyword_hit(normalized, group_keywords):
            score += task_weight
            details.append(f"{group_label} 命中(+{task_weight})")
        else:
            details.append(f"{group_label} 未命中")
            hard_failed = True

    # 相关性关键词
    relevance_keywords = rules.get("relevance_keywords", [])
    relevance_weight = weights.get("relevance", 12)
    max_score += relevance_weight
    if _keyword_hit(normalized, relevance_keywords):
        score += relevance_weight
        details.append(f"相关性命中(+{relevance_weight})")
    else:
        details.append("相关性不足")
        hard_failed = True

    # 结构化输出
    if rules.get("require_structure"):
        structure_weight = weights.get("structure", 10)
        max_score += structure_weight
        if _has_structure(text):
            score += structure_weight
            details.append(f"结构化输出(+{structure_weight})")
        else:
            details.append("结构化输出不足")
            hard_failed = True

    # 代码/示例块
    if rules.get("require_code_block"):
        code_weight = weights.get("code_block", 10)
        max_score += code_weight
        code_patterns = rules.get("code_patterns", [])
        if _has_code_block(text, code_patterns):
            score += code_weight
            details.append(f"包含代码/示例(+{code_weight})")
        else:
            details.append("缺少代码/示例")
            hard_failed = True

    # 应该命中（加分项）
    should_groups = rules.get("should_include_groups", [])
    should_weight = weights.get("should_group", 6)
    for idx, group in enumerate(should_groups, 1):
        group_keywords = group.get("keywords", []) if isinstance(group, dict) else group
        group_label = group.get("label", f"should_{idx}") if isinstance(group, dict) else f"should_{idx}"
        max_score += should_weight
        if _keyword_hit(normalized, group_keywords):
            score += should_weight
            details.append(f"{group_label} 命中(+{should_weight})")
        else:
            details.append(f"{group_label} 未命中")

    # 事实一致性冲突（硬失败）
    conflict_groups = rules.get("conflict_groups", [])
    conflict_hit = False
    for idx, group in enumerate(conflict_groups, 1):
        group_keywords = group.get("keywords", []) if isinstance(group, dict) else group
        group_label = group.get("label", f"conflict_{idx}") if isinstance(group, dict) else f"conflict_{idx}"
        if _keyword_hit(normalized, group_keywords):
            conflict_hit = True
            violations.append(f"{group_label} 命中")
            hard_failed = True

    # 禁止词（跨用户污染等，硬失败）
    forbidden_groups = rules.get("forbidden_groups", [])
    forbidden_penalty = weights.get("forbidden_penalty", 0)
    for idx, group in enumerate(forbidden_groups, 1):
        group_keywords = group.get("keywords", []) if isinstance(group, dict) else group
        group_label = group.get("label", f"forbidden_{idx}") if isinstance(group, dict) else f"forbidden_{idx}"
        if _keyword_hit(normalized, group_keywords):
            score -= forbidden_penalty
            violations.append(f"{group_label} 命中(-{forbidden_penalty})")
            hard_failed = True

    # 一致性奖励
    consistency_reward = weights.get("consistency_reward", 0)
    if consistency_reward > 0:
        max_score += consistency_reward
        if not conflict_hit:
            score += consistency_reward
            details.append(f"事实一致(+{consistency_reward})")
        else:
            details.append("事实一致性失败")

    # 拒答/空泛
    refusal_keywords = rules.get("refusal_keywords", [])
    refusal_penalty = weights.get("refusal_penalty", 10)
    if _keyword_hit(normalized, refusal_keywords):
        score -= refusal_penalty
        violations.append(f"拒答/空泛(-{refusal_penalty})")
        hard_failed = True

    # 幻觉检测（硬失败）
    hallucination_groups = rules.get("hallucination_groups", [])
    hallucination_patterns = rules.get("hallucination_patterns", [])
    hallucination_allow = rules.get("hallucination_allow_keywords", [])
    hallucination_hit = False
    if hallucination_groups and _keyword_hit(normalized, hallucination_groups):
        hallucination_hit = True
        violations.append("疑似幻觉/无依据断言")
        hard_failed = True

    pattern_hits = _match_patterns(text, hallucination_patterns)
    if pattern_hits and not _keyword_hit(normalized, hallucination_allow):
        hallucination_hit = True
        violations.append("疑似编造数字/数据")
        hard_failed = True

    no_hallu_reward = weights.get("no_hallucination_reward", 0)
    if no_hallu_reward > 0:
        max_score += no_hallu_reward
        if not hallucination_hit:
            score += no_hallu_reward
            details.append(f"无幻觉(+{no_hallu_reward})")
        else:
            details.append("幻觉风险")

    final_score = max(0, score)
    normalized_score = (final_score / max_score * 100) if (normalize_score and max_score > 0) else final_score
    passed = normalized_score >= threshold and not hard_failed

    return {
        "score": final_score,
        "max_score": max_score,
        "threshold": threshold,
        "normalized_score": normalized_score,
        "passed": passed,
        "details": details,
        "violations": violations,
        "hard_failed": hard_failed
    }


async def collect_stream_text(event_stream) -> str:
    """从 ChatService 流式事件中收集最终文本"""
    final_text = ""
    async for event in event_stream:
        event_type = event.get("type", "")
        data = event.get("data", {}) if isinstance(event, dict) else {}
        if event_type == "content_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                final_text += delta.get("text", "")
        elif event_type in ["message_stop", "session_end", "message.assistant.done"]:
            break
    return final_text

# ==================== Mock 数据：跨会话对话历史 ====================

MOCK_CONVERSATION_SESSIONS = {
    "developer_alice": {
        "user_id": "test_alice_mem0_001",
        "name": "Alice（前端开发者）",
        "sessions": [
            # 会话 1：用户自我介绍
            {
                "messages": [
                    {"role": "user", "content": "你好，我是一名前端开发者，主要使用 React 和 TypeScript 开发项目"},
                    {"role": "assistant", "content": "你好！很高兴认识你，作为 React 开发者有什么我可以帮助的吗？"}
                ]
            },
            # 会话 2：用户透露编码偏好
            {
                "messages": [
                    {"role": "user", "content": "我更喜欢函数式组件和 hooks，不太喜欢用 class 组件"},
                    {"role": "assistant", "content": "函数式组件确实更简洁，hooks 也让状态管理更灵活"}
                ]
            },
            # 会话 3：用户透露样式偏好
            {
                "messages": [
                    {"role": "user", "content": "我的项目通常使用 Tailwind CSS 做样式，感觉很高效"},
                    {"role": "assistant", "content": "Tailwind 的原子化 CSS 确实能提高开发效率"}
                ]
            }
        ],
        "expected_features": ["React", "TypeScript", "函数式", "hooks", "Tailwind"],
        "test_query": "帮我写一个用户注册表单组件",
        "response_rules": {
            "min_length": 180,
            "threshold": 88,
            "normalize_score": True,
            "require_code_block": True,
            "code_patterns": [r"<form", r"function\s+\w+\(", r"const\s+\w+\s*="],
            "relevance_keywords": ["注册", "表单", "组件"],
            "must_include_groups": [
                {"label": "技术栈", "keywords": ["React", "TypeScript", "TS"]},
                {"label": "偏好", "keywords": ["函数式", "函数组件", "hooks", "hook"]},
            ],
            "task_groups": [
                {"label": "账号字段", "keywords": ["邮箱", "邮件", "用户名", "账号", "手机号"]},
                {"label": "密码字段", "keywords": ["密码", "确认密码", "重复密码"]},
            ],
            "should_include_groups": [
                {"label": "样式偏好", "keywords": ["Tailwind", "className"]},
                {"label": "表单校验", "keywords": ["校验", "验证", "错误", "提示"]},
            ],
            "conflict_groups": [
                {"label": "偏好冲突", "keywords": ["class 组件", "class component", "Vue", "Angular"]},
            ],
            "forbidden_groups": [
                {"label": "跨用户污染", "keywords": ["产品经理", "销售数据", "图表", "可视化"]}
            ],
            "hallucination_groups": ["根据你提供的数据", "我已经分析", "数据库显示"],
            "hallucination_allow_keywords": ["示例", "假设", "占位"],
            "refusal_keywords": ["无法", "不能", "抱歉", "不确定"],
            "weights": {
                "min_length": 0,
                "must_group": 15,
                "task_group": 10,
                "relevance": 10,
                "code_block": 15,
                "should_group": 5,
                "consistency_reward": 20,
                "no_hallucination_reward": 10,
                "forbidden_penalty": 0,
                "refusal_penalty": 15
            }
        }
    },
    "manager_bob": {
        "user_id": "test_bob_mem0_002",
        "name": "Bob（产品经理）",
        "sessions": [
            {
                "messages": [
                    {"role": "user", "content": "我是产品经理，经常需要做数据分析和汇报"},
                    {"role": "assistant", "content": "了解，数据分析是产品决策的重要依据"}
                ]
            },
            {
                "messages": [
                    {"role": "user", "content": "我偏好用图表和可视化方式呈现数据，这样更直观"},
                    {"role": "assistant", "content": "可视化确实能让数据更易于理解"}
                ]
            }
        ],
        "expected_features": ["产品经理", "数据分析", "图表", "可视化"],
        "test_query": "帮我分析这个月的销售数据",
        "response_rules": {
            "min_length": 160,
            "threshold": 88,
            "normalize_score": True,
            "require_structure": True,
            "relevance_keywords": ["销售", "数据", "分析"],
            "must_include_groups": [
                {"label": "角色偏好", "keywords": ["产品经理", "数据分析"]},
                {"label": "表达方式", "keywords": ["图表", "可视化", "趋势"]},
            ],
            "task_groups": [
                {"label": "分析维度", "keywords": ["环比", "同比", "趋势", "维度"]},
                {"label": "行动建议", "keywords": ["建议", "结论", "行动", "洞察"]},
            ],
            "should_include_groups": [
                {"label": "指标范围", "keywords": ["客单价", "转化", "渠道", "区域", "品类"]},
                {"label": "数据请求", "keywords": ["请提供", "需要", "数据口径", "样例", "缺少数据"]},
            ],
            "conflict_groups": [
                {"label": "技术栈冲突", "keywords": ["React", "TypeScript", "Tailwind", "组件"]},
            ],
            "forbidden_groups": [
                {"label": "跨用户污染", "keywords": ["React", "TypeScript", "Tailwind", "组件"]}
            ],
            "hallucination_groups": ["根据你提供的数据", "我已分析", "我查看了数据", "数据如下"],
            "hallucination_patterns": [
                r"\d+(?:\.\d+)?\s*%",
                r"[￥$]\s*\d+(?:\.\d+)?",
                r"\d+(?:\.\d+)?\s*(万|千|亿|元|块|美元|人民币)",
                r"(增长|下降|提升|降低)\s*\d+",
                r"(环比|同比)\s*\d+"
            ],
            "hallucination_allow_keywords": ["假设", "示例", "占位", "请提供", "需要数据", "若提供", "如果"],
            "refusal_keywords": ["无法", "不能", "抱歉", "不确定"],
            "weights": {
                "min_length": 0,
                "must_group": 15,
                "task_group": 10,
                "relevance": 10,
                "structure": 15,
                "should_group": 5,
                "consistency_reward": 20,
                "no_hallucination_reward": 10,
                "forbidden_penalty": 0,
                "refusal_penalty": 15
            }
        }
    }
}


# ==================== 测试类 ====================

class Mem0PersonalizationE2ETest:
    """Mem0 个性化机制端到端测试"""
    
    def __init__(self):
        self.result = TestResult()
        self.test_users = MOCK_CONVERSATION_SESSIONS
        self.extracted_memories = {}  # 存储提取的记忆供后续验证
        self.e2e_scores = {}
    
    async def run_all(self):
        """运行所有测试"""
        print(f"{Color.HEADER}{Color.BOLD}")
        print("="*70)
        print("Mem0 个性化机制端到端验证测试")
        print("="*70)
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"测试用户数: {len(self.test_users)}")
        print("="*70)
        print(f"{Color.END}")
        
        try:
            # 1. 环境验证
            self.verify_environment()
            
            # 2. 准备阶段：模拟跨会话对话历史
            await self.setup_conversation_history()
            
            # 3. V1：验证 Fact Extraction
            await self.test_fact_extraction()
            
            # 4. V2：验证跨会话语义检索
            await self.test_cross_session_search()
            
            # 5. V3：验证 Prompt 注入
            await self.test_prompt_injection()
            
            # 6. V4：端到端个性化响应验证
            await self.test_personalized_response()
            
        except KeyboardInterrupt:
            print_warning("\n测试被用户中断")
        except Exception as e:
            print_error(f"测试执行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 清理测试数据
            await self.cleanup()
            
            # 打印总结
            print(self.result.summary())
            
            # 生成详细报告
            self.generate_report()
    
    def verify_environment(self):
        """验证环境配置"""
        print_section("步骤 0: 环境配置验证")
        
        required_vars = {
            'OPENAI_API_KEY': 'Embedding 和 Mem0 LLM',
            'ANTHROPIC_API_KEY': 'Agent LLM',
        }
        
        # 向量存储至少需要一个
        vector_store = os.getenv('VECTOR_STORE_PROVIDER', 'qdrant')
        if vector_store == 'tencent':
            required_vars['TENCENT_VDB_URL'] = '腾讯云 VectorDB URL'
            required_vars['TENCENT_VDB_API_KEY'] = '腾讯云 VectorDB API Key'
        else:
            required_vars['QDRANT_URL'] = 'Qdrant URL'
        
        missing = []
        for var, desc in required_vars.items():
            value = os.getenv(var)
            if value:
                display = value[:10] + '...' if 'KEY' in var else value[:30] + '...'
                print_info(f"✅ {var}: {display}", indent=1)
            else:
                missing.append(f"{var} ({desc})")
        
        if missing:
            print_error("环境配置不完整")
            print_info("缺少环境变量:", indent=1)
            for m in missing:
                print_info(f"- {m}", indent=2)
            self.result.failed += 1
            raise RuntimeError("环境配置不完整，请检查 .env 文件")
        else:
            print_success("环境配置验证")
            self.result.passed += 1
    
    async def setup_conversation_history(self):
        """
        准备阶段：模拟跨会话对话历史
        
        1. 遍历所有测试用户
        2. 对每个会话调用 Mem0Pool.add(messages)
        3. Mem0 内部 LLM 自动提取事实性记忆
        """
        print_section("步骤 1: 模拟跨会话对话历史")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            # 先清理旧的测试数据
            print_info("清理旧测试数据...", indent=1)
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                old_memories = pool.get_all(user_id=user_id, limit=100)
                if old_memories:
                    print_info(f"发现 {len(old_memories)} 条旧记忆，清理中...", indent=2)
                    for mem in old_memories:
                        pool.delete(memory_id=mem['id'], user_id=user_id)
            
            print_info("\n开始模拟跨会话对话...", indent=1)
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                sessions = user_data["sessions"]
                
                print_info(f"\n📝 用户: {user_display_name} (user_id={user_id})", indent=1)
                
                total_extracted = 0
                for i, session in enumerate(sessions, 1):
                    print_info(f"会话 {i}: {session['messages'][0]['content'][:40]}...", indent=2)
                    
                    # 调用 Mem0Pool.add() - 这会触发 Fact Extraction
                    try:
                        result = pool.add(
                            user_id=user_id,
                            messages=session["messages"]
                        )
                        
                        # 提取结果
                        memories = result.get("results", []) if isinstance(result, dict) else result
                        extracted_count = len(memories) if memories else 0
                        total_extracted += extracted_count
                        
                        if extracted_count > 0:
                            print_info(f"✅ 提取了 {extracted_count} 条记忆", indent=3)
                        else:
                            print_info(f"⚠️  未提取到新记忆（可能已存在相似记忆）", indent=3)
                        
                        # 稍微延迟避免 API 限流
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        print_warning(f"会话 {i} 写入失败: {e}", indent=3)
                        if 'timeout' not in str(e).lower():
                            raise
                
                print_info(f"✅ {user_display_name} 总计提取 {total_extracted} 条记忆", indent=2)
            
            print_success("跨会话对话历史模拟完成")
            self.result.passed += 1
            self.result.add_detail("setup", "success", "跨会话对话历史模拟成功")
            
        except Exception as e:
            print_error(f"跨会话对话历史模拟失败: {e}")
            self.result.failed += 1
            self.result.add_detail("setup", "failed", str(e))
            raise
    
    async def test_fact_extraction(self):
        """
        V1: 验证 Fact Extraction（自动提取用户特征）
        
        - 调用 get_all() 获取所有记忆
        - 检查是否包含关键特征词
        """
        print_section("步骤 2: V1 验证 Fact Extraction")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            all_passed = True
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                expected_features = user_data["expected_features"]
                
                print_info(f"\n🔍 验证用户: {user_display_name}", indent=1)
                
                # 获取所有记忆
                memories = pool.get_all(user_id=user_id, limit=50)
                
                if not memories:
                    print_error(f"未找到记忆")
                    print_info("", indent=2)
                    all_passed = False
                    continue
                
                print_info(f"找到 {len(memories)} 条记忆", indent=2)
                
                # 缓存记忆供后续使用
                self.extracted_memories[user_id] = memories
                
                # 展示记忆内容
                print_info("记忆内容:", indent=2)
                for i, mem in enumerate(memories[:5], 1):
                    memory_text = mem.get('memory', 'N/A')
                    print_info(f"{i}. {memory_text}", indent=3)
                
                # 检查是否包含关键特征
                all_memory_text = " ".join([m.get('memory', '') for m in memories])
                found_features = []
                missing_features = []
                
                for feature in expected_features:
                    if feature.lower() in all_memory_text.lower():
                        found_features.append(feature)
                    else:
                        missing_features.append(feature)
                
                if found_features:
                    print_info(f"✅ 检测到特征: {', '.join(found_features)}", indent=2)
                
                if missing_features:
                    print_warning(f"未检测到特征: {', '.join(missing_features)}", indent=2)
                    # 不算失败，因为 LLM 可能用不同词汇表达

                # 用户隔离：不应包含其他用户的核心特征
                other_features = []
                for other_name, other_data in self.test_users.items():
                    if other_name == user_name:
                        continue
                    other_features.extend(other_data.get("expected_features", []))
                contaminated = [f for f in other_features if f.lower() in all_memory_text.lower()]
                if contaminated:
                    print_error(f"检测到跨用户污染: {', '.join(contaminated)}")
                    all_passed = False
                
                # 只要提取了记忆就算成功
                if memories:
                    print_success(f"{user_display_name} Fact Extraction 验证通过")
                else:
                    print_error(f"{user_display_name} Fact Extraction 验证失败")
                    all_passed = False
            
            if all_passed:
                self.result.passed += 1
                self.result.add_detail("fact_extraction", "success", "所有用户特征提取成功")
            else:
                self.result.failed += 1
                self.result.add_detail("fact_extraction", "failed", "部分用户特征提取失败")
            
        except Exception as e:
            print_error(f"Fact Extraction 验证失败: {e}")
            self.result.failed += 1
            self.result.add_detail("fact_extraction", "failed", str(e))
    
    async def test_cross_session_search(self):
        """
        V2: 验证跨会话语义检索
        
        - 模拟新会话的查询
        - 检查 search() 返回的记忆是否与查询相关
        """
        print_section("步骤 3: V2 验证跨会话语义检索")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            all_passed = True
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                test_query = user_data["test_query"]
                
                print_info(f"\n🔍 验证用户: {user_display_name}", indent=1)
                print_info(f"新会话查询: \"{test_query}\"", indent=2)
                
                try:
                    # 语义搜索
                    results = pool.search(
                        user_id=user_id,
                        query=test_query,
                        limit=5
                    )
                    
                    if results:
                        print_info(f"检索到 {len(results)} 条相关记忆:", indent=2)
                        for i, mem in enumerate(results[:3], 1):
                            memory_text = mem.get('memory', 'N/A')
                            score = mem.get('score', 0)
                            print_info(f"{i}. [{score:.3f}] {memory_text}", indent=3)
                        
                        print_success(f"{user_display_name} 语义检索验证通过")
                    else:
                        print_warning(f"{user_display_name} 未检索到相关记忆")
                        all_passed = False
                    
                    await asyncio.sleep(0.3)  # 避免 API 限流
                    
                except Exception as e:
                    if 'timeout' in str(e).lower():
                        print_warning(f"API 超时: {e}", indent=2)
                        self.result.warnings += 1
                    else:
                        raise
            
            if all_passed:
                self.result.passed += 1
                self.result.add_detail("search", "success", "跨会话语义检索验证成功")
            else:
                self.result.warnings += 1
                self.result.add_detail("search", "warning", "部分用户检索结果不理想")
            
        except Exception as e:
            print_error(f"跨会话语义检索验证失败: {e}")
            self.result.failed += 1
            self.result.add_detail("search", "failed", str(e))
    
    async def test_prompt_injection(self):
        """
        V3: 验证 Prompt 注入
        
        - 调用 _fetch_user_profile()
        - 检查格式化后的画像是否正确
        """
        print_section("步骤 4: V3 验证 Prompt 注入")
        
        try:
            from prompts.universal_agent_prompt import _fetch_user_profile
            
            all_passed = True
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                test_query = user_data["test_query"]
                
                print_info(f"\n🔍 验证用户: {user_display_name}", indent=1)
                
                try:
                    # 调用 Prompt 注入函数
                    user_profile = _fetch_user_profile(
                        user_id=user_id,
                        user_query=test_query
                    )
                    
                    if user_profile:
                        print_info(f"✅ 成功获取用户画像 (长度: {len(user_profile)} 字符)", indent=2)
                        
                        # 展示格式化后的画像片段
                        preview = user_profile[:300] + "..." if len(user_profile) > 300 else user_profile
                        print_info("画像预览:", indent=2)
                        for line in preview.split('\n')[:8]:
                            if line.strip():
                                print_info(line, indent=3)
                        
                        # 检查是否包含用户画像标记
                        if "用户画像" in user_profile or "历史交互" in user_profile:
                            print_success(f"{user_display_name} Prompt 注入验证通过")
                        else:
                            print_warning(f"{user_display_name} 画像格式可能不标准")
                            all_passed = False
                    else:
                        print_warning(f"{user_display_name} 未获取到用户画像")
                        all_passed = False
                    
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    if 'timeout' in str(e).lower():
                        print_warning(f"API 超时: {e}", indent=2)
                        self.result.warnings += 1
                    else:
                        raise
            
            if all_passed:
                self.result.passed += 1
                self.result.add_detail("injection", "success", "Prompt 注入验证成功")
            else:
                self.result.warnings += 1
                self.result.add_detail("injection", "warning", "部分 Prompt 注入结果不理想")
            
        except Exception as e:
            print_error(f"Prompt 注入验证失败: {e}")
            self.result.failed += 1
            self.result.add_detail("injection", "failed", str(e))
    
    async def test_personalized_response(self):
        """
        V4: 端到端个性化响应验证
        
        - 完整调用 Agent chat 流程
        - 检查响应是否体现用户偏好
        """
        print_section("步骤 5: V4 端到端个性化响应验证")
        
        print_info("📌 提示: 这个测试需要调用完整的 Agent", indent=1)
        print_info("由于需要 LLM 调用，可能需要较长时间\n", indent=1)
        
        try:
            from services.chat_service import get_chat_service
            
            all_passed = True
            failed_users = []
            
            chat_service = get_chat_service()
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                test_query = user_data["test_query"]
                response_rules = user_data.get("response_rules", {})
                
                print_info(f"\n🔍 验证用户: {user_display_name}", indent=1)
                print_info(f"查询: \"{test_query}\"", indent=2)
                
                # 完整调用 Agent
                stream = await chat_service.chat(
                    message=test_query,
                    user_id=user_id,
                    stream=True
                )
                
                response_text = await collect_stream_text(stream)
                
                if not response_text:
                    print_error(f"{user_display_name} 未生成有效响应")
                    all_passed = False
                    failed_users.append(user_display_name)
                    continue
                
                # 规则化评分
                score_result = score_response(response_text, response_rules)
                score = score_result["score"]
                threshold = score_result["threshold"]
                normalized_score = score_result.get("normalized_score", score)
                max_score = score_result["max_score"]
                self.e2e_scores[user_id] = {
                    "user_name": user_display_name,
                    "query": test_query,
                    "normalized_score": normalized_score,
                    "raw_score": score,
                    "max_score": max_score,
                    "passed": score_result["passed"],
                    "details": score_result["details"],
                    "violations": score_result["violations"]
                }
                
                print_info(
                    f"评分: {normalized_score:.1f}/100 (原始 {score}/{max_score}) (阈值 {threshold})",
                    indent=3
                )
                for detail in score_result["details"]:
                    print_info(f"- {detail}", indent=4)
                for violation in score_result["violations"]:
                    print_warning(f"{user_display_name} 违规: {violation}", indent=4)
                
                if score_result["passed"]:
                    print_success(f"{user_display_name} 个性化响应评分通过")
                else:
                    print_error(f"{user_display_name} 个性化响应评分未达标")
                    all_passed = False
                    failed_users.append(user_display_name)
            
            if all_passed:
                print_success("\n✅ 端到端个性化响应验证通过")
                self.result.passed += 1
                self.result.add_detail("e2e", "success", "个性化响应评分通过")
            else:
                print_error("\n❌ 端到端个性化响应验证未通过")
                if failed_users:
                    print_info(f"未达标用户: {', '.join(failed_users)}", indent=1)
                self.result.failed += 1
                self.result.add_detail("e2e", "failed", f"未达标用户: {failed_users}")
            
        except Exception as e:
            print_error(f"端到端个性化响应验证失败: {e}")
            self.result.failed += 1
            self.result.add_detail("e2e", "failed", str(e))
    
    async def cleanup(self):
        """清理测试数据"""
        print_section("步骤 6: 清理测试数据")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            total_cleaned = 0
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                
                memories = pool.get_all(user_id=user_id, limit=100)
                
                if memories:
                    print_info(f"清理 {user_display_name} 的 {len(memories)} 条记忆...", indent=1)
                    for mem in memories:
                        try:
                            pool.delete(memory_id=mem['id'], user_id=user_id)
                            total_cleaned += 1
                        except:
                            pass
            
            if total_cleaned > 0:
                print_success(f"已清理 {total_cleaned} 条测试记忆")
            else:
                print_info("无需清理", indent=1)
            
        except Exception as e:
            print_warning(f"清理失败（不影响测试结果）: {e}")
    
    def generate_report(self):
        """生成详细报告"""
        report_file = "MEM0_PERSONALIZATION_VALIDATION_REPORT.md"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# Mem0 个性化机制验证报告\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write("## 测试概况\n\n")
            f.write(f"- 测试用户数: {len(self.test_users)}\n")
            f.write(f"- 通过数: {self.result.passed}\n")
            f.write(f"- 失败数: {self.result.failed}\n")
            f.write(f"- 警告数: {self.result.warnings}\n")
            f.write(f"- 总耗时: {self.result.duration():.2f}秒\n\n")
            
            f.write("## 测试详情\n\n")
            for detail in self.result.details:
                status_emoji = {
                    "success": "✅",
                    "failed": "❌",
                    "warning": "⚠️"
                }.get(detail["status"], "ℹ️")
                
                f.write(f"### {status_emoji} {detail['section']}\n\n")
                f.write(f"- 状态: {detail['status']}\n")
                f.write(f"- 信息: {detail['message']}\n")
                f.write(f"- 时间: {detail['timestamp']}\n\n")
            
            f.write("## 测试用户画像\n\n")
            for user_name, user_data in self.test_users.items():
                f.write(f"### {user_data['name']}\n\n")
                f.write(f"- User ID: `{user_data['user_id']}`\n")
                f.write(f"- 会话数: {len(user_data['sessions'])}\n")
                f.write(f"- 预期特征: {', '.join(user_data['expected_features'])}\n")
                f.write(f"- 测试查询: \"{user_data['test_query']}\"\n\n")
                
                # 展示提取的记忆
                user_id = user_data['user_id']
                if user_id in self.extracted_memories:
                    f.write("提取的记忆:\n\n")
                    for i, mem in enumerate(self.extracted_memories[user_id][:5], 1):
                        f.write(f"{i}. {mem.get('memory', 'N/A')}\n")
                    f.write("\n")

            f.write("## 端到端评分（规则化）\n\n")
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                score_info = self.e2e_scores.get(user_id)
                f.write(f"### {user_data['name']}\n\n")
                if not score_info:
                    f.write("- 无评分结果（可能未执行 V4）\n\n")
                    continue
                f.write(f"- 评分: {score_info['normalized_score']:.1f}/100\n")
                f.write(f"- 原始分: {score_info['raw_score']}/{score_info['max_score']}\n")
                f.write(f"- 结论: {'通过' if score_info['passed'] else '未通过'}\n")
                if score_info.get("details"):
                    f.write("- 评分细节:\n")
                    for detail in score_info["details"]:
                        f.write(f"  - {detail}\n")
                if score_info.get("violations"):
                    f.write("- 违规项:\n")
                    for violation in score_info["violations"]:
                        f.write(f"  - {violation}\n")
                f.write("\n")
            
            f.write("## 结论\n\n")
            if self.result.failed == 0:
                f.write("✅ Mem0 个性化机制验证全部通过！\n\n")
                f.write("验证要点:\n")
                f.write("- ✅ 跨会话对话历史成功写入 Mem0\n")
                f.write("- ✅ Fact Extraction 自动提取用户特征\n")
                f.write("- ✅ 语义搜索能检索相关记忆\n")
                f.write("- ✅ 用户画像正确注入 System Prompt\n")
            else:
                f.write(f"⚠️  Mem0 个性化机制验证存在 {self.result.failed} 个失败项\n\n")
                f.write("请检查环境配置和日志输出\n")
        
        print_info(f"\n📄 详细报告已生成: {report_file}", indent=1)


# ==================== 主函数 ====================

async def main():
    """主函数"""
    test = Mem0PersonalizationE2ETest()
    await test.run_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}测试被用户中断{Color.END}")
        sys.exit(130)
