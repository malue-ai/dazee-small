#!/usr/bin/env python3
"""
提示词分层功能演示测试

验证 V5.0 提示词分层功能：
1. 根据任务复杂度动态选择提示词版本
2. Simple/Medium/Complex 三个版本的差异
3. 个性化 Agent 构建
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.prompt import InstancePromptCache, TaskComplexity, detect_complexity
from logger import get_logger

logger = get_logger(__name__)


async def test_prompt_layering():
    """测试提示词分层功能"""
    
    print("=" * 80)
    print("✅ V5.0 提示词分层功能演示")
    print("=" * 80)
    print()
    
    # 1. 加载实例
    instance_name = "test_agent"
    instance_dir = Path("instances") / instance_name
    
    print(f"📂 加载实例: {instance_name}")
    print(f"   路径: {instance_dir}")
    print()
    
    # 2. 读取提示词
    prompt_file = instance_dir / "prompt.md"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        raw_prompt = f.read()
    
    print(f"📄 原始提示词: {len(raw_prompt):,} 字符")
    print()
    
    # 3. 加载 InstancePromptCache
    cache = InstancePromptCache.get_instance(instance_name)
    cache.set_cache_dir(instance_dir / ".cache")
    
    # 加载 config.yaml
    import yaml
    config_file = instance_dir / "config.yaml"
    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    print("🔄 加载 InstancePromptCache...")
    await cache.load_once(raw_prompt, config_data, force_refresh=False)
    
    print(f"✅ 缓存加载完成")
    print(f"   Simple:  {len(cache.system_prompt_simple):,} 字符")
    print(f"   Medium:  {len(cache.system_prompt_medium):,} 字符")
    print(f"   Complex: {len(cache.system_prompt_complex):,} 字符")
    print()
    
    # 4. 测试不同复杂度的查询
    test_queries = [
        ("今天天气怎么样？", TaskComplexity.SIMPLE),
        ("帮我分析一下销售数据趋势", TaskComplexity.MEDIUM),
        ("帮我设计一个完整的 ERP 系统架构", TaskComplexity.COMPLEX),
    ]
    
    print("=" * 80)
    print("🎯 测试不同复杂度查询的提示词选择")
    print("=" * 80)
    print()
    
    for query, expected_complexity in test_queries:
        print(f"📝 查询: {query}")
        
        # 检测复杂度
        complexity = detect_complexity(query, cache.prompt_schema)
        
        print(f"   检测复杂度: {complexity.value}")
        print(f"   预期复杂度: {expected_complexity.value}")
        
        # 获取对应的提示词
        system_prompt = cache.get_system_prompt(complexity)
        
        print(f"   ✅ 使用提示词: {len(system_prompt):,} 字符")
        
        # 显示提示词的前 200 字符
        print(f"   📄 提示词预览:")
        preview = system_prompt[:300].replace('\n', '\n      ')
        print(f"      {preview}")
        print("      ...")
        print()
    
    # 5. 显示三个版本的差异
    print("=" * 80)
    print("📊 提示词版本对比")
    print("=" * 80)
    print()
    
    # 提取每个版本的"当前任务模式"部分
    def extract_mode_section(prompt: str) -> str:
        if '## 当前任务模式' in prompt:
            start = prompt.find('## 当前任务模式')
            end = prompt.find('---', start + 1)
            return prompt[start:end].strip()
        return "未找到模式部分"
    
    simple_mode = extract_mode_section(cache.system_prompt_simple)
    medium_mode = extract_mode_section(cache.system_prompt_medium)
    complex_mode = extract_mode_section(cache.system_prompt_complex)
    
    print("🟢 Simple 版本动态提示:")
    print("-" * 80)
    print(simple_mode)
    print()
    
    print("🟡 Medium 版本动态提示:")
    print("-" * 80)
    print(medium_mode)
    print()
    
    print("🔴 Complex 版本动态提示:")
    print("-" * 80)
    print(complex_mode)
    print()
    
    # 6. 显示 Token 优化效果
    print("=" * 80)
    print("💰 Token 优化效果分析")
    print("=" * 80)
    print()
    
    simple_len = len(cache.system_prompt_simple)
    medium_len = len(cache.system_prompt_medium)
    complex_len = len(cache.system_prompt_complex)
    
    # 假设平均字符 Token 比例为 1:0.7（中文）
    token_ratio = 0.7
    
    print(f"📊 字符数统计:")
    print(f"   Simple:  {simple_len:,} 字符 (~{int(simple_len * token_ratio):,} tokens)")
    print(f"   Medium:  {medium_len:,} 字符 (~{int(medium_len * token_ratio):,} tokens)")
    print(f"   Complex: {complex_len:,} 字符 (~{int(complex_len * token_ratio):,} tokens)")
    print()
    
    print(f"💡 优化效果:")
    if simple_len < complex_len:
        saved_tokens = int((complex_len - simple_len) * token_ratio)
        saved_percent = ((complex_len - simple_len) / complex_len) * 100
        print(f"   Simple vs Complex: 节省 ~{saved_tokens:,} tokens ({saved_percent:.1f}%)")
    
    print()
    print("=" * 80)
    print("🎉 测试完成！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_prompt_layering())
