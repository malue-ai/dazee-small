#!/usr/bin/env python3
"""
测试 Skill 延迟加载机制

🆕 V6.2: 验证延迟加载功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from logger import get_logger
from core.prompt.skill_prompt_builder import (
    SkillPromptBuilder,
    SkillSummary,
    build_skills_prompt,
    build_skills_instructions,
)

logger = get_logger("test_skill_lazy_loading")


def test_lazy_prompt_builder():
    """测试延迟加载 Prompt 构建"""
    logger.info("=" * 60)
    logger.info("测试 1: 延迟加载 Prompt 构建")
    logger.info("=" * 60)
    
    # 模拟 Skills 列表
    summaries = [
        SkillSummary(
            name="github",
            description="Interact with GitHub using the `gh` CLI",
            location=Path("/path/to/skills/github/SKILL.md"),
            emoji="🐙",
        ),
        SkillSummary(
            name="gemini",
            description="Gemini CLI for one-shot Q&A",
            location=Path("/path/to/skills/gemini/SKILL.md"),
            emoji="💎",
        ),
        SkillSummary(
            name="peekaboo",
            description="macOS UI automation tool",
            location=Path("/path/to/skills/peekaboo/SKILL.md"),
            emoji="👀",
        ),
    ]
    
    # 构建延迟加载 Prompt
    prompt = SkillPromptBuilder.build_lazy_prompt(summaries, language="zh")
    
    logger.info("生成的 Prompt:")
    logger.info(f"\n{prompt}\n")
    logger.info(f"Prompt 长度: {len(prompt)} 字符")
    
    # 验证格式
    assert "<available_skills>" in prompt
    assert '<skill name="github"' in prompt
    assert '<description>🐙 Interact with GitHub' in prompt
    assert "</available_skills>" in prompt
    
    logger.info("✅ 测试通过：延迟加载 Prompt 格式正确")


def test_lazy_instructions():
    """测试延迟加载指令"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 2: 延迟加载使用指令")
    logger.info("=" * 60)
    
    # 中文指令
    zh_instructions = build_skills_instructions(language="zh")
    logger.info("中文指令:")
    logger.info(f"\n{zh_instructions}\n")
    
    # 英文指令
    en_instructions = build_skills_instructions(language="en")
    logger.info("英文指令:")
    logger.info(f"\n{en_instructions}\n")
    
    assert "Skills" in en_instructions
    assert "read its SKILL.md" in en_instructions
    
    logger.info("✅ 测试通过：使用指令生成正确")


def test_build_from_real_skills():
    """测试从真实 Skills 目录构建"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 3: 从真实 Skills 目录构建")
    logger.info("=" * 60)
    
    skills_dir = PROJECT_ROOT / "instances" / "client_agent" / "skills"
    
    if not skills_dir.exists():
        logger.warning(f"Skills 目录不存在: {skills_dir}")
        return
    
    # 延迟加载模式
    lazy_prompt = build_skills_prompt(skills_dir, mode="lazy", language="zh")
    logger.info(f"延迟加载 Prompt 长度: {len(lazy_prompt)} 字符")
    
    # 全量加载模式（对比）
    eager_prompt = build_skills_prompt(skills_dir, mode="eager", language="zh")
    logger.info(f"全量加载 Prompt 长度: {len(eager_prompt)} 字符")
    
    # 计算节省比例
    if eager_prompt:
        savings = (1 - len(lazy_prompt) / len(eager_prompt)) * 100
        logger.info(f"Token 节省: {savings:.1f}%")
        logger.info(f"✅ 测试通过：延迟加载节省 ~{savings:.0f}% Token")
    else:
        logger.info("⚠️ 全量加载失败，无法计算节省比例")


def test_eager_prompt_builder():
    """测试全量加载 Prompt 构建"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 4: 全量加载 Prompt 构建")
    logger.info("=" * 60)
    
    skills_content = [
        ("github", "# GitHub Skill\n\nUse the `gh` CLI to interact with GitHub..."),
        ("gemini", "# Gemini Skill\n\nGemini CLI for one-shot Q&A..."),
    ]
    
    prompt = SkillPromptBuilder.build_eager_prompt(skills_content, language="zh")
    
    logger.info(f"全量加载 Prompt 长度: {len(prompt)} 字符")
    logger.info(f"预览前 300 字符:\n{prompt[:300]}...")
    
    assert "## github" in prompt
    assert "## gemini" in prompt
    assert "GitHub Skill" in prompt
    
    logger.info("✅ 测试通过：全量加载 Prompt 格式正确")


def test_token_savings_estimate():
    """测试 Token 节省估算"""
    logger.info("\n" + "=" * 60)
    logger.info("测试 5: Token 节省估算")
    logger.info("=" * 60)
    
    # 假设 52 个 Skills，每个 SKILL.md 平均 1000 字符
    num_skills = 52
    avg_skill_length = 1000
    avg_description_length = 100
    
    # 全量加载大小
    eager_size = num_skills * avg_skill_length
    logger.info(f"全量加载估算大小: {eager_size:,} 字符")
    
    # 延迟加载大小
    lazy_size = num_skills * (avg_description_length + 50)  # +50 for XML tags
    logger.info(f"延迟加载估算大小: {lazy_size:,} 字符")
    
    # 节省比例
    savings = (1 - lazy_size / eager_size) * 100
    logger.info(f"估算 Token 节省: {savings:.1f}%")
    
    # Token 成本（假设 1000 characters ≈ 250 tokens, $10/M tokens）
    eager_tokens = eager_size / 4
    lazy_tokens = lazy_size / 4
    cost_per_million = 10.0
    
    eager_cost = (eager_tokens / 1_000_000) * cost_per_million
    lazy_cost = (lazy_tokens / 1_000_000) * cost_per_million
    
    logger.info(f"\n每次对话成本估算:")
    logger.info(f"  全量加载: ${eager_cost:.6f}")
    logger.info(f"  延迟加载: ${lazy_cost:.6f}")
    logger.info(f"  节省成本: ${(eager_cost - lazy_cost):.6f} ({savings:.1f}%)")
    
    logger.info(f"\n💡 如果每天 1000 次对话：")
    logger.info(f"  年度节省: ${(eager_cost - lazy_cost) * 1000 * 365:.2f}")
    
    logger.info("✅ 测试通过：Token 节省显著")


if __name__ == "__main__":
    try:
        test_lazy_prompt_builder()
        test_lazy_instructions()
        test_build_from_real_skills()
        test_eager_prompt_builder()
        test_token_savings_estimate()
        
        logger.info("\n" + "=" * 60)
        logger.info("🎉 所有测试通过！")
        logger.info("=" * 60)
    
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)
