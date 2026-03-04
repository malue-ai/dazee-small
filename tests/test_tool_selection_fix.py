"""工具选择系统级修复 - 冒烟测试（纯单元测试，无框架依赖）"""
import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestFix1PlanFieldName(unittest.TestCase):
    """Fix 1: selector 读 required_skills"""

    def test_reads_required_skills(self):
        src = open(os.path.join(ROOT, "core/tool/selector.py")).read()
        self.assertIn('plan.get("required_skills")', src)

    def test_no_required_capabilities_residue(self):
        src = open(os.path.join(ROOT, "core/tool/selector.py")).read()
        self.assertNotIn('plan.get("required_capabilities")', src)

    def test_plan_tool_writes_required_skills(self):
        src = open(os.path.join(ROOT, "tools/plan_todo_tool.py")).read()
        self.assertIn("required_skills", src)


class TestFix2IntentResult(unittest.TestCase):
    """Fix 2a: IntentResult 数据类"""

    def test_field_exists(self):
        src = open(os.path.join(ROOT, "core/routing/types.py")).read()
        tree = ast.parse(src)
        fields = [
            node.target.id
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        ]
        self.assertIn("required_tools", fields)

    def test_to_dict_includes_field(self):
        src = open(os.path.join(ROOT, "core/routing/types.py")).read()
        self.assertIn('"required_tools"', src)


class TestFix2Schema(unittest.TestCase):
    """Fix 2b: _INTENT_TOOL schema"""

    def setUp(self):
        src = open(os.path.join(ROOT, "core/routing/intent_analyzer.py")).read()
        self.src = src

    def test_schema_has_required_tools_property(self):
        self.assertIn('"required_tools"', self.src)

    def test_schema_enum_values(self):
        self.assertIn('"browser"', self.src)
        self.assertIn('"audio_processing"', self.src)
        self.assertIn('"code_execution"', self.src)

    def test_required_list_includes_field(self):
        # required_tools 出现在 required 列表中
        lines = self.src.split("\n")
        in_required = False
        found = False
        for line in lines:
            if '"required"' in line and "[" in line:
                in_required = True
            if in_required and '"required_tools"' in line:
                found = True
                break
            if in_required and "]" in line:
                break
        self.assertTrue(found, "required_tools 不在 required 列表中")


class TestFix2Parse(unittest.TestCase):
    """Fix 2c: _parse_intent_dict 解析"""

    def test_parses_required_tools(self):
        src = open(os.path.join(ROOT, "core/routing/intent_analyzer.py")).read()
        self.assertIn('parsed.get("required_tools"', src)
        self.assertIn("required_tools=required_tools", src)


class TestFix2Selector(unittest.TestCase):
    """Fix 2d+e: resolve_capabilities 签名和优先级"""

    def setUp(self):
        self.src = open(os.path.join(ROOT, "core/tool/selector.py")).read()

    def test_has_intent_parameter(self):
        self.assertIn("intent_required_tools", self.src)

    def test_four_level_priority(self):
        for source in ["plan", "intent", "schema", "default"]:
            self.assertIn(
                f'selection_source = "{source}"',
                self.src,
                f"缺少 {source} 优先级",
            )

    def test_intent_before_schema(self):
        intent_pos = self.src.index('selection_source = "intent"')
        schema_pos = self.src.index('selection_source = "schema"')
        self.assertLess(intent_pos, schema_pos, "intent 应在 schema 之前")


class TestFix2Base(unittest.TestCase):
    """Fix 2f: base.py 传递 intent"""

    def test_passes_required_tools(self):
        src = open(os.path.join(ROOT, "core/agent/base.py")).read()
        self.assertIn("intent.required_tools", src)
        self.assertIn("intent_required_tools=", src)


class TestFix2Prompt(unittest.TestCase):
    """Fix 2g: prompt Few-Shot"""

    def setUp(self):
        self.src = open(
            os.path.join(ROOT, "prompts/intent_recognition_prompt.py")
        ).read()

    def test_all_examples_have_required_tools(self):
        count = self.src.count("required_tools")
        self.assertGreaterEqual(count, 30, f"只有 {count} 处")

    def test_has_browser_example(self):
        self.assertIn('"required_tools": ["browser"]', self.src)

    def test_has_audio_example(self):
        self.assertIn('"required_tools": ["audio_processing"]', self.src)

    def test_has_code_example(self):
        self.assertIn('"required_tools": ["code_execution"]', self.src)

    def test_output_format_includes_field(self):
        self.assertIn('"required_tools": []', self.src)


class TestFix3Fallback(unittest.TestCase):
    """Fix 3: 全量 fallback"""

    def test_uses_all_tools(self):
        src = open(os.path.join(ROOT, "core/tool/selector.py")).read()
        self.assertIn("self.registry.capabilities.keys()", src)

    def test_old_warning_removed(self):
        src = open(os.path.join(ROOT, "core/tool/selector.py")).read()
        self.assertNotIn("⚠️ 无可用来源", src)


class TestFix4Compaction(unittest.TestCase):
    """Fix 4: 上下文压缩成对处理"""

    def setUp(self):
        self.src = open(
            os.path.join(ROOT, "core/context/compaction/__init__.py")
        ).read()

    def test_function_defined(self):
        self.assertIn("def _ensure_tool_pairs_in_trimmed", self.src)

    def test_called_in_trim(self):
        self.assertIn("_ensure_tool_pairs_in_trimmed(result)", self.src)

    def test_called_before_ensure_tool_pairs(self):
        pos_new = self.src.index("_ensure_tool_pairs_in_trimmed(result)")
        pos_old = self.src.index("ClaudeAdaptor.ensure_tool_pairs(result)")
        self.assertLess(pos_new, pos_old, "应在 ensure_tool_pairs 之前调用")

    def test_converts_orphan_to_summary(self):
        self.assertIn("之前调用了", self.src)
        self.assertIn("结果未记录", self.src)


class TestCallChainIntegrity(unittest.TestCase):
    """端到端调用链完整性"""

    def test_plan_tool_to_selector(self):
        """plan_todo_tool 写 required_skills → selector 读 required_skills"""
        plan_src = open(os.path.join(ROOT, "tools/plan_todo_tool.py")).read()
        sel_src = open(os.path.join(ROOT, "core/tool/selector.py")).read()
        self.assertIn("required_skills", plan_src)
        self.assertIn('plan.get("required_skills")', sel_src)

    def test_analyzer_to_types(self):
        """analyzer 写 required_tools= → IntentResult 有 required_tools 字段"""
        ana_src = open(os.path.join(ROOT, "core/routing/intent_analyzer.py")).read()
        typ_src = open(os.path.join(ROOT, "core/routing/types.py")).read()
        self.assertIn("required_tools=required_tools", ana_src)
        self.assertIn("required_tools: Optional", typ_src)

    def test_types_to_base(self):
        """IntentResult.required_tools → base.py 读 intent.required_tools"""
        base_src = open(os.path.join(ROOT, "core/agent/base.py")).read()
        self.assertIn("intent.required_tools", base_src)

    def test_base_to_selector(self):
        """base.py intent_required_tools= → selector 参数 intent_required_tools"""
        base_src = open(os.path.join(ROOT, "core/agent/base.py")).read()
        sel_src = open(os.path.join(ROOT, "core/tool/selector.py")).read()
        self.assertIn("intent_required_tools=", base_src)
        self.assertIn("intent_required_tools:", sel_src)

    def test_compaction_before_adaptor(self):
        """_ensure_tool_pairs_in_trimmed 在 ensure_tool_pairs 之前"""
        src = open(os.path.join(ROOT, "core/context/compaction/__init__.py")).read()
        p1 = src.index("_ensure_tool_pairs_in_trimmed(result)")
        p2 = src.index("ClaudeAdaptor.ensure_tool_pairs(result)")
        self.assertLess(p1, p2)


if __name__ == "__main__":
    os.chdir(ROOT)
    unittest.main(verbosity=2)
