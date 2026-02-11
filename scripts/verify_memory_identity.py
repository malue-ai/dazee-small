#!/usr/bin/env python3
"""
End-to-end cross-session memory identity verification.

Tests the full pipeline:
  1. FragmentExtractor (DeepSeek LLM) extracts identity from conversation
  2. InstanceMemoryManager stores to MEMORY.md + FTS5
  3. UserMemoryInjector recalls and injects into new session context

Usage:
    python scripts/verify_memory_identity.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


async def main():
    # ── Setup: load instance env + LLM profiles ──
    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / "instances" / "xiaodazi" / ".env"
    load_dotenv(env_path)
    print(f"✓ Loaded .env from {env_path}")

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("✗ DEEPSEEK_API_KEY not set")
        sys.exit(1)
    print(f"✓ DEEPSEEK_API_KEY present ({api_key[:8]}...)")

    # Load LLM profiles (instance_loader normally does this at startup)
    import yaml

    profiles_path = (
        PROJECT_ROOT / "instances" / "xiaodazi" / "config" / "llm_profiles.yaml"
    )
    with open(profiles_path) as f:
        profiles_raw = yaml.safe_load(f)

    # Resolve profiles using deepseek provider
    from utils.instance_loader import _resolve_llm_profiles

    provider_templates = profiles_raw.get("provider_templates", {})
    raw_profiles = profiles_raw.get("llm_profiles", {})
    resolved = _resolve_llm_profiles("deepseek", provider_templates, raw_profiles)

    from config.llm_config import set_instance_profiles

    set_instance_profiles(resolved)
    print(f"✓ LLM profiles loaded: {list(resolved.keys())}")

    fe_profile = resolved.get("fragment_extractor", {})
    print(
        f"  fragment_extractor → provider={fe_profile.get('provider')}, "
        f"model={fe_profile.get('model')}"
    )

    # ── Use temp dir for clean test (no interference with real data) ──
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        memory_dir = tmpdir / "memory"
        memory_dir.mkdir()
        store_dir = tmpdir / "store"
        store_dir.mkdir()

        print("\n" + "=" * 60)
        print("STEP 1: Extract identity from conversation (DeepSeek LLM)")
        print("=" * 60)

        # Simulate a conversation where user reveals identity
        conversation = [
            {"role": "user", "content": "你好，叫我良哥就行"},
            {
                "role": "assistant",
                "content": "好的良哥！有什么我可以帮你的吗？",
            },
            {
                "role": "user",
                "content": "我在做一个AI产品叫焗基律动，帮我看看这个方案",
            },
            {
                "role": "assistant",
                "content": "好的良哥，我来帮你看看焗基律动的方案。",
            },
        ]

        from core.memory.instance_memory import InstanceMemoryManager

        mgr = InstanceMemoryManager(
            base_dir=memory_dir,
            user_id="test_user",
            mem0_enabled=False,  # Skip Mem0 vector layer for speed
            enabled=True,
        )

        # Extract + store (this calls DeepSeek LLM)
        print("  Calling FragmentExtractor with DeepSeek...")
        await mgr.flush(session_id="test-session-001", messages=conversation)

        # Read back MEMORY.md
        content = await mgr.get_memory_context()
        print(f"\n  MEMORY.md ({len(content)} chars):")
        for line in content.split("\n"):
            if line.strip() and not line.startswith(">"):
                print(f"    {line}")

        # ── Verify identity was extracted ──
        has_name = "良哥" in content
        identity_section = "基本信息" in content
        # Count total entries to verify noise-free extraction
        import re as _re
        total_entries = len(_re.findall(r"^\s*-\s+(?!\（)", content, _re.MULTILINE))

        print(f"\n  ✓ 包含「良哥」: {has_name}")
        print(f"  ✓ 有「基本信息」section: {identity_section}")
        print(f"  ✓ 总条目数: {total_entries} (应 ≤ 5, 无噪音)")

        print("\n" + "=" * 60)
        print("STEP 2: Simulate new session — verify memory injection")
        print("=" * 60)

        # Simulate UserMemoryInjector reading MEMORY.md
        from core.context.injectors.phase2.user_memory import UserMemoryInjector

        injector = UserMemoryInjector()

        trimmed = injector._trim_markdown_memory(content, max_chars=1500)
        print(f"\n  Injected context ({len(trimmed)} chars, budget=1500):")
        for line in trimmed.split("\n"):
            if line.strip():
                print(f"    {line}")

        # Verify identity survives injection budget
        inject_has_name = "良哥" in trimmed
        print(f"\n  ✓ 注入后包含「良哥」: {inject_has_name}")

        print("\n" + "=" * 60)
        print("STEP 3: Dedup verification")
        print("=" * 60)

        # Flush again with same conversation — dedup should prevent duplicates
        await mgr.flush(session_id="test-session-002", messages=conversation)
        content_after = await mgr.get_memory_context()

        # Count occurrences
        count_before = content.count("良哥")
        count_after = content_after.count("良哥")

        # LLM-driven content may use slightly different wording across calls,
        # so exact dedup won't always catch rephrased duplicates.
        # Acceptable: count grows by at most 1 per flush (not N).
        dedup_ok = count_after <= count_before + 1
        print(f"  「良哥」出现次数: flush前={count_before}, flush后={count_after}")
        print(f"  ✓ 去重可控: {dedup_ok} (增长 ≤ 1, LLM 措辞变化属正常)")

        # ── Final verdict ──
        print("\n" + "=" * 60)
        noise_free = total_entries <= 5
        all_pass = all([
            has_name,
            identity_section,
            noise_free,
            inject_has_name,
            dedup_ok,
        ])
        if all_pass:
            print("✅ ALL CHECKS PASSED — 跨会话记忆身份提取验证通过")
        else:
            print("❌ SOME CHECKS FAILED")
            if not has_name:
                print("   → 提取未捕获「良哥」")
            if not identity_section:
                print("   → MEMORY.md 缺少「基本信息」section")
            if not noise_free:
                print(f"   → 噪音过多: {total_entries} 条 (应 ≤ 5)")
            if not inject_has_name:
                print("   → 注入预算截断丢失「良哥」")
            if not dedup_ok:
                print(f"   → 去重失控: {count_before} → {count_after} (增长 > 1)")
        print("=" * 60)

        sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    asyncio.run(main())
