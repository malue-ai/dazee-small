#!/usr/bin/env python3
"""
环境变量诊断脚本

检查 .env 文件和环境变量配置
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

print("="*70)
print("🔍 环境变量诊断")
print("="*70)

# 查找 .env 文件
env_paths = [
    Path.cwd() / ".env",
    Path.cwd().parent / ".env",
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent.parent / ".env",
]

print("\n1️⃣ 查找 .env 文件:")
found_env = None
for env_path in env_paths:
    exists = env_path.exists()
    print(f"  {'✅' if exists else '❌'} {env_path}")
    if exists and not found_env:
        found_env = env_path

if found_env:
    print(f"\n✅ 找到 .env 文件: {found_env}")
    
    # 加载
    print("\n2️⃣ 加载环境变量:")
    loaded = load_dotenv(found_env, override=True)
    print(f"  load_dotenv() 返回: {loaded}")
    
    # 读取文件内容（只显示 key 名，不显示值）
    print("\n3️⃣ .env 文件内容（key列表）:")
    with open(found_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key = line.split('=')[0]
                value_preview = line.split('=')[1][:10] if len(line.split('=')) > 1 else ""
                print(f"  • {key} = {value_preview}...")
    
    # 检查关键 API Keys
    print("\n4️⃣ 检查关键 API Keys:")
    keys_to_check = [
        "E2B_API_KEY",
        "ANTHROPIC_API_KEY",
        "EXA_API_KEY",
        "SLIDESPEAK_API_KEY"
    ]
    
    for key in keys_to_check:
        value = os.getenv(key)
        if value:
            print(f"  ✅ {key}: {value[:15]}...")
        else:
            print(f"  ❌ {key}: 未设置")
    
    print("\n" + "="*70)
    
    # 检查必需的 keys
    e2b_key = os.getenv("E2B_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    if e2b_key and anthropic_key:
        print("✅ 所有必需的 API Keys 已配置")
        print("\n可以运行测试:")
        print("  python tests/test_vibe_coding_real.py")
    else:
        print("❌ 缺少必需的 API Keys")
        if not e2b_key:
            print("\n请在 .env 文件中添加:")
            print("  E2B_API_KEY=e2b_你的key")
        if not anthropic_key:
            print("\n请在 .env 文件中添加:")
            print("  ANTHROPIC_API_KEY=sk-ant-你的key")
else:
    print("\n❌ 未找到 .env 文件")
    print("\n请创建 .env 文件并添加:")
    print("  E2B_API_KEY=e2b_你的key")
    print("  ANTHROPIC_API_KEY=sk-ant-你的key")

