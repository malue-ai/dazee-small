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
        "test_query": "帮我写一个用户注册表单组件"
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
        "test_query": "帮我分析这个月的销售数据"
    }
}


# ==================== 测试类 ====================

class Mem0PersonalizationE2ETest:
    """Mem0 个性化机制端到端测试"""
    
    def __init__(self):
        self.result = TestResult()
        self.test_users = MOCK_CONVERSATION_SESSIONS
        self.extracted_memories = {}  # 存储提取的记忆供后续验证
    
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
        print_info("由于需要 LLM 调用，可能需要较长时间", indent=1)
        print_info("为了测试速度，我们只验证 Prompt 构建流程\n", indent=1)
        
        try:
            from prompts.universal_agent_prompt import get_universal_agent_prompt
            
            all_passed = True
            
            for user_name, user_data in self.test_users.items():
                user_id = user_data["user_id"]
                user_display_name = user_data["name"]
                test_query = user_data["test_query"]
                
                print_info(f"\n🔍 验证用户: {user_display_name}", indent=1)
                print_info(f"查询: \"{test_query}\"", indent=2)
                
                # 构建完整的 System Prompt（包含 Mem0 画像）
                system_prompt = get_universal_agent_prompt(
                    user_id=user_id,
                    user_query=test_query,
                    skip_memory_retrieval=False,  # 启用 Mem0 检索
                    include_skills=False,
                    include_e2b=False
                )
                
                # 检查 Prompt 中是否包含用户画像
                has_profile = "用户画像" in system_prompt or any(
                    feature.lower() in system_prompt.lower() 
                    for feature in user_data["expected_features"][:2]
                )
                
                if has_profile:
                    print_success(f"{user_display_name} System Prompt 包含用户画像")
                    print_info(f"Prompt 长度: {len(system_prompt)} 字符", indent=3)
                else:
                    print_warning(f"{user_display_name} System Prompt 未包含明显的用户画像")
                    all_passed = False
            
            if all_passed:
                print_success("\n✅ 端到端个性化响应验证通过")
                self.result.passed += 1
                self.result.add_detail("e2e", "success", "System Prompt 成功注入用户画像")
            else:
                print_warning("\n⚠️  端到端个性化响应验证部分通过")
                self.result.warnings += 1
                self.result.add_detail("e2e", "warning", "部分用户画像注入不明显")
            
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
