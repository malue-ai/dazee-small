#!/usr/bin/env python3
"""
E2E 验证：Skill 延迟加载机制

验证目标：
1. 系统 Prompt 中包含延迟加载格式（<available_skills>）
2. Agent 按需读取 SKILL.md（而非全量注入）
3. 实际 Token 节省效果

🆕 V6.2: 端到端验证
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger

logger = get_logger("e2e_skill_lazy_loading")


async def test_1_system_prompt_format():
    """
    测试 1：验证系统 Prompt 格式
    
    期望：
    - 包含 <available_skills> 标签
    - 不包含完整的 SKILL.md 内容
    """
    logger.info("=" * 60)
    logger.info("测试 1：验证系统 Prompt 格式")
    logger.info("=" * 60)
    
    from scripts.instance_loader import (
        load_instance_config,
        load_instance_env,
        _format_skills_for_prompt,
    )
    
    instance_name = "client_agent"
    
    # 加载配置
    load_instance_env(instance_name)
    config = load_instance_config(instance_name)
    
    # 获取加载模式配置
    skill_loading_config = config.raw_config.get("skill_loading", {})
    loading_mode = skill_loading_config.get("mode", "lazy")
    
    runtime_env_config = config.raw_config.get("runtime_environment", {})
    language = runtime_env_config.get("language", "en")
    
    logger.info(f"   加载模式: {loading_mode}")
    logger.info(f"   语言: {language}")
    
    # 获取启用的 Skills
    enabled_skills = [s for s in config.skills if s.enabled]
    logger.info(f"   启用的 Skills: {len(enabled_skills)} 个")
    
    # 构建 Skills Prompt
    skills_prompt = _format_skills_for_prompt(
        instance_name,
        enabled_skills,
        loading_mode=loading_mode,
        language=language,
    )
    
    # 验证格式
    has_available_skills = "<available_skills>" in skills_prompt
    has_skill_location = 'location="' in skills_prompt
    has_skill_description = "<description>" in skills_prompt
    
    # 检查是否包含完整 SKILL.md 内容（不应该包含）
    has_full_content = "---\nname:" in skills_prompt  # frontmatter 格式
    
    logger.info(f"\n验证结果：")
    logger.info(f"   ✓ 包含 <available_skills>: {has_available_skills}")
    logger.info(f"   ✓ 包含 location 属性: {has_skill_location}")
    logger.info(f"   ✓ 包含 <description>: {has_skill_description}")
    logger.info(f"   ✓ 不包含完整 SKILL.md: {not has_full_content}")
    logger.info(f"   Prompt 长度: {len(skills_prompt):,} 字符")
    
    # 显示预览
    logger.info(f"\n预览（前 800 字符）：")
    logger.info("-" * 60)
    logger.info(skills_prompt[:800])
    logger.info("...")
    
    # 断言
    assert has_available_skills, "应包含 <available_skills> 标签"
    assert has_skill_location, "应包含 location 属性"
    assert has_skill_description, "应包含 <description> 标签"
    assert not has_full_content, "不应包含完整 SKILL.md 内容（frontmatter）"
    
    logger.info("\n✅ 测试 1 通过：系统 Prompt 格式正确（延迟加载）")
    
    return skills_prompt


async def test_2_token_savings():
    """
    测试 2：验证 Token 节省效果
    
    对比延迟加载 vs 全量加载的 Prompt 大小
    """
    logger.info("\n" + "=" * 60)
    logger.info("测试 2：验证 Token 节省效果")
    logger.info("=" * 60)
    
    from scripts.instance_loader import (
        load_instance_config,
        load_instance_env,
        _format_skills_for_prompt,
    )
    
    instance_name = "client_agent"
    
    # 加载配置
    load_instance_env(instance_name)
    config = load_instance_config(instance_name)
    enabled_skills = [s for s in config.skills if s.enabled]
    
    # 延迟加载模式
    lazy_prompt = _format_skills_for_prompt(
        instance_name,
        enabled_skills,
        loading_mode="lazy",
        language="en",
    )
    
    # 全量加载模式
    eager_prompt = _format_skills_for_prompt(
        instance_name,
        enabled_skills,
        loading_mode="eager",
        language="en",
    )
    
    # 计算节省
    lazy_size = len(lazy_prompt)
    eager_size = len(eager_prompt)
    savings_pct = (1 - lazy_size / eager_size) * 100 if eager_size > 0 else 0
    
    # Token 估算（约 4 字符 = 1 token）
    lazy_tokens = lazy_size / 4
    eager_tokens = eager_size / 4
    
    logger.info(f"\n对比结果：")
    logger.info(f"   延迟加载: {lazy_size:,} 字符 (~{lazy_tokens:,.0f} tokens)")
    logger.info(f"   全量加载: {eager_size:,} 字符 (~{eager_tokens:,.0f} tokens)")
    logger.info(f"   节省: {savings_pct:.1f}%")
    
    # 成本估算（Claude 3.5 Sonnet: $3/M input tokens）
    cost_per_million = 3.0
    lazy_cost = (lazy_tokens / 1_000_000) * cost_per_million
    eager_cost = (eager_tokens / 1_000_000) * cost_per_million
    savings_per_call = eager_cost - lazy_cost
    
    logger.info(f"\n成本估算（每次对话）：")
    logger.info(f"   延迟加载: ${lazy_cost:.4f}")
    logger.info(f"   全量加载: ${eager_cost:.4f}")
    logger.info(f"   每次节省: ${savings_per_call:.4f}")
    
    # 年度节省（假设每天 1000 次）
    daily_savings = savings_per_call * 1000
    yearly_savings = daily_savings * 365
    logger.info(f"\n年度节省（1000 次/天）：${yearly_savings:,.2f}")
    
    # 断言
    assert savings_pct >= 80, f"Token 节省应 >= 80%，实际 {savings_pct:.1f}%"
    
    logger.info("\n✅ 测试 2 通过：Token 节省显著")
    
    return {
        "lazy_size": lazy_size,
        "eager_size": eager_size,
        "savings_pct": savings_pct,
        "yearly_savings": yearly_savings,
    }


async def test_3_skill_location_valid():
    """
    测试 3：验证 Skill location 路径有效
    
    确保 Agent 可以通过 Read 工具读取 SKILL.md
    """
    logger.info("\n" + "=" * 60)
    logger.info("测试 3：验证 Skill location 路径有效")
    logger.info("=" * 60)
    
    import re
    from scripts.instance_loader import (
        load_instance_config,
        load_instance_env,
        _format_skills_for_prompt,
    )
    
    instance_name = "client_agent"
    
    # 加载配置
    load_instance_env(instance_name)
    config = load_instance_config(instance_name)
    enabled_skills = [s for s in config.skills if s.enabled]
    
    # 构建延迟加载 Prompt
    lazy_prompt = _format_skills_for_prompt(
        instance_name,
        enabled_skills,
        loading_mode="lazy",
        language="en",
    )
    
    # 提取所有 location 路径
    locations = re.findall(r'location="([^"]+)"', lazy_prompt)
    
    logger.info(f"   找到 {len(locations)} 个 Skill locations")
    
    # 验证每个路径
    valid_count = 0
    invalid_paths = []
    
    for location in locations:
        path = Path(location)
        if path.exists() and path.is_file():
            valid_count += 1
        else:
            invalid_paths.append(location)
    
    logger.info(f"   有效路径: {valid_count}/{len(locations)}")
    
    if invalid_paths:
        logger.warning(f"   无效路径:")
        for p in invalid_paths[:5]:  # 只显示前 5 个
            logger.warning(f"      - {p}")
    
    # 测试读取一个 SKILL.md
    if locations:
        sample_path = Path(locations[0])
        if sample_path.exists():
            content = sample_path.read_text(encoding="utf-8")
            logger.info(f"\n示例 SKILL.md 读取测试：")
            logger.info(f"   路径: {sample_path}")
            logger.info(f"   大小: {len(content):,} 字符")
            logger.info(f"   内容预览: {content[:200]}...")
    
    # 断言
    assert valid_count == len(locations), f"所有路径应有效，无效: {len(invalid_paths)}"
    
    logger.info("\n✅ 测试 3 通过：所有 Skill location 路径有效")
    
    return {
        "total_locations": len(locations),
        "valid_count": valid_count,
    }


async def test_4_config_integration():
    """
    测试 4：验证配置集成正确
    
    确保从 config.yaml 读取 skill_loading 配置
    """
    logger.info("\n" + "=" * 60)
    logger.info("测试 4：验证配置集成正确")
    logger.info("=" * 60)
    
    import yaml
    
    config_path = PROJECT_ROOT / "instances" / "client_agent" / "config.yaml"
    
    with open(config_path) as f:
        raw_config = yaml.safe_load(f)
    
    # 检查配置项
    skill_loading = raw_config.get("skill_loading", {})
    dep_check = raw_config.get("skill_dependency_check", {})
    runtime_env = raw_config.get("runtime_environment", {})
    
    logger.info(f"\n配置验证：")
    logger.info(f"   skill_loading.mode: {skill_loading.get('mode', '未配置')}")
    logger.info(f"   skill_dependency_check.enabled: {dep_check.get('enabled', '未配置')}")
    logger.info(f"   skill_dependency_check.mode: {dep_check.get('mode', '未配置')}")
    logger.info(f"   runtime_environment.language: {runtime_env.get('language', '未配置')}")
    
    # 断言配置存在
    assert "mode" in skill_loading, "skill_loading.mode 应存在"
    assert "enabled" in dep_check, "skill_dependency_check.enabled 应存在"
    assert "language" in runtime_env, "runtime_environment.language 应存在"
    
    logger.info("\n✅ 测试 4 通过：配置集成正确")
    
    return {
        "skill_loading_mode": skill_loading.get("mode"),
        "dep_check_enabled": dep_check.get("enabled"),
        "language": runtime_env.get("language"),
    }


async def main():
    """运行所有 E2E 测试"""
    logger.info("🚀 开始 E2E 验证：Skill 延迟加载机制")
    logger.info("=" * 60)
    
    results = {}
    
    try:
        # 测试 1: 系统 Prompt 格式
        await test_1_system_prompt_format()
        results["test_1"] = "✅ 通过"
        
        # 测试 2: Token 节省
        savings = await test_2_token_savings()
        results["test_2"] = f"✅ 通过 (节省 {savings['savings_pct']:.1f}%)"
        
        # 测试 3: location 路径有效
        locations = await test_3_skill_location_valid()
        results["test_3"] = f"✅ 通过 ({locations['valid_count']} 个有效路径)"
        
        # 测试 4: 配置集成
        config_result = await test_4_config_integration()
        results["test_4"] = f"✅ 通过 (mode={config_result['skill_loading_mode']})"
        
        # 汇总
        logger.info("\n" + "=" * 60)
        logger.info("📊 E2E 验证汇总")
        logger.info("=" * 60)
        
        for test_name, result in results.items():
            logger.info(f"   {test_name}: {result}")
        
        logger.info("\n" + "=" * 60)
        logger.info("🎉 所有 E2E 测试通过！延迟加载机制工作正常")
        logger.info("=" * 60)
        
        # 输出关键指标
        logger.info("\n📈 关键指标：")
        logger.info(f"   Token 节省: {savings['savings_pct']:.1f}%")
        logger.info(f"   年度成本节省: ${savings['yearly_savings']:,.2f}")
        logger.info(f"   有效 Skill 路径: {locations['valid_count']} 个")
        
    except AssertionError as e:
        logger.error(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 测试异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
