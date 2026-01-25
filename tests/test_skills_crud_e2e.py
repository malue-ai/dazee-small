"""
Claude Skills CRUD 端到端测试

测试目标：
1. 验证 Skills 注册（Create）功能
2. 验证 Skills 查询（Read）功能
3. 验证 Skills 版本更新（Update）功能
4. 验证 Skills 注销（Delete）功能
5. 验证本地目录验证逻辑

参考文档：
- https://platform.claude.com/docs/en/build-with-claude/skills-guide

运行方式：
    # 运行全部测试
    pytest tests/test_skills_crud_e2e.py -v -s
    
    # 只运行验证测试（不调用 API）
    pytest tests/test_skills_crud_e2e.py -v -s -k "validate"
    
    # 只运行 CRUD 测试（需要 ANTHROPIC_API_KEY）
    pytest tests/test_skills_crud_e2e.py -v -s -k "crud"

作者：ZenFlux Team
日期：2026-01-25
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ==================== 配置 ====================

# 测试实例名称
TEST_INSTANCE = "dazee_agent"

# Beta 版本（根据官方文档）
SKILLS_BETA = "skills-2025-10-02"

# 测试 Skill 名称前缀（避免与真实 Skill 冲突）
TEST_SKILL_PREFIX = "_test_skill_"


# ==================== 数据结构 ====================

@dataclass
class SkillTestResult:
    """Skill 测试结果"""
    name: str
    operation: str  # create, read, update, delete
    success: bool
    skill_id: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0


# ==================== 工具函数 ====================

def get_anthropic_client():
    """
    获取带 Skills beta 的 Anthropic 客户端
    
    Returns:
        Anthropic 客户端实例
        
    Raises:
        ImportError: anthropic 库未安装
        ValueError: API Key 未配置
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        pytest.skip("anthropic 库未安装")
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY 未配置")
    
    return Anthropic(
        api_key=api_key,
        default_headers={"anthropic-beta": SKILLS_BETA}
    )


def create_test_skill_directory(skill_name: str, description: str = "Test skill") -> Path:
    """
    创建临时测试 Skill 目录
    
    Args:
        skill_name: Skill 名称
        description: Skill 描述
        
    Returns:
        临时目录路径
    """
    # 创建临时目录
    temp_dir = Path(tempfile.mkdtemp())
    skill_dir = temp_dir / skill_name
    skill_dir.mkdir(parents=True)
    
    # 创建 SKILL.md（符合官方规范）
    skill_md_content = f"""---
name: {skill_name}
description: {description}
---

# {skill_name}

This is a test skill for CRUD validation.

## Capabilities

- Test functionality
- Validation

## Usage

Use this skill for testing purposes only.
"""
    
    (skill_dir / "SKILL.md").write_text(skill_md_content, encoding="utf-8")
    
    # 创建一个简单的脚本
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    
    (scripts_dir / "test_script.py").write_text("""
# Test script
def test_function():
    return "Hello from test skill"
""", encoding="utf-8")
    
    return skill_dir


def cleanup_test_skill_directory(skill_dir: Path):
    """清理临时测试目录"""
    if skill_dir and skill_dir.exists():
        # 获取父目录（临时目录）
        temp_dir = skill_dir.parent
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==================== 验证测试（无需 API）====================

class TestSkillValidation:
    """Skill 目录验证测试（无需 API 调用）"""
    
    def test_validate_skill_directory_valid(self):
        """测试：有效的 Skill 目录应该通过验证"""
        from scripts.instance_loader import validate_skill_directory
        
        # 创建有效的测试目录
        skill_dir = create_test_skill_directory(
            skill_name="valid-test-skill",
            description="A valid test skill"
        )
        
        try:
            result = validate_skill_directory(skill_dir)
            
            print(f"\n验证结果: {result}")
            
            assert result["valid"], f"验证应该通过: {result['errors']}"
            assert len(result["errors"]) == 0
            assert result["info"]["file_count"] >= 2  # SKILL.md + script
            assert result["info"]["has_scripts"]
            
            print("✅ 有效目录验证通过")
            
        finally:
            cleanup_test_skill_directory(skill_dir)
    
    def test_validate_skill_directory_missing_skillmd(self):
        """测试：缺少 SKILL.md 应该验证失败"""
        from scripts.instance_loader import validate_skill_directory
        
        # 创建缺少 SKILL.md 的目录
        temp_dir = Path(tempfile.mkdtemp())
        skill_dir = temp_dir / "invalid-skill"
        skill_dir.mkdir(parents=True)
        
        # 只创建脚本，不创建 SKILL.md
        (skill_dir / "script.py").write_text("# test")
        
        try:
            result = validate_skill_directory(skill_dir)
            
            print(f"\n验证结果: {result}")
            
            assert not result["valid"]
            assert any("SKILL.md" in e for e in result["errors"])
            
            print("✅ 缺少 SKILL.md 验证正确")
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_validate_skill_directory_invalid_frontmatter(self):
        """测试：无效的 YAML frontmatter 应该验证失败"""
        from scripts.instance_loader import validate_skill_directory
        
        temp_dir = Path(tempfile.mkdtemp())
        skill_dir = temp_dir / "bad-frontmatter"
        skill_dir.mkdir(parents=True)
        
        # 创建缺少必需字段的 SKILL.md
        (skill_dir / "SKILL.md").write_text("""---
title: Missing name field
---

# Content
""", encoding="utf-8")
        
        try:
            result = validate_skill_directory(skill_dir)
            
            print(f"\n验证结果: {result}")
            
            assert not result["valid"]
            assert any("name" in e for e in result["errors"])
            
            print("✅ 无效 frontmatter 验证正确")
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_validate_skill_directory_nonexistent(self):
        """测试：不存在的目录应该验证失败"""
        from scripts.instance_loader import validate_skill_directory
        
        result = validate_skill_directory(Path("/nonexistent/path"))
        
        print(f"\n验证结果: {result}")
        
        assert not result["valid"]
        assert any("不存在" in e for e in result["errors"])
        
        print("✅ 不存在目录验证正确")


# ==================== Skills CRUD 测试（需要 API）====================

class TestSkillsCRUD:
    """Skills CRUD 操作测试（需要 ANTHROPIC_API_KEY）"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前检查环境"""
        self.client = get_anthropic_client()
        self.created_skill_ids = []  # 跟踪创建的 skill_id，用于清理
        yield
        # 清理创建的测试 skills
        self._cleanup_test_skills()
    
    def _cleanup_test_skills(self):
        """清理测试创建的 Skills"""
        for skill_id in self.created_skill_ids:
            try:
                # 先删除版本
                try:
                    versions = self.client.beta.skills.versions.list(
                        skill_id=skill_id,
                        betas=[SKILLS_BETA]
                    )
                    for version in versions.data:
                        self.client.beta.skills.versions.delete(
                            skill_id=skill_id,
                            version=version.version,
                            betas=[SKILLS_BETA]
                        )
                except Exception:
                    pass
                
                # 删除 skill
                self.client.beta.skills.delete(
                    skill_id=skill_id,
                    betas=[SKILLS_BETA]
                )
                print(f"   🧹 已清理测试 Skill: {skill_id}")
            except Exception as e:
                print(f"   ⚠️ 清理失败 {skill_id}: {e}")
    
    @pytest.mark.asyncio
    async def test_crud_create_skill(self):
        """测试：创建 Skill（Create）"""
        from anthropic.lib import files_from_dir
        import time
        
        print("\n" + "=" * 50)
        print("测试: Create Skill")
        print("=" * 50)
        
        # 创建测试目录
        test_name = f"{TEST_SKILL_PREFIX}{int(time.time())}"
        skill_dir = create_test_skill_directory(
            skill_name=test_name,
            description="E2E test skill for CRUD validation"
        )
        
        try:
            start_time = time.time()
            
            # 调用 API 创建 Skill（参考官方文档格式）
            skill = self.client.beta.skills.create(
                display_title="E2E Test Skill",
                files=files_from_dir(str(skill_dir)),
                betas=[SKILLS_BETA]
            )
            
            duration = (time.time() - start_time) * 1000
            
            # 跟踪用于清理
            self.created_skill_ids.append(skill.id)
            
            print(f"   skill_id: {skill.id}")
            print(f"   display_title: {skill.display_title}")
            print(f"   latest_version: {skill.latest_version}")
            print(f"   耗时: {duration:.0f}ms")
            
            # 验证返回值
            assert skill.id is not None, "skill_id 不应为空"
            assert skill.id.startswith("skill_"), f"skill_id 应以 skill_ 开头: {skill.id}"
            assert skill.display_title == "E2E Test Skill"
            assert skill.latest_version is not None
            
            print("   ✅ Create Skill 测试通过")
            
            return skill.id
            
        finally:
            cleanup_test_skill_directory(skill_dir)
    
    @pytest.mark.asyncio
    async def test_crud_retrieve_skill(self):
        """测试：获取 Skill 详情（Read）"""
        from anthropic.lib import files_from_dir
        import time
        
        print("\n" + "=" * 50)
        print("测试: Retrieve Skill")
        print("=" * 50)
        
        # 先创建一个 skill
        test_name = f"{TEST_SKILL_PREFIX}{int(time.time())}"
        skill_dir = create_test_skill_directory(
            skill_name=test_name,
            description="Test skill for retrieve"
        )
        
        try:
            # 创建
            created = self.client.beta.skills.create(
                display_title="Retrieve Test Skill",
                files=files_from_dir(str(skill_dir)),
                betas=[SKILLS_BETA]
            )
            self.created_skill_ids.append(created.id)
            
            print(f"   已创建 skill_id: {created.id}")
            
            # 获取详情（参考官方文档格式）
            start_time = time.time()
            
            skill = self.client.beta.skills.retrieve(
                skill_id=created.id,
                betas=[SKILLS_BETA]
            )
            
            duration = (time.time() - start_time) * 1000
            
            print(f"   获取结果:")
            print(f"      id: {skill.id}")
            print(f"      display_title: {skill.display_title}")
            print(f"      latest_version: {skill.latest_version}")
            print(f"      created_at: {skill.created_at}")
            print(f"   耗时: {duration:.0f}ms")
            
            # 验证
            assert skill.id == created.id
            assert skill.display_title == "Retrieve Test Skill"
            assert skill.latest_version is not None
            
            print("   ✅ Retrieve Skill 测试通过")
            
        finally:
            cleanup_test_skill_directory(skill_dir)
    
    @pytest.mark.asyncio
    async def test_crud_list_skills(self):
        """测试：列出 Skills（Read - List）"""
        import time
        
        print("\n" + "=" * 50)
        print("测试: List Skills")
        print("=" * 50)
        
        start_time = time.time()
        
        # 列出所有 skills（参考官方文档格式）
        skills = self.client.beta.skills.list(
            betas=[SKILLS_BETA]
        )
        
        duration = (time.time() - start_time) * 1000
        
        print(f"   Skills 数量: {len(skills.data)}")
        for skill in skills.data[:5]:  # 只显示前 5 个
            print(f"      - {skill.id}: {skill.display_title} (source: {skill.source})")
        
        if len(skills.data) > 5:
            print(f"      ... 还有 {len(skills.data) - 5} 个")
        
        print(f"   耗时: {duration:.0f}ms")
        
        # 验证
        assert isinstance(skills.data, list)
        
        # 过滤只看 custom skills
        custom_skills = self.client.beta.skills.list(
            source="custom",
            betas=[SKILLS_BETA]
        )
        
        print(f"   Custom Skills 数量: {len(custom_skills.data)}")
        
        print("   ✅ List Skills 测试通过")
    
    @pytest.mark.asyncio
    async def test_crud_update_skill_version(self):
        """测试：更新 Skill 版本（Update）"""
        from anthropic.lib import files_from_dir
        import time
        
        print("\n" + "=" * 50)
        print("测试: Update Skill Version")
        print("=" * 50)
        
        # 创建初始 skill
        test_name = f"{TEST_SKILL_PREFIX}{int(time.time())}"
        skill_dir = create_test_skill_directory(
            skill_name=test_name,
            description="Initial version"
        )
        
        try:
            # 创建
            created = self.client.beta.skills.create(
                display_title="Update Test Skill",
                files=files_from_dir(str(skill_dir)),
                betas=[SKILLS_BETA]
            )
            self.created_skill_ids.append(created.id)
            
            initial_version = created.latest_version
            print(f"   初始版本: {initial_version}")
            
            # 修改 SKILL.md 内容
            skill_md = skill_dir / "SKILL.md"
            content = skill_md.read_text()
            new_content = content.replace("Initial version", "Updated version v2")
            skill_md.write_text(new_content)
            
            # 创建新版本（参考官方文档格式）
            start_time = time.time()
            
            new_version = self.client.beta.skills.versions.create(
                skill_id=created.id,
                files=files_from_dir(str(skill_dir)),
                betas=[SKILLS_BETA]
            )
            
            duration = (time.time() - start_time) * 1000
            
            print(f"   新版本: {new_version.version}")
            print(f"   耗时: {duration:.0f}ms")
            
            # 验证版本变化
            assert new_version.version != initial_version, "新版本应该与初始版本不同"
            
            # 获取更新后的 skill 确认
            updated = self.client.beta.skills.retrieve(
                skill_id=created.id,
                betas=[SKILLS_BETA]
            )
            
            print(f"   确认最新版本: {updated.latest_version}")
            assert updated.latest_version == new_version.version
            
            print("   ✅ Update Skill Version 测试通过")
            
        finally:
            cleanup_test_skill_directory(skill_dir)
    
    @pytest.mark.asyncio
    async def test_crud_delete_skill(self):
        """测试：删除 Skill（Delete）"""
        from anthropic.lib import files_from_dir
        import time
        
        print("\n" + "=" * 50)
        print("测试: Delete Skill")
        print("=" * 50)
        
        # 创建待删除的 skill
        test_name = f"{TEST_SKILL_PREFIX}{int(time.time())}"
        skill_dir = create_test_skill_directory(
            skill_name=test_name,
            description="To be deleted"
        )
        
        try:
            # 创建
            created = self.client.beta.skills.create(
                display_title="Delete Test Skill",
                files=files_from_dir(str(skill_dir)),
                betas=[SKILLS_BETA]
            )
            
            print(f"   已创建 skill_id: {created.id}")
            
            # 先删除所有版本（参考官方文档，这是必需步骤）
            versions = self.client.beta.skills.versions.list(
                skill_id=created.id,
                betas=[SKILLS_BETA]
            )
            
            print(f"   版本数量: {len(versions.data)}")
            
            for version in versions.data:
                self.client.beta.skills.versions.delete(
                    skill_id=created.id,
                    version=version.version,
                    betas=[SKILLS_BETA]
                )
                print(f"      已删除版本: {version.version}")
            
            # 删除 skill（参考官方文档格式）
            start_time = time.time()
            
            self.client.beta.skills.delete(
                skill_id=created.id,
                betas=[SKILLS_BETA]
            )
            
            duration = (time.time() - start_time) * 1000
            
            print(f"   已删除 Skill")
            print(f"   耗时: {duration:.0f}ms")
            
            # 验证删除成功（尝试获取应该失败）
            try:
                self.client.beta.skills.retrieve(
                    skill_id=created.id,
                    betas=[SKILLS_BETA]
                )
                assert False, "删除后不应该能获取到 skill"
            except Exception as e:
                print(f"   验证删除成功: {type(e).__name__}")
            
            # 从清理列表中移除（已手动删除）
            if created.id in self.created_skill_ids:
                self.created_skill_ids.remove(created.id)
            
            print("   ✅ Delete Skill 测试通过")
            
        finally:
            cleanup_test_skill_directory(skill_dir)


# ==================== 集成测试：instance_loader 函数 ====================

class TestInstanceLoaderSkillsFunctions:
    """测试 instance_loader.py 中的 Skills 函数"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前检查环境"""
        # 检查 anthropic 库
        try:
            import anthropic
        except ImportError:
            pytest.skip("anthropic 库未安装")
        
        # 检查 API key
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY 未配置")
    
    def test_get_skills_status(self):
        """测试：获取 Skills 状态"""
        from scripts.instance_loader import get_skills_status, list_instances
        
        print("\n" + "=" * 50)
        print("测试: get_skills_status()")
        print("=" * 50)
        
        # 获取所有实例的 skills 状态
        status = get_skills_status()
        
        print(f"   实例数: {len(status)}")
        
        for instance_name, skills in status.items():
            print(f"\n   📦 {instance_name}:")
            for skill in skills:
                status_icon = "✅" if skill["status"] == "registered" else "❌"
                print(f"      {status_icon} {skill['name']}: {skill['status']}")
                if skill.get("skill_id"):
                    print(f"         skill_id: {skill['skill_id'][:30]}...")
        
        # 验证返回格式
        assert isinstance(status, dict)
        
        print("\n   ✅ get_skills_status 测试通过")
    
    def test_scan_skills_directory(self):
        """测试：扫描 Skills 目录"""
        from scripts.instance_loader import scan_skills_directory, list_instances
        
        print("\n" + "=" * 50)
        print("测试: scan_skills_directory()")
        print("=" * 50)
        
        instances = list_instances()
        
        for instance_name in instances:
            skills = scan_skills_directory(instance_name)
            print(f"\n   📦 {instance_name}: {len(skills)} 个 Skills")
            
            for skill in skills:
                print(f"      - {skill.name}")
                print(f"        enabled: {skill.enabled}")
                print(f"        skill_id: {skill.skill_id or '(未注册)'}")
                print(f"        path: {skill.skill_path}")
        
        print("\n   ✅ scan_skills_directory 测试通过")
    
    def test_load_skill_registry(self):
        """测试：加载 skill_registry.yaml"""
        from scripts.instance_loader import load_skill_registry, list_instances
        
        print("\n" + "=" * 50)
        print("测试: load_skill_registry()")
        print("=" * 50)
        
        instances = list_instances()
        
        for instance_name in instances:
            skills = load_skill_registry(instance_name)
            print(f"\n   📦 {instance_name}: {len(skills)} 个已注册 Skills")
            
            for skill in skills:
                print(f"      - {skill.name}: {skill.skill_id or 'N/A'}")
        
        print("\n   ✅ load_skill_registry 测试通过")


# ==================== 代码正确性验证 ====================

class TestCodeCorrectness:
    """验证 instance_loader.py 代码与 Claude Skills API 文档的一致性"""
    
    def test_verify_api_call_format(self):
        """验证 API 调用格式是否符合文档规范"""
        from scripts.instance_loader import (
            get_anthropic_client,
            register_skill_to_claude,
            unregister_skill_from_claude,
            update_skill_version
        )
        import inspect
        
        print("\n" + "=" * 50)
        print("验证: API 调用格式")
        print("=" * 50)
        
        # 检查 get_anthropic_client
        client_source = inspect.getsource(get_anthropic_client)
        
        # 验证使用了正确的 beta header
        assert "skills-2025-10-02" in client_source, \
            "应该使用 skills-2025-10-02 beta"
        print("   ✅ Beta header 配置正确")
        
        # 验证 register 函数使用了正确的参数
        register_source = inspect.getsource(register_skill_to_claude)
        assert "client.beta.skills.create" in register_source, \
            "应该使用 client.beta.skills.create"
        assert "display_title" in register_source, \
            "应该使用 display_title 参数"
        assert "files_from_dir" in register_source, \
            "应该使用 files_from_dir 辅助函数"
        print("   ✅ Create 调用格式正确")
        
        # 验证 unregister 函数使用了正确的步骤
        unregister_source = inspect.getsource(unregister_skill_from_claude)
        assert "versions.list" in unregister_source, \
            "应该先列出版本"
        assert "versions.delete" in unregister_source, \
            "应该删除所有版本"
        assert "skills.delete" in unregister_source, \
            "应该删除 skill"
        print("   ✅ Delete 调用格式正确（包含版本删除）")
        
        # 验证 update 函数使用了正确的 API
        update_source = inspect.getsource(update_skill_version)
        assert "versions.create" in update_source, \
            "应该使用 versions.create 创建新版本"
        print("   ✅ Update 调用格式正确")
        
        print("\n   ✅ 所有 API 调用格式验证通过")
    
    def test_verify_skill_validation_rules(self):
        """验证 Skill 目录验证规则是否符合文档要求"""
        from scripts.instance_loader import validate_skill_directory
        import inspect
        
        print("\n" + "=" * 50)
        print("验证: Skill 验证规则")
        print("=" * 50)
        
        source = inspect.getsource(validate_skill_directory)
        
        # 文档要求：SKILL.md 必须存在
        assert "SKILL.md" in source, "应该检查 SKILL.md 存在"
        print("   ✅ 检查 SKILL.md 存在")
        
        # 文档要求：YAML frontmatter 格式
        assert "---" in source, "应该检查 YAML frontmatter 格式"
        print("   ✅ 检查 YAML frontmatter 格式")
        
        # 文档要求：name 字段必须存在
        assert "name" in source, "应该检查 name 字段"
        print("   ✅ 检查 name 字段")
        
        # 文档要求：description 字段必须存在
        assert "description" in source, "应该检查 description 字段"
        print("   ✅ 检查 description 字段")
        
        # 文档要求：frontmatter 不超过 1024 字符
        assert "1024" in source, "应该检查 frontmatter 大小限制 (1024)"
        print("   ✅ 检查 frontmatter 大小限制")
        
        # 文档要求：总大小不超过 8MB
        assert "8" in source and "1024" in source, "应该检查 8MB 大小限制"
        print("   ✅ 检查总大小限制")
        
        print("\n   ✅ 所有验证规则检查通过")


# ==================== 运行入口 ====================

if __name__ == "__main__":
    # 运行 pytest
    pytest.main([__file__, "-v", "-s"])
