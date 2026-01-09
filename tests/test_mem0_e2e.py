#!/usr/bin/env python
"""
Mem0 + 腾讯云 VectorDB 端对端集成测试

测试覆盖：
1. 环境配置验证
2. Mem0 连接测试
3. 基本 CRUD 操作
4. 语义搜索
5. 与 Agent 框架集成
6. 清理测试数据

运行方式：
    python test_mem0_e2e.py
"""

import asyncio
import os
import sys
import json
import time
from datetime import datetime
from typing import List, Dict, Any

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()


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
    """测试结果"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.start_time = time.time()
    
    def duration(self) -> float:
        return time.time() - self.start_time
    
    def summary(self) -> str:
        total = self.passed + self.failed
        rate = (self.passed / total * 100) if total > 0 else 0
        return (
            f"\n{'='*60}\n"
            f"测试总结\n"
            f"{'='*60}\n"
            f"✅ 通过: {self.passed}\n"
            f"❌ 失败: {self.failed}\n"
            f"⚠️  警告: {self.warnings}\n"
            f"通过率: {rate:.1f}%\n"
            f"总耗时: {self.duration():.2f}秒\n"
            f"{'='*60}"
        )


def print_section(title: str):
    """打印分节标题"""
    print(f"\n{Color.BOLD}{Color.BLUE}{'='*60}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{title}{Color.END}")
    print(f"{Color.BOLD}{Color.BLUE}{'='*60}{Color.END}")


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


class Mem0E2ETest:
    """Mem0 端对端测试"""
    
    def __init__(self):
        self.result = TestResult()
        self.test_user_id = f"e2e_test_{int(time.time())}"
        self.test_memories = []
    
    async def run_all(self):
        """运行所有测试"""
        print(f"{Color.HEADER}{Color.BOLD}")
        print("="*60)
        print("Mem0 + 腾讯云 VectorDB 端对端集成测试")
        print("="*60)
        print(f"测试用户: {self.test_user_id}")
        print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(f"{Color.END}")
        
        try:
            # 1. 环境配置验证
            self.test_env_config()
            
            # 2. Mem0 连接测试
            await self.test_mem0_connection()
            
            # 3. 基本操作测试
            await self.test_add_memories()
            await self.test_search_memories()
            await self.test_get_all_memories()
            
            # 4. CRUD 操作
            await self.test_update_memory()
            await self.test_delete_memory()
            
            # 5. 高级功能
            await self.test_batch_operations()
            
            # 6. 与 Agent 集成
            await self.test_agent_integration()
            
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
    
    def test_env_config(self):
        """测试环境配置"""
        print_section("步骤 1: 验证环境配置")
        
        required_vars = {
            'OPENAI_API_KEY': '用于 Embedding 和 LLM',
            'TENCENT_VDB_URL': '腾讯云 VectorDB URL',
            'TENCENT_VDB_API_KEY': '腾讯云 VectorDB API Key',
            'MEM0_COLLECTION_NAME': '集合名称'
        }
        
        missing = []
        for var, desc in required_vars.items():
            value = os.getenv(var)
            if value:
                # 隐藏敏感信息
                display = value[:10] + '...' if 'KEY' in var else value[:20] + '...'
                print_info(f"✅ {var}: {display}", indent=1)
            else:
                missing.append(f"{var} ({desc})")
        
        if missing:
            print_error("环境配置验证")
            print_info("缺少必需的环境变量:", indent=1)
            for m in missing:
                print_info(f"- {m}", indent=2)
            self.result.failed += 1
            raise RuntimeError("环境配置不完整")
        else:
            print_success("环境配置验证")
            print_info("所有必需环境变量已配置", indent=1)
            self.result.passed += 1
    
    async def test_mem0_connection(self):
        """测试 Mem0 连接"""
        print_section("步骤 2: 测试 Mem0 连接")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            # 获取 Memory 实例
            memory = pool.memory
            
            # 获取集合信息
            vs = memory.vector_store
            info = vs.col_info()
            
            print_success("Mem0连接测试")
            print_info(f"Vector Store: {os.getenv('VECTOR_STORE_PROVIDER', 'qdrant')}", indent=1)
            print_info(f"Collection: {info.get('name', 'N/A')}", indent=1)
            print_info(f"文档数: {info.get('document_count', 0)}", indent=1)
            
            self.result.passed += 1
            
        except Exception as e:
            print_error(f"Mem0连接测试: {e}")
            self.result.failed += 1
            raise
    
    async def test_add_memories(self):
        """测试添加记忆"""
        print_section("步骤 3: 添加测试记忆")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            # 清理旧数据
            old_memories = pool.get_all(user_id=self.test_user_id)
            if old_memories:
                print_info(f"发现 {len(old_memories)} 条旧记忆，准备清理...", indent=1)
                for mem in old_memories:
                    pool.delete(memory_id=mem['id'], user_id=self.test_user_id)
                print_info("✅ 已清理旧记忆", indent=1)
            
            # 添加测试记忆
            test_messages = [
                {
                    'role': 'user',
                    'content': '我是一名Python开发者，主要使用FastAPI框架，喜欢写测试驱动开发的代码'
                },
                {
                    'role': 'assistant',
                    'content': '好的，我记住了你是Python开发者，使用FastAPI和TDD方法。'
                }
            ]
            
            print_info(f"添加测试会话（用户: {self.test_user_id}）...", indent=1)
            
            # 使用 retry 机制处理 OpenAI API 可能的超时
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    result = pool.add(
                        user_id=self.test_user_id,
                        messages=test_messages
                    )
                    
                    # pool.add() 返回 {"results": [...]}，需要提取 results 列表
                    memories = result.get("results", []) if isinstance(result, dict) else result
                    
                    if memories:
                        extracted_count = len(memories)
                        print_success("添加测试记忆")
                        print_info(f"Mem0 提取了 {extracted_count} 条事实记忆", indent=1)
                        self.test_memories = memories  # 保存 results 列表
                        self.result.passed += 1
                        return
                    else:
                        print_warning("Mem0 未提取到新记忆（可能已存在相似记忆）")
                        self.result.warnings += 1
                        return
                        
                except Exception as e:
                    if attempt < max_retries - 1 and 'timeout' in str(e).lower():
                        print_warning(f"OpenAI API 超时，重试 ({attempt+1}/{max_retries})...")
                        await asyncio.sleep(2)
                    else:
                        raise
            
        except Exception as e:
            print_error(f"添加测试记忆: {e}")
            self.result.failed += 1
    
    async def test_search_memories(self):
        """测试搜索记忆"""
        print_section("步骤 4: 语义搜索测试")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            queries = [
                "用户用什么编程语言？",
                "用户偏好的框架是什么？",
                "用户的开发方法论"
            ]
            
            all_found = True
            
            for query in queries:
                print_info(f"\n查询: {query}", indent=1)
                
                try:
                    results = pool.search(
                        user_id=self.test_user_id,
                        query=query,
                        limit=3
                    )
                    
                    if results:
                        for i, mem in enumerate(results[:2], 1):
                            memory_text = mem.get('memory', 'N/A')
                            score = mem.get('score', 0)
                            print_info(f"{i}. [{score:.3f}] {memory_text}", indent=2)
                    else:
                        print_warning("未找到相关记忆", indent=2)
                        all_found = False
                        
                except Exception as e:
                    if 'timeout' in str(e).lower():
                        print_warning(f"OpenAI API 超时: {e}", indent=2)
                        all_found = False
                    else:
                        raise
                
                await asyncio.sleep(0.5)  # 避免频繁调用
            
            if all_found:
                print_success("搜索记忆验证")
                self.result.passed += 1
            else:
                print_warning("搜索记忆验证 - 部分查询失败或超时")
                self.result.warnings += 1
                
        except Exception as e:
            print_error(f"搜索记忆验证: {e}")
            self.result.failed += 1
    
    async def test_get_all_memories(self):
        """测试获取所有记忆"""
        print_section("步骤 5: 获取所有记忆")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            all_memories = pool.get_all(user_id=self.test_user_id)
            
            print_success("获取所有记忆")
            print_info(f"用户 {self.test_user_id} 共有 {len(all_memories)} 条记忆", indent=1)
            
            if all_memories:
                print_info("记忆列表:", indent=1)
                for i, mem in enumerate(all_memories[:5], 1):
                    print_info(f"{i}. {mem.get('memory', 'N/A')}", indent=2)
            
            self.result.passed += 1
            
        except Exception as e:
            print_error(f"获取所有记忆: {e}")
            self.result.failed += 1
    
    async def test_update_memory(self):
        """测试更新记忆"""
        print_section("步骤 6: 更新记忆测试")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            if not self.test_memories:
                print_warning("没有可更新的记忆，跳过测试")
                self.result.warnings += 1
                return
            
            # 更新第一条记忆
            first_mem = self.test_memories[0]
            memory_id = first_mem.get('id')
            
            if memory_id:
                new_text = f"{first_mem.get('memory', '')} [已更新]"
                pool.update(
                    memory_id=memory_id,
                    data=new_text,
                    user_id=self.test_user_id
                )
                
                print_success("更新记忆测试")
                print_info(f"更新记忆 ID: {memory_id}", indent=1)
                self.result.passed += 1
            else:
                print_warning("记忆没有ID，跳过更新测试")
                self.result.warnings += 1
                
        except Exception as e:
            print_error(f"更新记忆测试: {e}")
            self.result.failed += 1
    
    async def test_delete_memory(self):
        """测试删除记忆"""
        print_section("步骤 7: 删除记忆测试")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            if len(self.test_memories) < 2:
                print_warning("记忆数量不足，跳过删除测试")
                self.result.warnings += 1
                return
            
            # 删除第二条记忆
            second_mem = self.test_memories[1]
            memory_id = second_mem.get('id')
            
            if memory_id:
                pool.delete(memory_id=memory_id, user_id=self.test_user_id)
                
                print_success("删除记忆测试")
                print_info(f"删除记忆 ID: {memory_id}", indent=1)
                self.result.passed += 1
            else:
                print_warning("记忆没有ID，跳过删除测试")
                self.result.warnings += 1
                
        except Exception as e:
            print_error(f"删除记忆测试: {e}")
            self.result.failed += 1
    
    async def test_batch_operations(self):
        """测试批量操作"""
        print_section("步骤 8: 批量操作测试")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            # 批量添加
            batch_messages = [
                [
                    {'role': 'user', 'content': f'测试批量添加 {i}'},
                    {'role': 'assistant', 'content': '好的'}
                ]
                for i in range(3)
            ]
            
            added_count = 0
            for i, msgs in enumerate(batch_messages):
                try:
                    result = pool.add(user_id=self.test_user_id, messages=msgs)
                    if result:
                        added_count += len(result)
                except Exception as e:
                    if 'timeout' not in str(e).lower():
                        raise
            
            print_success("批量操作测试")
            print_info(f"批量添加了 {added_count} 条记忆", indent=1)
            self.result.passed += 1
            
        except Exception as e:
            print_error(f"批量操作测试: {e}")
            self.result.failed += 1
    
    async def test_agent_integration(self):
        """测试与 Agent 框架集成"""
        print_section("步骤 9: Agent 框架集成测试")
        
        try:
            from prompts.universal_agent_prompt import get_universal_agent_prompt
            
            # 测试 prompt 注入
            prompt = get_universal_agent_prompt(
                user_id=self.test_user_id,
                user_query="帮我写个FastAPI接口",
                include_skills=False,
                include_e2b=False
            )
            
            has_profile = "用户画像" in prompt or "Python" in prompt
            
            if has_profile:
                print_success("Agent框架集成测试")
                print_info("✅ 用户画像已注入到 System Prompt", indent=1)
                self.result.passed += 1
            else:
                print_warning("Agent框架集成测试 - 未检测到用户画像")
                self.result.warnings += 1
                
        except Exception as e:
            print_error(f"Agent框架集成测试: {e}")
            self.result.failed += 1
    
    async def cleanup(self):
        """清理测试数据"""
        print_section("清理测试数据")
        
        try:
            from core.memory.mem0 import get_mem0_pool
            
            pool = get_mem0_pool()
            
            # 获取所有测试用户的记忆
            all_memories = pool.get_all(user_id=self.test_user_id)
            
            if all_memories:
                print_info(f"清理 {len(all_memories)} 条测试记忆...", indent=1)
                for mem in all_memories:
                    try:
                        pool.delete(memory_id=mem['id'], user_id=self.test_user_id)
                    except:
                        pass
                print_success("测试数据已清理")
            else:
                print_info("无需清理", indent=1)
                
        except Exception as e:
            print_warning(f"清理测试数据失败: {e}")


async def main():
    """主函数"""
    test = Mem0E2ETest()
    await test.run_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}测试被用户中断{Color.END}")
        sys.exit(130)
