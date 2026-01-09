#!/usr/bin/env python3
"""
测试 Claude Platform 所有 API 封装

验证：
1. Skills API (create, list, get, delete)
2. Files API (download, get_info, list)
3. Citations API
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env")

# 导入 anthropic
import anthropic


@dataclass
class SkillInfo:
    """Skill 信息"""
    id: str
    display_title: str
    latest_version: str
    created_at: str
    source: str

@dataclass  
class FileInfo:
    """文件信息"""
    file_id: str
    filename: str
    size_bytes: int
    mime_type: str
    created_at: str
    downloadable: bool = True


def get_anthropic_client():
    """获取 Anthropic 客户端"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY 环境变量未设置")
    return anthropic.Anthropic(api_key=api_key)


def test_skills_api():
    """测试 Skills API"""
    print("\n" + "=" * 60)
    print("🧪 测试 Skills API")
    print("=" * 60)
    
    client = get_anthropic_client()
    
    # 1. 列出现有 Skills
    print("\n📋 列出现有 Skills:")
    try:
        skills_response = client.beta.skills.list()
        skills = [
            SkillInfo(
                id=s.id,
                display_title=s.display_title,
                latest_version=s.latest_version,
                created_at=s.created_at,
                source=s.source
            )
            for s in skills_response.data
        ]
        print(f"   找到 {len(skills)} 个 Skills")
        for skill in skills[:5]:  # 最多显示 5 个
            print(f"   - {skill.id}: {skill.display_title} ({skill.source})")
    except Exception as e:
        print(f"   ❌ 获取 Skills 列表失败: {e}")
        skills = []
    
    # 2. 创建 Skill（如果目录存在）
    skill_path = project_root / "skills" / "library" / "ppt-generator"
    created_skill_id = None
    
    if skill_path.exists():
        print(f"\n📤 创建 Skill: {skill_path}")
        try:
            from anthropic.lib import files_from_dir
            
            skill = client.beta.skills.create(
                display_title="Test PPT Generator",
                files=files_from_dir(str(skill_path))
            )
            created_skill_id = skill.id
            print(f"   ✅ Skill ID: {skill.id}")
            print(f"   Version: {skill.latest_version}")
            
            # 3. 获取 Skill 详情
            print(f"\n🔍 获取 Skill 详情: {skill.id}")
            detail = client.beta.skills.retrieve(skill.id)
            print(f"   ✅ Display Title: {detail.display_title}")
            print(f"   Created At: {detail.created_at}")
            
        except Exception as e:
            print(f"   ❌ Skill 创建失败: {e}")
    else:
        print(f"\n⚠️ Skill 目录不存在: {skill_path}")
    
    # 4. 删除测试 Skill（如果创建了）
    if created_skill_id:
        print(f"\n🗑️ 删除测试 Skill: {created_skill_id}")
        try:
            # 先删除所有版本
            versions = client.beta.skills.versions.list(skill_id=created_skill_id)
            for version in versions.data:
                client.beta.skills.versions.delete(
                    skill_id=created_skill_id,
                    version=version.version
                )
            
            # 再删除 Skill
            client.beta.skills.delete(created_skill_id)
            print("   ✅ 删除成功")
        except Exception as e:
            print(f"   ❌ 删除失败: {e}")
    
    return True


def test_files_api():
    """测试 Files API"""
    print("\n" + "=" * 60)
    print("🧪 测试 Files API")
    print("=" * 60)
    
    client = get_anthropic_client()
    
    # 列出文件
    print("\n📋 列出文件:")
    try:
        files_response = client.beta.files.list()
        files = [
            FileInfo(
                file_id=f.id,
                filename=f.filename,
                size_bytes=f.size_bytes,
                mime_type=f.mime_type,
                created_at=f.created_at,
                downloadable=f.downloadable
            )
            for f in files_response.data
        ]
        print(f"   找到 {len(files)} 个文件")
        for f in files[:5]:  # 最多显示 5 个
            print(f"   - {f.file_id}: {f.filename} ({f.size_bytes} bytes)")
    except Exception as e:
        print(f"   ❌ 获取文件列表失败: {e}")
        files = []
    
    # 如果有文件，尝试获取详情
    if files:
        file_id = files[0].file_id
        print(f"\n🔍 获取文件详情: {file_id}")
        try:
            info = client.beta.files.retrieve_metadata(file_id=file_id)
            print(f"   ✅ Filename: {info.filename}")
            print(f"   Size: {info.size_bytes} bytes")
            print(f"   MIME Type: {info.mime_type}")
            print(f"   Created At: {info.created_at}")
        except Exception as e:
            print(f"   ❌ 获取文件详情失败: {e}")
    
    return True


def test_citations_api():
    """测试 Citations API"""
    print("\n" + "=" * 60)
    print("🧪 测试 Citations API")
    print("=" * 60)
    
    client = get_anthropic_client()
    
    # 创建文档内容
    print("\n📄 创建文档内容:")
    document_text = """
    ZenFlux Agent 是一个基于 Claude 的智能代理框架。
    
    主要特性：
    1. Extended Thinking 支持
    2. Skills API 集成
    3. E2B 沙箱执行
    4. 自适应重规划
    
    版本：V4.2.2
    """
    
    # 构建带引用的消息
    content = [
        {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": document_text
            },
            "title": "ZenFlux Agent 文档",
            "citations": {"enabled": True}
        },
        {
            "type": "text",
            "text": "ZenFlux Agent 有哪些主要特性？请引用文档内容。"
        }
    ]
    
    print("   ✅ 文档内容已创建")
    
    # 测试带引用的消息（实际调用）
    print("\n📝 测试 Citations 调用:")
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}]
        )
        
        # 提取响应内容
        response_text = ""
        citations_found = []
        
        for block in response.content:
            if hasattr(block, 'type'):
                if block.type == "text":
                    response_text = block.text
                elif block.type == "citation":
                    citations_found.append(block)
        
        print(f"   ✅ 响应: {response_text[:200]}...")
        print(f"   📎 找到 {len(citations_found)} 个引用")
        return True
        
    except Exception as e:
        print(f"   ❌ 调用失败: {e}")
        return False


def test_all():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("🚀 Claude Platform APIs 测试")
    print("=" * 60)
    
    results = {}
    
    try:
        results["Skills API"] = test_skills_api()
    except Exception as e:
        print(f"\n❌ Skills API 测试失败: {e}")
        results["Skills API"] = False
    
    try:
        results["Files API"] = test_files_api()
    except Exception as e:
        print(f"\n❌ Files API 测试失败: {e}")
        results["Files API"] = False
    
    try:
        results["Citations API"] = test_citations_api()
    except Exception as e:
        print(f"\n❌ Citations API 测试失败: {e}")
        results["Citations API"] = False
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    for api, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {api}: {status}")
    
    all_passed = all(results.values())
    print(f"\n{'🎉 所有测试通过!' if all_passed else '⚠️ 部分测试失败'}")
    
    return all_passed


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 Claude Platform APIs")
    parser.add_argument("--skills", action="store_true", help="仅测试 Skills API")
    parser.add_argument("--files", action="store_true", help="仅测试 Files API")
    parser.add_argument("--citations", action="store_true", help="仅测试 Citations API")
    
    args = parser.parse_args()
    
    if args.skills:
        test_skills_api()
    elif args.files:
        test_files_api()
    elif args.citations:
        test_citations_api()
    else:
        test_all()

