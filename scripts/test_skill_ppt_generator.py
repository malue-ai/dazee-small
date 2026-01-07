#!/usr/bin/env python3
"""
测试 PPT Generator Custom Skill

验证流程：
1. 验证 Skill 目录结构
2. 注册 Skill 到 Claude
3. 使用 Skill 生成 PPT
4. 下载生成的 PPT 文件
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量
load_dotenv(project_root / ".env")


def validate_skill_directory(skill_path: str) -> dict:
    """
    验证 Skill 目录结构
    
    检查:
    - SKILL.md 存在
    - YAML frontmatter 有效
    - 总大小 < 8MB
    """
    result = {"valid": True, "errors": [], "warnings": [], "info": {}}
    
    skill_dir = Path(skill_path)
    
    # 检查目录存在
    if not skill_dir.exists():
        result["valid"] = False
        result["errors"].append(f"目录不存在: {skill_path}")
        return result
    
    # 检查 SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        result["valid"] = False
        result["errors"].append("SKILL.md 文件必需")
    else:
        content = skill_md.read_text(encoding='utf-8')
        
        # 检查 YAML frontmatter
        if not content.startswith("---"):
            result["valid"] = False
            result["errors"].append("SKILL.md 必须以 YAML frontmatter (---) 开始")
        else:
            try:
                end_idx = content.index("---", 3)
                frontmatter = content[3:end_idx].strip()
                
                if "name:" not in frontmatter:
                    result["valid"] = False
                    result["errors"].append("YAML frontmatter 必须包含 'name' 字段")
                
                if "description:" not in frontmatter:
                    result["valid"] = False
                    result["errors"].append("YAML frontmatter 必须包含 'description' 字段")
                
                if len(frontmatter) > 1024:
                    result["valid"] = False
                    result["errors"].append(f"YAML frontmatter 超过 1024 字符 (当前: {len(frontmatter)})")
                    
            except ValueError:
                result["valid"] = False
                result["errors"].append("无效的 YAML frontmatter 格式")
    
    # 检查总大小
    total_size = sum(f.stat().st_size for f in skill_dir.rglob("*") if f.is_file())
    result["info"]["total_size_mb"] = total_size / (1024 * 1024)
    
    if total_size > 8 * 1024 * 1024:
        result["valid"] = False
        result["errors"].append(f"总大小超过 8MB (当前: {total_size / (1024 * 1024):.2f} MB)")
    
    # 统计文件
    files = list(skill_dir.rglob("*"))
    result["info"]["file_count"] = len([f for f in files if f.is_file()])
    result["info"]["directory_count"] = len([f for f in files if f.is_dir()])
    
    # 检查 scripts 目录
    if (skill_dir / "scripts").exists():
        result["info"]["has_scripts"] = True
        result["info"]["script_files"] = [
            f.name for f in (skill_dir / "scripts").iterdir() if f.is_file()
        ]
    
    return result


def test_skill_validation():
    """测试 Skill 目录验证"""
    print("\n" + "=" * 60)
    print("🧪 Step 1: 验证 Skill 目录结构")
    print("=" * 60)
    
    skill_path = project_root / "skills" / "library" / "ppt-generator"
    result = validate_skill_directory(str(skill_path))
    
    print(f"\n📁 Skill 路径: {skill_path}")
    print(f"✅ 验证状态: {'通过' if result['valid'] else '失败'}")
    
    if result["errors"]:
        print("\n❌ 错误:")
        for error in result["errors"]:
            print(f"   - {error}")
    
    if result["warnings"]:
        print("\n⚠️ 警告:")
        for warning in result["warnings"]:
            print(f"   - {warning}")
    
    print("\n📊 信息:")
    for key, value in result["info"].items():
        print(f"   - {key}: {value}")
    
    return result["valid"], skill_path


def test_skill_registration(skill_path: Path):
    """测试 Skill 注册到 Claude"""
    print("\n" + "=" * 60)
    print("🧪 Step 2: 注册 Skill 到 Claude")
    print("=" * 60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 未找到 ANTHROPIC_API_KEY 环境变量")
        return None
    
    try:
        from anthropic import Anthropic
        from anthropic.lib import files_from_dir
        
        # 创建客户端
        client = Anthropic(api_key=api_key)
        
        print(f"\n📤 正在上传 Skill: {skill_path}")
        
        # 注册 Skill
        skill = client.beta.skills.create(
            display_title="PPT Generator",
            files=files_from_dir(str(skill_path))
        )
        
        print(f"\n✅ Skill 注册成功!")
        print(f"   - Skill ID: {skill.id}")
        print(f"   - Display Title: {skill.display_title}")
        print(f"   - Latest Version: {skill.latest_version}")
        print(f"   - Created At: {skill.created_at}")
        print(f"   - Source: {skill.source}")
        
        return skill.id, client
        
    except Exception as e:
        print(f"\n❌ Skill 注册失败: {str(e)}")
        return None, None


def test_skill_execution(skill_id: str, client, max_retries: int = 3):
    """测试 Skill 执行生成 PPT"""
    print("\n" + "=" * 60)
    print("🧪 Step 3: 使用 Skill 生成 PPT")
    print("=" * 60)
    
    if not skill_id or not client:
        print("❌ 缺少 skill_id 或 client")
        return None
    
    import time
    
    for attempt in range(max_retries):
        try:
            print(f"\n📝 发送 PPT 生成请求... (尝试 {attempt + 1}/{max_retries})")
            
            # 调用 Skill 生成 PPT
            response = client.beta.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"],
                container={
                    "skills": [
                        {"type": "custom", "skill_id": skill_id, "version": "latest"}
                    ]
                },
                tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
                messages=[{
                    "role": "user",
                    "content": """请使用 ppt-generator skill 创建一个简单的 PPT，包含：
1. 标题页：AI 技术趋势 2024
2. 内容页：3 个主要趋势
3. 结束页：谢谢观看

使用 business_blue 主题。"""
                }]
            )
            
            print(f"\n✅ Claude 响应完成!")
            print(f"   - Stop Reason: {response.stop_reason}")
            print(f"   - Content Blocks: {len(response.content)}")
            
            # 提取 file_id
            file_ids = []
            for block in response.content:
                block_type = getattr(block, 'type', 'unknown')
                
                # 打印文本内容
                if hasattr(block, 'text'):
                    print(f"\n📝 Text: {block.text[:200]}...")
                
                # 检查 code execution 结果
                if 'code_execution' in block_type or 'tool_result' in block_type:
                    print(f"\n📄 Block Type: {block_type}")
                    
                    # 递归搜索 file_id
                    def find_file_ids(obj, depth=0):
                        found = []
                        if depth > 10:  # 防止无限递归
                            return found
                        
                        if hasattr(obj, 'file_id'):
                            found.append(obj.file_id)
                        
                        if hasattr(obj, 'content'):
                            content = obj.content
                            if isinstance(content, (list, tuple)):
                                for item in content:
                                    found.extend(find_file_ids(item, depth + 1))
                            elif hasattr(content, '__dict__'):
                                found.extend(find_file_ids(content, depth + 1))
                        
                        if hasattr(obj, '__dict__'):
                            for key, value in obj.__dict__.items():
                                if key == 'file_id' and value:
                                    found.append(value)
                                elif hasattr(value, '__dict__') or isinstance(value, (list, tuple)):
                                    found.extend(find_file_ids(value, depth + 1))
                        
                        return found
                    
                    found_ids = find_file_ids(block)
                    for fid in found_ids:
                        if fid not in file_ids:
                            file_ids.append(fid)
                            print(f"   - Found file_id: {fid}")
            
            return file_ids, client, response
            
        except Exception as e:
            print(f"\n⚠️ 尝试 {attempt + 1} 失败: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避
                print(f"   等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
            else:
                print(f"\n❌ Skill 执行失败，已达最大重试次数")
                import traceback
                traceback.print_exc()
                return None, None, None
    
    return None, None, None


def test_file_download(file_ids: list, client, response=None):
    """测试下载生成的 PPT 文件"""
    print("\n" + "=" * 60)
    print("🧪 Step 4: 下载生成的 PPT 文件")
    print("=" * 60)
    
    if not file_ids:
        print("⚠️ 没有从响应中直接提取到 file_id")
        
        # 尝试列出最近的文件
        if client:
            try:
                print("\n📂 尝试从 Files API 获取最近文件...")
                files = client.beta.files.list()
                if files.data:
                    print(f"   找到 {len(files.data)} 个文件:")
                    for f in files.data[:5]:  # 只显示最近 5 个
                        print(f"   - {f.id}: {f.filename} ({f.size_bytes} bytes)")
                        if f.filename.endswith('.pptx'):
                            file_ids.append(f.id)
                else:
                    print("   没有找到文件")
            except Exception as e:
                print(f"   获取文件列表失败: {e}")
        
        if not file_ids:
            return
    
    output_dir = project_root / "outputs"
    output_dir.mkdir(exist_ok=True)
    
    for file_id in file_ids:
        try:
            print(f"\n📥 下载文件: {file_id}")
            
            # 获取文件元数据
            metadata = client.beta.files.retrieve_metadata(file_id=file_id)
            print(f"   - Filename: {metadata.filename}")
            print(f"   - Size: {metadata.size_bytes} bytes")
            print(f"   - MIME Type: {metadata.mime_type}")
            
            # 下载文件内容
            file_content = client.beta.files.download(file_id=file_id)
            
            # 保存文件
            output_path = output_dir / metadata.filename
            with open(output_path, 'wb') as f:
                f.write(file_content.read())
            
            print(f"   ✅ 文件已保存: {output_path}")
            
        except Exception as e:
            print(f"   ❌ 下载失败: {str(e)}")


def cleanup_skill(skill_id: str, client):
    """清理测试创建的 Skill"""
    print("\n" + "=" * 60)
    print("🧹 清理: 删除测试 Skill")
    print("=" * 60)
    
    if not skill_id or not client:
        return
    
    try:
        # 先删除所有版本
        versions = client.beta.skills.versions.list(skill_id=skill_id)
        for version in versions.data:
            client.beta.skills.versions.delete(skill_id=skill_id, version=version.version)
            print(f"   删除版本: {version.version}")
        
        # 再删除 Skill
        client.beta.skills.delete(skill_id)
        print(f"   ✅ Skill 已删除: {skill_id}")
        
    except Exception as e:
        print(f"   ⚠️ 清理失败: {str(e)}")


def main():
    """运行完整的 Skill 测试流程"""
    print("\n" + "=" * 60)
    print("🚀 PPT Generator Custom Skill 端到端测试")
    print("=" * 60)
    
    skill_id = None
    client = None
    
    try:
        # Step 1: 验证目录结构
        valid, skill_path = test_skill_validation()
        if not valid:
            print("\n❌ Skill 目录验证失败，请先修复错误")
            return
        
        # Step 2: 注册 Skill
        result = test_skill_registration(skill_path)
        if result and result[0]:
            skill_id, client = result
        else:
            print("\n❌ Skill 注册失败")
            return
        
        # Step 3: 执行 Skill 生成 PPT
        result = test_skill_execution(skill_id, client)
        if result and result[0] is not None:
            file_ids, _, response = result
            
            # Step 4: 下载文件
            test_file_download(file_ids, client)
        
        print("\n" + "=" * 60)
        print("✅ 端到端测试完成!")
        print("=" * 60)
        
    finally:
        # 自动清理（非交互模式）
        if skill_id and client:
            print("\n⚠️ 保留已注册的 Skill（可使用 skill_id 再次测试）")
            print(f"   Skill ID: {skill_id}")
            print("   若要删除，请运行: python scripts/test_skill_ppt_generator.py --cleanup <skill_id>")


def test_with_prebuilt_pptx():
    """
    测试使用官方 Pre-built pptx Skill（作为对比）
    """
    print("\n" + "=" * 60)
    print("🧪 对比测试: 使用官方 Pre-built pptx Skill")
    print("=" * 60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 未找到 ANTHROPIC_API_KEY 环境变量")
        return
    
    try:
        from anthropic import Anthropic
        
        client = Anthropic(api_key=api_key)
        
        print("\n📝 使用官方 pptx Skill 生成 PPT...")
        
        response = client.beta.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"],
            container={
                "skills": [
                    {"type": "anthropic", "skill_id": "pptx", "version": "latest"}
                ]
            },
            tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
            messages=[{
                "role": "user",
                "content": "创建一个简单的 PPT，包含标题页（AI 趋势 2024）、一页内容、结束页"
            }]
        )
        
        print(f"\n✅ 响应完成!")
        print(f"   - Stop Reason: {response.stop_reason}")
        
        # 提取并下载文件
        for block in response.content:
            if hasattr(block, 'text'):
                print(f"\n📝 {block.text[:300]}...")
            
            if hasattr(block, 'content') and hasattr(block.content, '__iter__'):
                for item in block.content:
                    if hasattr(item, 'file_id'):
                        file_id = item.file_id
                        print(f"\n📥 下载文件: {file_id}")
                        
                        metadata = client.beta.files.retrieve_metadata(file_id=file_id)
                        content = client.beta.files.download(file_id=file_id)
                        
                        output_dir = project_root / "outputs"
                        output_dir.mkdir(exist_ok=True)
                        output_path = output_dir / f"prebuilt_{metadata.filename}"
                        
                        with open(output_path, 'wb') as f:
                            f.write(content.read())
                        
                        print(f"   ✅ 保存: {output_path}")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()


def test_existing_skill(skill_id: str):
    """使用已注册的 Skill ID 直接测试执行"""
    print("\n" + "=" * 60)
    print(f"🧪 使用已有 Skill 测试: {skill_id}")
    print("=" * 60)
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ 未找到 ANTHROPIC_API_KEY 环境变量")
        return
    
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    
    result = test_skill_execution(skill_id, client)
    if result and result[0] is not None:
        file_ids, _, response = result
        test_file_download(file_ids, client, response)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 PPT Generator Custom Skill")
    parser.add_argument("--prebuilt", action="store_true", help="测试官方 Pre-built pptx Skill")
    parser.add_argument("--validate-only", action="store_true", help="仅验证目录结构")
    parser.add_argument("--skill-id", type=str, help="使用已有 Skill ID 直接测试")
    parser.add_argument("--cleanup", type=str, help="删除指定的 Skill")
    
    args = parser.parse_args()
    
    if args.prebuilt:
        test_with_prebuilt_pptx()
    elif args.validate_only:
        test_skill_validation()
    elif args.skill_id:
        test_existing_skill(args.skill_id)
    elif args.cleanup:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        cleanup_skill(args.cleanup, client)
    else:
        main()

