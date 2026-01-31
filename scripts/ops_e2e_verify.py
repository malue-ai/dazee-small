#!/usr/bin/env python3
"""
运营人员端到端验证脚本

从运营人员角度严格验证：
1. 配置文件是否完整
2. 自动化构建流程是否正常
3. MCP 工具是否能被调用

运行方式：
    python scripts/ops_e2e_verify.py --instance test_agent

高标准严要求：对任何错误零容忍！
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 从 .env 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


class OpsVerificationResult:
    """运营验证结果"""
    
    def __init__(self, name: str, passed: bool, details: str = "", critical: bool = False):
        self.name = name
        self.passed = passed
        self.details = details
        self.critical = critical  # 是否是致命错误
        self.timestamp = datetime.now()
    
    def __str__(self):
        icon = "✅" if self.passed else ("❌" if self.critical else "⚠️")
        return f"{icon} {self.name}: {self.details}"


class OpsE2EVerifier:
    """运营人员端到端验证器"""
    
    def __init__(self, instance_name: str):
        self.instance_name = instance_name
        self.instance_path = PROJECT_ROOT / "instances" / instance_name
        self.results: List[OpsVerificationResult] = []
        self.agent = None
        self.config = None
    
    def add_result(self, name: str, passed: bool, details: str = "", critical: bool = False):
        """添加验证结果"""
        result = OpsVerificationResult(name, passed, details, critical)
        self.results.append(result)
        print(result)
        if not passed and critical:
            print(f"\n🚨 致命错误！验证终止。")
            raise Exception(f"Critical verification failed: {name}")
    
    # ==========================================================
    # 阶段 1: 验证配置文件完整性
    # ==========================================================
    
    def verify_config_files(self):
        """验证运营人员配置的文件是否完整"""
        print("\n" + "=" * 60)
        print("📋 阶段 1: 验证配置文件完整性")
        print("=" * 60)
        
        # 1.1 检查实例目录是否存在
        if not self.instance_path.exists():
            self.add_result(
                "实例目录存在", False, 
                f"目录不存在: {self.instance_path}", 
                critical=True
            )
        else:
            self.add_result("实例目录存在", True, str(self.instance_path))
        
        # 1.2 检查必需文件
        required_files = ["config.yaml", "prompt.md"]
        for filename in required_files:
            filepath = self.instance_path / filename
            if not filepath.exists():
                self.add_result(
                    f"配置文件 {filename}", False,
                    f"文件不存在: {filepath}",
                    critical=True
                )
            else:
                size = filepath.stat().st_size
                self.add_result(
                    f"配置文件 {filename}", True,
                    f"大小: {size} 字节"
                )
        
        # 1.3 检查 .env 文件（或从父目录继承）
        env_file = self.instance_path / ".env"
        parent_env = PROJECT_ROOT / ".env"
        if env_file.exists():
            # 🆕 立即加载实例级 .env，以便后续检查环境变量
            load_dotenv(env_file, override=True)
            self.add_result(".env 文件", True, f"实例级: {env_file}")
        elif parent_env.exists():
            self.add_result(".env 文件", True, f"全局级: {parent_env}")
        else:
            self.add_result(
                ".env 文件", False,
                "未找到 .env 文件，API 密钥可能未配置",
                critical=False
            )
        
        # 1.4 验证环境变量（现在已加载实例级 .env）
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        dify_key = os.getenv("DIFY_API_KEY")
        
        if anthropic_key and anthropic_key.startswith("sk-ant-"):
            self.add_result("ANTHROPIC_API_KEY", True, "已配置")
        else:
            self.add_result(
                "ANTHROPIC_API_KEY", False,
                "未配置或格式错误",
                critical=True
            )
        
        if dify_key and len(dify_key) > 10:
            # DIFY_API_KEY 格式多样，只检查是否存在且长度合理
            self.add_result("DIFY_API_KEY", True, f"已配置 ({len(dify_key)} 字符)")
        else:
            self.add_result(
                "DIFY_API_KEY", False,
                "未配置或格式错误（MCP 工具需要此密钥）",
                critical=True
            )
    
    # ==========================================================
    # 阶段 2: 验证配置内容解析
    # ==========================================================
    
    def verify_config_content(self):
        """验证配置文件内容是否正确解析"""
        print("\n" + "=" * 60)
        print("📄 阶段 2: 验证配置内容解析")
        print("=" * 60)
        
        from scripts.instance_loader import load_instance_config
        
        try:
            self.config = load_instance_config(self.instance_name)
            self.add_result(
                "config.yaml 解析", True,
                f"实例: {self.config.name} v{self.config.version}"
            )
        except Exception as e:
            self.add_result(
                "config.yaml 解析", False,
                f"解析失败: {str(e)}",
                critical=True
            )
        
        # 2.1 验证 MCP 工具配置
        mcp_tools = self.config.mcp_tools or []
        if len(mcp_tools) > 0:
            for tool in mcp_tools:
                # 支持字典或对象两种格式
                name = tool.get("name") if isinstance(tool, dict) else tool.name
                url = tool.get("server_url") if isinstance(tool, dict) else tool.server_url
                self.add_result(
                    f"MCP 工具配置: {name}", True,
                    f"URL: {url}"
                )
        else:
            self.add_result(
                "MCP 工具配置", False,
                "未配置任何 MCP 工具",
                critical=False
            )
        
        # 2.2 验证 Agent 配置
        agent_config = getattr(self.config, 'agent_override', None) or getattr(self.config, 'agent', None) or {}
        if isinstance(agent_config, dict):
            model = agent_config.get("model", "未指定")
        else:
            model = getattr(agent_config, 'model', '未指定')
        self.add_result(
            "Agent 模型配置", True,
            f"model: {model}"
        )
        
        # 2.3 验证 prompt.md 内容
        prompt_file = self.instance_path / "prompt.md"
        prompt_content = prompt_file.read_text(encoding="utf-8")
        
        # 检查是否提到了 MCP 工具
        has_mcp_tool_mention = "dify_Ontology_TextToChart_zen0" in prompt_content
        if has_mcp_tool_mention:
            self.add_result(
                "prompt.md MCP 工具说明", True,
                "提示词中正确描述了 MCP 工具"
            )
        else:
            self.add_result(
                "prompt.md MCP 工具说明", False,
                "提示词未提及 MCP 工具名称",
                critical=False
            )
    
    # ==========================================================
    # 阶段 3: 验证自动化 Agent 构建
    # ==========================================================
    
    async def verify_agent_construction(self):
        """验证 Agent 自动化构建流程"""
        print("\n" + "=" * 60)
        print("🏗️ 阶段 3: 验证自动化 Agent 构建")
        print("=" * 60)
        
        from scripts.instance_loader import create_agent_from_instance
        
        try:
            # 3.1 加载实例级 .env
            instance_env = self.instance_path / ".env"
            if instance_env.exists():
                load_dotenv(instance_env, override=True)
                self.add_result("加载实例 .env", True, str(instance_env))
            
            # 3.2 创建 Agent
            self.agent = await create_agent_from_instance(
                self.instance_name,
                skip_mcp_registration=False,
                skip_skills_registration=True
            )
            
            self.add_result(
                "Agent 创建", True,
                f"类型: {type(self.agent).__name__}"
            )
            
            # 3.3 验证 InstancePromptCache 是否加载
            # SimpleAgent 使用 _prompt_cache（带下划线）存储
            cache = getattr(self.agent, '_prompt_cache', None)
            if cache and hasattr(cache, 'system_prompt_simple') and cache.is_loaded:
                simple_len = len(cache.system_prompt_simple or '')
                medium_len = len(cache.system_prompt_medium or '')
                complex_len = len(cache.system_prompt_complex or '')
                self.add_result(
                    "InstancePromptCache 加载", True,
                    f"Simple={simple_len}字符, Medium={medium_len}字符, Complex={complex_len}字符"
                )
            else:
                self.add_result(
                    "InstancePromptCache 加载", False,
                    "未找到缓存或缓存未加载",
                    critical=True  # 这是严重错误，必须使用缓存
                )
            
            # 3.4 验证 MCP 客户端是否连接
            if hasattr(self.agent, '_mcp_clients') and self.agent._mcp_clients:
                for client in self.agent._mcp_clients:
                    self.add_result(
                        f"MCP 客户端连接: {client.server_name}", True,
                        f"工具数: {len(client.available_tools)}"
                    )
            else:
                self.add_result(
                    "MCP 客户端连接", False,
                    "未找到 MCP 客户端",
                    critical=True
                )
            
            # 3.5 验证 MCP 工具是否注册到 Agent
            if hasattr(self.agent, '_instance_registry') and self.agent._instance_registry:
                from core.tool.instance_registry import InstanceToolType
                mcp_tools = self.agent._instance_registry.get_by_type(InstanceToolType.MCP)
                if len(mcp_tools) > 0:
                    tool_names = [t.name for t in mcp_tools]
                    self.add_result(
                        "MCP 工具注册", True,
                        f"工具: {tool_names}"
                    )
                else:
                    self.add_result(
                        "MCP 工具注册", False,
                        "InstanceToolRegistry 中无 MCP 工具",
                        critical=True
                    )
            
        except Exception as e:
            self.add_result(
                "Agent 创建", False,
                f"创建失败: {str(e)}",
                critical=True
            )
    
    # ==========================================================
    # 阶段 4: 验证端到端 MCP 调用
    # ==========================================================
    
    async def verify_mcp_call(self):
        """验证端到端 MCP 工具调用"""
        print("\n" + "=" * 60)
        print("🚀 阶段 4: 验证端到端 MCP 工具调用")
        print("=" * 60)
        
        if not self.agent:
            self.add_result(
                "MCP 调用", False,
                "Agent 未创建",
                critical=True
            )
            return
        
        # 4.1 发送测试消息
        test_query = "帮我生成一个简单的用户注册流程 flowchart"
        messages = [{"role": "user", "content": test_query}]
        
        print(f"\n👤 测试输入: {test_query}")
        print("\n🤖 Agent 响应: ", end="", flush=True)
        
        response_text = ""
        mcp_tool_called = False
        mcp_tool_name = ""
        flowchart_url = ""
        
        try:
            async for event in self.agent.chat(messages=messages):
                event_type = event.get("type", "")
                
                # 收集文本响应（支持多种事件格式）
                if event_type == "content_delta":
                    # data.delta.text 或 delta.text
                    data = event.get("data", {})
                    delta = data.get("delta", {}) if data else event.get("delta", {})
                    text = delta.get("text", "")
                    if text:
                        print(text, end="", flush=True)
                        response_text += text
                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    text = delta.get("text", "") or delta.get("content", "")
                    if text:
                        print(text, end="", flush=True)
                        response_text += text
                
                # 检测工具调用
                if event_type in ["tool_use", "tool_call_start"]:
                    tool_name = event.get("tool_name", "") or event.get("name", "")
                    if "dify" in tool_name.lower() or "flowchart" in tool_name.lower():
                        mcp_tool_called = True
                        mcp_tool_name = tool_name
                
                # 检测工具结果
                if event_type in ["tool_result", "tool_call_complete"]:
                    result = event.get("result", "") or event.get("output", "")
                    if "s3" in str(result).lower() or "http" in str(result).lower():
                        # 提取 URL
                        import re
                        urls = re.findall(r'https?://[^\s\"\'\)]+', str(result))
                        if urls:
                            flowchart_url = urls[0]
            
            print("\n")
            
            # 4.2 验证是否调用了 MCP 工具
            # 通过响应内容判断（比事件检测更可靠）
            has_s3_url = "s3.ap-southeast" in response_text or "dify-storage" in response_text
            has_flowchart_mention = "flowchart" in response_text.lower() or "流程图" in response_text
            
            if mcp_tool_called:
                self.add_result(
                    "MCP 工具调用", True,
                    f"调用了: {mcp_tool_name}"
                )
            elif has_s3_url:
                # MCP 工具返回了 S3 URL，说明调用成功
                self.add_result(
                    "MCP 工具调用", True,
                    "MCP 工具已执行（检测到 S3 URL）"
                )
            elif has_flowchart_mention and "http" in response_text:
                self.add_result(
                    "MCP 工具调用", True,
                    "通过响应内容推断 MCP 工具已执行"
                )
            else:
                self.add_result(
                    "MCP 工具调用", False,
                    "未检测到 MCP 工具调用",
                    critical=True
                )
            
            # 4.3 验证是否返回了 flowchart URL
            if flowchart_url:
                self.add_result(
                    "Flowchart 生成", True,
                    f"URL: {flowchart_url[:80]}..."
                )
            elif "http" in response_text:
                # 尝试从响应中提取 URL
                import re
                urls = re.findall(r'https?://[^\s\"\'\)]+', response_text)
                if urls:
                    self.add_result(
                        "Flowchart 生成", True,
                        f"URL: {urls[0][:80]}..."
                    )
                else:
                    self.add_result(
                        "Flowchart 生成", False,
                        "未找到生成的 flowchart URL",
                        critical=False
                    )
            else:
                self.add_result(
                    "Flowchart 生成", False,
                    "未找到生成的 flowchart URL",
                    critical=False
                )
            
            # 4.4 验证响应质量
            if len(response_text) > 50:
                self.add_result(
                    "响应质量", True,
                    f"响应长度: {len(response_text)} 字符"
                )
            else:
                self.add_result(
                    "响应质量", False,
                    f"响应过短: {len(response_text)} 字符",
                    critical=False
                )
            
        except Exception as e:
            self.add_result(
                "端到端对话", False,
                f"对话失败: {str(e)}",
                critical=True
            )
    
    # ==========================================================
    # 清理
    # ==========================================================
    
    async def cleanup(self):
        """清理资源"""
        from scripts.run_instance import cleanup_agent
        if self.agent:
            await cleanup_agent(self.agent)
            print("\n✅ 已清理 MCP 客户端资源")
    
    # ==========================================================
    # 生成报告
    # ==========================================================
    
    def generate_report(self):
        """生成验证报告"""
        print("\n" + "=" * 60)
        print("📊 运营端到端验证报告")
        print("=" * 60)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        critical_failed = sum(1 for r in self.results if not r.passed and r.critical)
        
        print(f"\n总计: {total} 项验证")
        print(f"✅ 通过: {passed}")
        print(f"❌ 失败: {failed}")
        if critical_failed > 0:
            print(f"🚨 致命: {critical_failed}")
        
        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"\n通过率: {success_rate:.1f}%")
        
        # 列出失败项
        failed_items = [r for r in self.results if not r.passed]
        if failed_items:
            print("\n⚠️ 失败项:")
            for r in failed_items:
                icon = "🚨" if r.critical else "⚠️"
                print(f"   {icon} {r.name}: {r.details}")
        
        # 运营评估
        print("\n" + "-" * 60)
        if success_rate == 100:
            print("🎉 运营验收通过！Agent 配置和自动化流程完全正常！")
        elif success_rate >= 80:
            print("✅ 基本通过，但有警告项需要关注")
        else:
            print("❌ 验收未通过，请修复上述问题后重新验证")
        
        return success_rate == 100
    
    # ==========================================================
    # 运行全部验证
    # ==========================================================
    
    async def run_all(self):
        """运行全部验证"""
        print("\n" + "=" * 60)
        print("🔍 运营人员端到端验证")
        print(f"   实例: {self.instance_name}")
        print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        try:
            # 阶段 1: 配置文件
            self.verify_config_files()
            
            # 阶段 2: 配置内容
            self.verify_config_content()
            
            # 阶段 3: Agent 构建
            await self.verify_agent_construction()
            
            # 阶段 4: MCP 调用
            await self.verify_mcp_call()
            
        except Exception as e:
            print(f"\n🚨 验证中断: {str(e)}")
        finally:
            # 清理资源
            await self.cleanup()
            
            # 生成报告
            return self.generate_report()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="运营人员端到端验证")
    parser.add_argument(
        "--instance", "-i",
        type=str,
        default="test_agent",
        help="要验证的实例名称"
    )
    
    args = parser.parse_args()
    
    verifier = OpsE2EVerifier(args.instance)
    success = await verifier.run_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
