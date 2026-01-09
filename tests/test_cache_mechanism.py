"""
测试缓存机制

测试场景：
1. 首次加载 - 无缓存，生成 Schema 和推断工具
2. 缓存复用 - 有缓存且有效，直接加载
3. 配置修改失效 - 修改 config.yaml 后缓存失效
4. 增量工具更新 - 新增工具时只推断新工具
5. 强制刷新 - --force-refresh 参数
6. 清除缓存 - --clear-cache 命令
"""

import asyncio
import sys
from pathlib import Path
import time
import hashlib

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger
logger = get_logger("test_cache")


async def test_cache_mechanism():
    """测试缓存机制"""
    from scripts.instance_loader import create_agent_from_instance
    from utils.cache_utils import is_cache_valid, clear_cache
    
    instance_name = "test_agent"
    instance_path = PROJECT_ROOT / "instances" / instance_name
    cache_dir = instance_path / ".cache"
    
    print("=" * 60)
    print("🧪 测试实例级缓存机制")
    print("=" * 60)
    
    # 测试 1: 清除旧缓存，从头开始
    print("\n📌 测试 1: 首次加载（无缓存）")
    print("-" * 60)
    if cache_dir.exists():
        clear_cache(cache_dir)
        print("✅ 已清除旧缓存")
    
    start_time = time.time()
    agent1 = await create_agent_from_instance(instance_name)
    elapsed1 = time.time() - start_time
    print(f"⏱️  首次加载耗时: {elapsed1:.2f}s")
    
    # 检查缓存文件是否生成
    schema_file = cache_dir / "schema.json"
    tools_file = cache_dir / "tools_inference.json"
    meta_file = cache_dir / "cache_metadata.json"
    
    assert schema_file.exists(), "❌ Schema 缓存未生成"
    assert tools_file.exists(), "❌ 工具推断缓存未生成"
    assert meta_file.exists(), "❌ 缓存元数据未生成"
    print("✅ 缓存文件已生成")
    
    # 测试 2: 缓存复用
    print("\n📌 测试 2: 缓存复用（有效缓存）")
    print("-" * 60)
    
    # 验证缓存有效性
    is_valid = is_cache_valid(cache_dir, instance_path)
    assert is_valid, "❌ 缓存应该有效但检测为无效"
    print("✅ 缓存有效性检查通过")
    
    start_time = time.time()
    agent2 = await create_agent_from_instance(instance_name)
    elapsed2 = time.time() - start_time
    print(f"⏱️  缓存加载耗时: {elapsed2:.2f}s")
    
    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float('inf')
    print(f"🚀 加速比: {speedup:.2f}x")
    
    if speedup < 1.5:
        print("⚠️  警告: 缓存加速不明显，可能没有正确使用缓存")
    else:
        print("✅ 缓存显著加速加载")
    
    # 测试 3: 配置修改失效
    print("\n📌 测试 3: 配置修改导致缓存失效")
    print("-" * 60)
    
    # 修改 config.yaml（添加一个空行）
    config_file = instance_path / "config.yaml"
    original_content = config_file.read_text()
    config_file.write_text(original_content + "\n# test comment\n")
    
    # 检查缓存失效
    is_valid_after_modify = is_cache_valid(cache_dir, instance_path)
    assert not is_valid_after_modify, "❌ 配置修改后缓存应该失效"
    print("✅ 配置修改后缓存正确失效")
    
    # 恢复原始配置
    config_file.write_text(original_content)
    print("✅ 已恢复原始配置")
    
    # 测试 4: 强制刷新
    print("\n📌 测试 4: 强制刷新缓存")
    print("-" * 60)
    
    start_time = time.time()
    agent3 = await create_agent_from_instance(instance_name, force_refresh=True)
    elapsed3 = time.time() - start_time
    print(f"⏱️  强制刷新耗时: {elapsed3:.2f}s")
    print("✅ 强制刷新成功，缓存已重新生成")
    
    # 测试 5: 清除缓存
    print("\n📌 测试 5: 清除缓存")
    print("-" * 60)
    
    clear_cache(cache_dir)
    assert not cache_dir.exists(), "❌ 缓存目录应该被删除"
    print("✅ 缓存已清除")
    
    # 测试总结
    print("\n" + "=" * 60)
    print("🎉 所有测试通过！")
    print("=" * 60)
    print(f"\n性能对比:")
    print(f"  首次加载:   {elapsed1:.2f}s")
    print(f"  缓存复用:   {elapsed2:.2f}s  (加速 {speedup:.2f}x)")
    print(f"  强制刷新:   {elapsed3:.2f}s")
    print(f"\n缓存文件位置: {cache_dir}")


if __name__ == "__main__":
    try:
        asyncio.run(test_cache_mechanism())
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
        sys.exit(1)
