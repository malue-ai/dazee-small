"""
术语重构验证测试

验证 Skill → Interface 术语重构是否完整：
- Interface: 本地工作流接口（interfaces/library/）
- Claude Skills: 上传到 Anthropic 服务器的技能（完全独立机制）

注意：这些测试不依赖项目的复杂模块，只验证目录结构和文件存在性
"""

import pytest
from pathlib import Path
import os

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


class TestDirectoryStructure:
    """验证目录结构重构"""
    
    def test_interfaces_library_exists(self):
        """interfaces/library/ 目录应该存在"""
        interfaces_dir = PROJECT_ROOT / "interfaces" / "library"
        assert interfaces_dir.exists(), f"目录不存在: {interfaces_dir}"
    
    def test_old_skills_library_not_exists(self):
        """旧的 skills/library/ 目录应该不存在"""
        old_dir = PROJECT_ROOT / "skills" / "library"
        assert not old_dir.exists(), f"旧目录仍然存在: {old_dir}"
    
    def test_interface_md_files_exist(self):
        """每个接口目录应该有 INTERFACE.md 文件"""
        interfaces_dir = PROJECT_ROOT / "interfaces" / "library"
        interface_dirs = [d for d in interfaces_dir.iterdir() 
                         if d.is_dir() and not d.name.startswith('_')]
        
        assert len(interface_dirs) > 0, "应该至少有一个接口目录"
        
        for interface_dir in interface_dirs:
            interface_md = interface_dir / "INTERFACE.md"
            assert interface_md.exists(), f"缺少 INTERFACE.md: {interface_dir}"
    
    def test_no_skill_md_files(self):
        """不应该存在 SKILL.md 文件"""
        interfaces_dir = PROJECT_ROOT / "interfaces" / "library"
        
        for interface_dir in interfaces_dir.iterdir():
            if interface_dir.is_dir():
                skill_md = interface_dir / "SKILL.md"
                assert not skill_md.exists(), f"旧的 SKILL.md 仍然存在: {skill_md}"


class TestFileRenaming:
    """验证文件重命名"""
    
    def test_interface_loader_exists(self):
        """interface_loader.py 应该存在"""
        file_path = PROJECT_ROOT / "core" / "tool" / "capability" / "interface_loader.py"
        assert file_path.exists(), f"文件不存在: {file_path}"
    
    def test_old_skill_loader_not_exists(self):
        """旧的 skill_loader.py 不应该存在"""
        file_path = PROJECT_ROOT / "core" / "tool" / "capability" / "skill_loader.py"
        assert not file_path.exists(), f"旧文件仍然存在: {file_path}"
    
    def test_interface_memory_exists(self):
        """interface.py 应该存在于 memory/system/"""
        file_path = PROJECT_ROOT / "core" / "memory" / "system" / "interface.py"
        assert file_path.exists(), f"文件不存在: {file_path}"
    
    def test_old_skill_memory_not_exists(self):
        """旧的 skill.py 不应该存在于 memory/system/"""
        file_path = PROJECT_ROOT / "core" / "memory" / "system" / "skill.py"
        assert not file_path.exists(), f"旧文件仍然存在: {file_path}"
    
    def test_interfaces_loader_exists(self):
        """interfaces_loader.py 应该存在于 prompts/"""
        file_path = PROJECT_ROOT / "prompts" / "interfaces_loader.py"
        assert file_path.exists(), f"文件不存在: {file_path}"
    
    def test_old_skills_loader_not_exists(self):
        """旧的 skills_loader.py 不应该存在于 prompts/"""
        file_path = PROJECT_ROOT / "prompts" / "skills_loader.py"
        assert not file_path.exists(), f"旧文件仍然存在: {file_path}"


class TestFileContentTerminology:
    """验证文件内容中的术语"""
    
    def test_interface_loader_has_correct_class_name(self):
        """interface_loader.py 应该有 InterfaceLoader 类"""
        file_path = PROJECT_ROOT / "core" / "tool" / "capability" / "interface_loader.py"
        content = file_path.read_text()
        
        assert "class InterfaceLoader" in content, "应该有 InterfaceLoader 类"
        assert "class InterfaceInfo" in content, "应该有 InterfaceInfo 类"
    
    def test_interface_memory_has_correct_class_name(self):
        """interface.py 应该有 InterfaceMemory 类"""
        file_path = PROJECT_ROOT / "core" / "memory" / "system" / "interface.py"
        content = file_path.read_text()
        
        assert "class InterfaceMemory" in content, "应该有 InterfaceMemory 类"
    
    def test_interfaces_loader_no_prebuilt_skills(self):
        """interfaces_loader.py 不应该有 PREBUILT_CLAUDE_SKILLS"""
        file_path = PROJECT_ROOT / "prompts" / "interfaces_loader.py"
        content = file_path.read_text()
        
        assert "PREBUILT_CLAUDE_SKILLS" not in content, \
            "interfaces_loader.py 不应该包含 PREBUILT_CLAUDE_SKILLS"


class TestClaudeSkillsIndependence:
    """验证 Claude Skills 与 Interfaces 完全独立"""
    
    def test_routers_skills_has_prebuilt_claude_skills(self):
        """routers/skills.py 应该有 PREBUILT_CLAUDE_SKILLS"""
        file_path = PROJECT_ROOT / "routers" / "skills.py"
        content = file_path.read_text()
        
        assert "PREBUILT_CLAUDE_SKILLS" in content, \
            "routers/skills.py 应该包含 PREBUILT_CLAUDE_SKILLS"
    
    def test_claude_skill_info_preserved(self):
        """core/llm/claude.py 中的 SkillInfo 应该保留"""
        file_path = PROJECT_ROOT / "core" / "llm" / "claude.py"
        content = file_path.read_text()
        
        # Claude API 的 SkillInfo 应该保留
        assert "class SkillInfo" in content, \
            "core/llm/claude.py 应该保留 SkillInfo 类（用于 Claude API）"


class TestInitFiles:
    """验证 __init__.py 文件的导出"""
    
    def test_capability_init_exports_interface_loader(self):
        """capability/__init__.py 应该导出 InterfaceLoader"""
        file_path = PROJECT_ROOT / "core" / "tool" / "capability" / "__init__.py"
        content = file_path.read_text()
        
        assert "InterfaceLoader" in content, "应该导出 InterfaceLoader"
        assert "InterfaceInfo" in content, "应该导出 InterfaceInfo"
        assert "create_interface_loader" in content, "应该导出 create_interface_loader"
    
    def test_system_init_exports_interface_memory(self):
        """system/__init__.py 应该导出 InterfaceMemory"""
        file_path = PROJECT_ROOT / "core" / "memory" / "system" / "__init__.py"
        content = file_path.read_text()
        
        assert "InterfaceMemory" in content, "应该导出 InterfaceMemory"
        assert "create_interface_memory" in content, "应该导出 create_interface_memory"


class TestRulesFiles:
    """验证规则文件"""
    
    def test_interfaces_development_rule_exists(self):
        """06-interfaces-development 规则应该存在"""
        rule_dir = PROJECT_ROOT / ".cursor" / "rules" / "06-interfaces-development"
        assert rule_dir.exists(), f"规则目录不存在: {rule_dir}"
    
    def test_old_skills_development_rule_not_exists(self):
        """旧的 06-skills-development 规则不应该存在"""
        rule_dir = PROJECT_ROOT / ".cursor" / "rules" / "06-skills-development"
        assert not rule_dir.exists(), f"旧规则目录仍然存在: {rule_dir}"


class TestInterfaceCount:
    """验证接口数量"""
    
    def test_all_interfaces_discovered(self):
        """应该发现所有接口"""
        interfaces_dir = PROJECT_ROOT / "interfaces" / "library"
        interface_dirs = [d for d in interfaces_dir.iterdir() 
                         if d.is_dir() and not d.name.startswith('_')
                         and (d / "INTERFACE.md").exists()]
        
        expected_interfaces = [
            "ontology-builder",
            "planning-task",
            "ppt-generator",
            "slidespeak-editor",
            "slidespeak-generator",
            "slidespeak-slide-editor"
        ]
        
        found_interfaces = [d.name for d in interface_dirs]
        
        for expected in expected_interfaces:
            assert expected in found_interfaces, f"缺少接口: {expected}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
