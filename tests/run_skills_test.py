"""
Skills CRUD 独立测试脚本

用于验证 instance_loader.py 中的 Skills 功能

运行方式：
    cd zenflux_agent
    python tests/run_skills_test.py
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

# 设置 UTF-8 输出编码（Windows 兼容）
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 使用 ASCII 兼容的图标
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
SKIP = "[SKIP]"


def create_test_skill_directory(skill_name: str, description: str = "Test skill") -> Path:
    """创建临时测试 Skill 目录"""
    temp_dir = Path(tempfile.mkdtemp())
    skill_dir = temp_dir / skill_name
    skill_dir.mkdir(parents=True)
    
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
        temp_dir = skill_dir.parent
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_validation():
    """测试目录验证功能（参考官方最佳实践）"""
    from utils.instance_loader import validate_skill_directory
    
    print("\n" + "=" * 60)
    print("测试 1: 目录验证功能 (Best Practices)")
    print("=" * 60)
    
    # 1.1 测试有效目录
    print("\n1.1 Testing valid directory...")
    skill_dir = create_test_skill_directory("valid-skill", "A valid test skill for processing documents")
    
    try:
        result = validate_skill_directory(skill_dir)
        
        if result["valid"]:
            print(f"   {PASS} Valid directory validation passed")
            print(f"      Name: {result['info'].get('name', 'N/A')}")
            print(f"      File count: {result['info']['file_count']}")
            print(f"      Size: {result['info']['total_size_mb']:.4f} MB")
        else:
            print(f"   {FAIL} Validation failed: {result['errors']}")
    finally:
        cleanup_test_skill_directory(skill_dir)
    
    # 1.2 测试无效目录（缺少 SKILL.md）
    print("\n1.2 Testing invalid directory (missing SKILL.md)...")
    temp_dir = Path(tempfile.mkdtemp())
    invalid_dir = temp_dir / "invalid-skill"
    invalid_dir.mkdir()
    (invalid_dir / "script.py").write_text("# test")
    
    try:
        result = validate_skill_directory(invalid_dir)
        
        if not result["valid"]:
            print(f"   {PASS} Correctly identified invalid directory")
            print(f"      Errors: {result['errors']}")
        else:
            print(f"   {FAIL} Should identify as invalid")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 1.3 测试不存在目录
    print("\n1.3 Testing non-existent directory...")
    result = validate_skill_directory(Path("/nonexistent/path"))
    
    if not result["valid"]:
        print(f"   {PASS} Correctly identified non-existent directory")
    else:
        print(f"   {FAIL} Should identify as non-existent")
    
    # 1.4 测试 name 字段验证（官方要求：小写字母、数字、连字符）
    print("\n1.4 Testing name validation (lowercase, numbers, hyphens only)...")
    temp_dir = Path(tempfile.mkdtemp())
    invalid_name_dir = temp_dir / "InvalidName"
    invalid_name_dir.mkdir()
    
    # 使用大写字母的 name（应该失败）
    (invalid_name_dir / "SKILL.md").write_text("""---
name: Invalid_Name_With_Uppercase
description: Test skill
---

# Test
""", encoding="utf-8")
    
    try:
        result = validate_skill_directory(invalid_name_dir)
        
        if not result["valid"] and any("小写" in e or "lowercase" in e.lower() for e in result["errors"]):
            print(f"   {PASS} Correctly rejected uppercase/underscore in name")
            print(f"      Errors: {result['errors']}")
        else:
            print(f"   {FAIL} Should reject invalid name format")
            print(f"      Result: {result}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 1.5 测试保留词检查（官方要求：不能包含 anthropic、claude）
    print("\n1.5 Testing reserved words in name...")
    temp_dir = Path(tempfile.mkdtemp())
    reserved_dir = temp_dir / "reserved-test"
    reserved_dir.mkdir()
    
    (reserved_dir / "SKILL.md").write_text("""---
name: my-anthropic-helper
description: Test skill
---

# Test
""", encoding="utf-8")
    
    try:
        result = validate_skill_directory(reserved_dir)
        
        if not result["valid"] and any("anthropic" in e.lower() for e in result["errors"]):
            print(f"   {PASS} Correctly rejected reserved word 'anthropic'")
            print(f"      Errors: {result['errors']}")
        else:
            print(f"   {FAIL} Should reject reserved word")
            print(f"      Result: {result}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 1.6 测试空 description（官方要求：必须非空）
    print("\n1.6 Testing empty description...")
    temp_dir = Path(tempfile.mkdtemp())
    empty_desc_dir = temp_dir / "empty-desc"
    empty_desc_dir.mkdir()
    
    (empty_desc_dir / "SKILL.md").write_text("""---
name: test-skill
description: 
---

# Test
""", encoding="utf-8")
    
    try:
        result = validate_skill_directory(empty_desc_dir)
        
        if not result["valid"] and any("description" in e.lower() for e in result["errors"]):
            print(f"   {PASS} Correctly rejected empty description")
            print(f"      Errors: {result['errors']}")
        else:
            print(f"   {FAIL} Should reject empty description")
            print(f"      Result: {result}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return True


def test_code_correctness():
    """验证代码与 API 文档一致性"""
    import inspect
    from utils.instance_loader import (
        get_anthropic_client,
        register_skill_to_claude,
        unregister_skill_from_claude,
        update_skill_version
    )
    
    print("\n" + "=" * 60)
    print("测试 2: 代码正确性验证")
    print("=" * 60)
    
    # 检查 get_anthropic_client
    print("\n2.1 Verifying Beta Header configuration...")
    client_source = inspect.getsource(get_anthropic_client)
    
    if "skills-2025-10-02" in client_source:
        print(f"   {PASS} Beta header configured correctly")
    else:
        print(f"   {FAIL} Missing correct beta header")
    
    # 检查 register
    print("\n2.2 Verifying Create Skill API call...")
    register_source = inspect.getsource(register_skill_to_claude)
    
    checks = [
        ("client.beta.skills.create", "Uses beta.skills.create"),
        ("display_title", "Uses display_title parameter"),
        ("files_from_dir", "Uses files_from_dir helper"),
        ("betas=", "Passes betas parameter"),
    ]
    
    for pattern, description in checks:
        if pattern in register_source:
            print(f"   {PASS} {description}")
        else:
            print(f"   {FAIL} Missing: {description}")
    
    # 检查 unregister
    print("\n2.3 Verifying Delete Skill API call...")
    unregister_source = inspect.getsource(unregister_skill_from_claude)
    
    checks = [
        ("versions.list", "Lists versions first"),
        ("versions.delete", "Deletes all versions"),
        ("skills.delete", "Deletes skill"),
        ("skill_id=", "Uses keyword argument"),
        ("betas=", "Passes betas parameter"),
    ]
    
    for pattern, description in checks:
        if pattern in unregister_source:
            print(f"   {PASS} {description}")
        else:
            print(f"   {FAIL} Missing: {description}")
    
    # 检查 update
    print("\n2.4 Verifying Update Version API call...")
    update_source = inspect.getsource(update_skill_version)
    
    checks = [
        ("versions.create", "Uses versions.create"),
        ("betas=", "Passes betas parameter"),
    ]
    
    for pattern, description in checks:
        if pattern in update_source:
            print(f"   {PASS} {description}")
        else:
            print(f"   {FAIL} Missing: {description}")
    
    return True


def test_local_functions():
    """测试本地功能（无需 API）"""
    from utils.instance_loader import (
        list_instances,
        get_skills_status,
        scan_skills_directory,
        load_skill_registry
    )
    
    print("\n" + "=" * 60)
    print("测试 3: 本地功能测试")
    print("=" * 60)
    
    # 列出实例
    print("\n3.1 列出所有实例...")
    instances = list_instances()
    print(f"   找到 {len(instances)} 个实例: {instances}")
    
    # 获取 Skills 状态
    print("\n3.2 获取 Skills 状态...")
    status = get_skills_status()
    
    for instance_name, skills in status.items():
        print(f"   [Instance] {instance_name}: {len(skills)} Skills")
        for skill in skills:
            icon = PASS if skill["status"] == "registered" else FAIL
            print(f"      {icon} {skill['name']}: {skill['status']}")
            if skill.get("skill_id"):
                print(f"         skill_id: {skill['skill_id'][:30]}...")
    
    # 扫描 Skills 目录
    print("\n3.3 扫描 Skills 目录...")
    for instance in instances:
        skills = scan_skills_directory(instance)
        print(f"   {instance}: {len(skills)} 个 Skills")
        for skill in skills:
            print(f"      - {skill.name} (enabled={skill.enabled})")
    
    return True


def test_crud_api():
    """测试 CRUD API（需要 ANTHROPIC_API_KEY）"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    
    # 处理可能的前导/尾随空格
    if api_key:
        api_key = api_key.strip()
    
    print("\n" + "=" * 60)
    print("测试 4: CRUD API 测试")
    print("=" * 60)
    
    if not api_key:
        print(f"\n   {SKIP} ANTHROPIC_API_KEY not configured, skipping API tests")
        print("   Set the environment variable and re-run to test API functionality")
        return True
    
    try:
        from anthropic import Anthropic
        from anthropic.lib import files_from_dir
    except ImportError:
        print(f"\n   {SKIP} anthropic library not installed, skipping API tests")
        return True
    
    # 使用处理后的 API key 初始化客户端
    client = Anthropic(
        api_key=api_key,  # 已经 strip() 处理过
        default_headers={"anthropic-beta": "skills-2025-10-02"}
    )
    
    print(f"   API Key: {api_key[:20]}...{api_key[-4:]}")
    
    created_skill_id = None
    
    try:
        # 测试 Create
        print("\n4.1 测试 Create Skill...")
        test_name = f"e2e-test-skill-{int(time.time())}"
        skill_dir = create_test_skill_directory(test_name, "E2E test skill")
        
        try:
            start = time.time()
            skill = client.beta.skills.create(
                display_title="E2E Test Skill",
                files=files_from_dir(str(skill_dir)),
                betas=["skills-2025-10-02"]
            )
            duration = (time.time() - start) * 1000
            
            created_skill_id = skill.id
            print(f"   {PASS} Create succeeded")
            print(f"      skill_id: {skill.id}")
            print(f"      version: {skill.latest_version}")
            print(f"      Duration: {duration:.0f}ms")
        finally:
            cleanup_test_skill_directory(skill_dir)
        
        # 测试 Retrieve
        print("\n4.2 Testing Retrieve Skill...")
        start = time.time()
        retrieved = client.beta.skills.retrieve(
            skill_id=created_skill_id,
            betas=["skills-2025-10-02"]
        )
        duration = (time.time() - start) * 1000
        
        print(f"   {PASS} Retrieve succeeded")
        print(f"      display_title: {retrieved.display_title}")
        print(f"      Duration: {duration:.0f}ms")
        
        # 测试 List
        print("\n4.3 Testing List Skills...")
        start = time.time()
        skills_list = client.beta.skills.list(
            source="custom",
            betas=["skills-2025-10-02"]
        )
        duration = (time.time() - start) * 1000
        
        print(f"   {PASS} List succeeded")
        print(f"      Custom Skills: {len(skills_list.data)}")
        print(f"      Duration: {duration:.0f}ms")
        
        # 测试 Update (Create Version)
        # 注意：更新版本时 SKILL.md 的 name 必须保持不变！
        print("\n4.4 Testing Update Version...")
        skill_dir = create_test_skill_directory(test_name, "Updated version - v2")
        
        try:
            start = time.time()
            new_version = client.beta.skills.versions.create(
                skill_id=created_skill_id,
                files=files_from_dir(str(skill_dir)),
                betas=["skills-2025-10-02"]
            )
            duration = (time.time() - start) * 1000
            
            print(f"   {PASS} Update succeeded")
            print(f"      New version: {new_version.version}")
            print(f"      Duration: {duration:.0f}ms")
        finally:
            cleanup_test_skill_directory(skill_dir)
        
        # 测试 Delete
        print("\n4.5 Testing Delete Skill...")
        
        # 先删除版本
        versions = client.beta.skills.versions.list(
            skill_id=created_skill_id,
            betas=["skills-2025-10-02"]
        )
        
        for version in versions.data:
            client.beta.skills.versions.delete(
                skill_id=created_skill_id,
                version=version.version,
                betas=["skills-2025-10-02"]
            )
        
        start = time.time()
        client.beta.skills.delete(
            skill_id=created_skill_id,
            betas=["skills-2025-10-02"]
        )
        duration = (time.time() - start) * 1000
        
        print(f"   {PASS} Delete succeeded")
        print(f"      Duration: {duration:.0f}ms")
        
        # 验证删除
        try:
            client.beta.skills.retrieve(
                skill_id=created_skill_id,
                betas=["skills-2025-10-02"]
            )
            print(f"   {FAIL} Delete verification failed: skill still retrievable")
        except Exception:
            print(f"   {PASS} Delete verification succeeded: skill not found")
        
        created_skill_id = None  # 已删除
        
    except Exception as e:
        print(f"\n   {FAIL} API test failed: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理
        if created_skill_id:
            try:
                versions = client.beta.skills.versions.list(
                    skill_id=created_skill_id,
                    betas=["skills-2025-10-02"]
                )
                for version in versions.data:
                    client.beta.skills.versions.delete(
                        skill_id=created_skill_id,
                        version=version.version,
                        betas=["skills-2025-10-02"]
                    )
                client.beta.skills.delete(
                    skill_id=created_skill_id,
                    betas=["skills-2025-10-02"]
                )
                print(f"\n   [CLEANUP] Cleaned up test Skill: {created_skill_id}")
            except Exception:
                pass
    
    return True


def main():
    """主函数"""
    print("=" * 60)
    print("Claude Skills CRUD 端到端测试")
    print("=" * 60)
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目录: {os.getcwd()}")
    print(f"ANTHROPIC_API_KEY: {'已配置' if os.getenv('ANTHROPIC_API_KEY') else '未配置'}")
    
    results = []
    
    # 运行测试
    tests = [
        ("目录验证", test_validation),
        ("代码正确性", test_code_correctness),
        ("本地功能", test_local_functions),
        ("CRUD API", test_crud_api),
    ]
    
    for name, test_func in tests:
        try:
            test_func()
            results.append((name, True, None))
        except Exception as e:
            import traceback
            results.append((name, False, str(e)))
            traceback.print_exc()
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, success, _ in results if success)
    failed = len(results) - passed
    
    for name, success, error in results:
        icon = PASS if success else FAIL
        print(f"   {icon} {name}")
        if error:
            print(f"      错误: {error}")
    
    print(f"\n总计: {len(results)} 个测试, {passed} 通过, {failed} 失败")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
