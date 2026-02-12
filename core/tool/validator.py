"""
工具验证器 - Tool Validator

职责：
1. Schema 验证（参数格式）
2. 代码静态分析（安全检查）
3. 同步/异步检测
4. 信任等级判定

原则：永远不要直接执行未经验证的用户代码
"""

import ast
import asyncio
import hashlib
import inspect
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from logger import get_logger

logger = get_logger("tool_validator")


# ============================================================
# 信任等级
# ============================================================


class TrustLevel(str, Enum):
    """工具信任等级"""

    L1_BUILTIN = "L1"  # 内置工具，完全信任
    L2_REVIEWED = "L2"  # 审核过的工具，高信任
    L3_RESTRICTED = "L3"  # 受限执行，中等信任


class ExecutionMode(str, Enum):
    """执行模式"""

    DIRECT = "direct"  # 直接执行（仅限 L1/L2）
    RESTRICTED = "restricted"  # 受限环境执行
    THREAD_POOL = "thread_pool"  # 线程池（同步代码包装）


# ============================================================
# 验证结果
# ============================================================


@dataclass
class ValidationResult:
    """验证结果"""

    valid: bool
    trust_level: TrustLevel = TrustLevel.L3_RESTRICTED
    execution_mode: ExecutionMode = ExecutionMode.RESTRICTED
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # 代码分析结果
    is_async: bool = False
    has_main_function: bool = False
    has_tool_class: bool = False
    imported_modules: Set[str] = field(default_factory=set)
    detected_risks: List[str] = field(default_factory=list)

    # 代码哈希
    code_hash: Optional[str] = None

    def add_error(self, error: str):
        self.errors.append(error)
        self.valid = False

    def add_warning(self, warning: str):
        self.warnings.append(warning)


# ============================================================
# 安全配置
# ============================================================

# 禁止的模式（正则）
FORBIDDEN_PATTERNS = [
    (r"\b__import__\s*\(", "禁止使用 __import__"),
    (r"\beval\s*\(", "禁止使用 eval"),
    (r"\bexec\s*\(", "禁止使用 exec"),
    (r"\bcompile\s*\(", "禁止使用 compile"),
    (r"\bglobals\s*\(", "禁止使用 globals"),
    (r"\blocals\s*\(", "禁止使用 locals"),
    (r'\bgetattr\s*\(.+,\s*[\'"]__', "禁止访问双下划线属性"),
    (r'\bsetattr\s*\(.+,\s*[\'"]__', "禁止设置双下划线属性"),
    (r"\bdelattr\s*\(", "禁止使用 delattr"),
    (r"\b__builtins__", "禁止访问 __builtins__"),
    (r"\b__code__", "禁止访问 __code__"),
    (r"\b__class__\.__bases__", "禁止访问类继承链"),
]

# 禁止导入的模块
FORBIDDEN_IMPORTS = {
    # 系统操作
    "os",
    "sys",
    "subprocess",
    "shutil",
    "pathlib",
    # 进程/线程
    "multiprocessing",
    "threading",
    "concurrent",
    # 网络（除非明确允许）
    "socket",
    "ssl",
    "ftplib",
    "smtplib",
    "telnetlib",
    # 危险模块
    "pickle",
    "marshal",
    "shelve",
    "ctypes",
    "cffi",
    "code",
    "codeop",
    "importlib",
    # 文件操作
    "io",
    "tempfile",
    "glob",
}

# 允许的模块（白名单）
ALLOWED_IMPORTS = {
    # 基础
    "typing",
    "types",
    "dataclasses",
    "abc",
    "enum",
    # 数据处理
    "json",
    "re",
    "datetime",
    "time",
    "math",
    "decimal",
    "fractions",
    "statistics",
    "random",
    # 集合
    "collections",
    "collections.abc",
    "itertools",
    "functools",
    "operator",
    # 字符串
    "string",
    "textwrap",
    "unicodedata",
    # 异步
    "asyncio",
    # 日志（安全的）
    "logging",
}

# 需要网络权限的模块
NETWORK_MODULES = {
    "httpx",
    "aiohttp",
    "requests",
    "urllib",
    "urllib.request",
    "urllib.parse",
}

# 需要特殊权限的模块
PRIVILEGED_MODULES = {
    "pandas",
    "numpy",
    "scipy",
    "matplotlib",
    "plotly",
    "beautifulsoup4",
    "bs4",
    "lxml",
}


# ============================================================
# 代码分析器
# ============================================================


class CodeAnalyzer(ast.NodeVisitor):
    """
    AST 代码分析器

    检查用户代码的安全性
    """

    def __init__(self):
        self.imports: Set[str] = set()
        self.from_imports: Set[str] = set()
        self.function_defs: Dict[str, bool] = {}  # name -> is_async
        self.class_defs: Set[str] = set()
        self.risks: List[str] = []
        self.has_main: bool = False
        self.has_tool_class: bool = False
        self.is_main_async: bool = False

    def visit_Import(self, node: ast.Import):
        """检查 import 语句"""
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            self.imports.add(module_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """检查 from ... import 语句"""
        if node.module:
            module_name = node.module.split(".")[0]
            self.from_imports.add(module_name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """检查函数定义"""
        self.function_defs[node.name] = False
        if node.name == "main":
            self.has_main = True
            self.is_main_async = False
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """检查异步函数定义"""
        self.function_defs[node.name] = True
        if node.name == "main":
            self.has_main = True
            self.is_main_async = True
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """检查类定义"""
        self.class_defs.add(node.name)

        # 检查是否是 Tool 类
        if node.name == "Tool":
            self.has_tool_class = True

            # 检查是否有 execute 方法
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == "execute":
                        self.is_main_async = isinstance(item, ast.AsyncFunctionDef)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """检查函数调用"""
        # 检查危险函数调用
        if isinstance(node.func, ast.Name):
            if node.func.id in ("eval", "exec", "compile", "__import__"):
                self.risks.append(f"禁止调用 {node.func.id}()")

        # 检查 getattr/setattr 访问双下划线属性
        if isinstance(node.func, ast.Name) and node.func.id in ("getattr", "setattr"):
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                attr_name = node.args[1].value
                if isinstance(attr_name, str) and attr_name.startswith("__"):
                    self.risks.append(f"禁止访问双下划线属性: {attr_name}")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """检查属性访问"""
        # 检查危险属性访问
        if node.attr.startswith("__") and node.attr.endswith("__"):
            if node.attr not in ("__init__", "__str__", "__repr__", "__dict__", "__class__"):
                self.risks.append(f"禁止访问魔术属性: {node.attr}")

        self.generic_visit(node)

    def get_all_imports(self) -> Set[str]:
        """获取所有导入的模块"""
        return self.imports | self.from_imports


# ============================================================
# 工具验证器
# ============================================================


class ToolValidator:
    """
    工具验证器

    提供完整的工具验证功能：
    1. Schema 验证
    2. 代码安全检查
    3. 信任等级判定
    """

    def __init__(
        self,
        allow_network: bool = False,
        allow_privileged: bool = False,
        custom_allowed_imports: Optional[Set[str]] = None,
    ):
        """
        初始化验证器

        Args:
            allow_network: 是否允许网络模块
            allow_privileged: 是否允许特权模块
            custom_allowed_imports: 自定义允许的模块
        """
        self.allow_network = allow_network
        self.allow_privileged = allow_privileged

        # 构建允许的模块集合
        self.allowed_imports = ALLOWED_IMPORTS.copy()
        if allow_network:
            self.allowed_imports |= NETWORK_MODULES
        if allow_privileged:
            self.allowed_imports |= PRIVILEGED_MODULES
        if custom_allowed_imports:
            self.allowed_imports |= custom_allowed_imports

    def validate_schema(self, input_schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证输入 Schema

        Args:
            input_schema: JSON Schema 格式的输入定义

        Returns:
            (is_valid, errors)
        """
        errors = []

        # 必须是 object 类型
        if input_schema.get("type") != "object":
            errors.append("input_schema.type 必须是 'object'")

        # 必须有 properties
        if "properties" not in input_schema:
            errors.append("input_schema 必须包含 properties")

        # 检查每个属性
        properties = input_schema.get("properties", {})
        for name, prop in properties.items():
            if "type" not in prop:
                errors.append(f"属性 '{name}' 缺少 type 定义")

        # 检查 required
        required = input_schema.get("required", [])
        for req in required:
            if req not in properties:
                errors.append(f"required 中的 '{req}' 不在 properties 中")

        return len(errors) == 0, errors

    def validate_code(
        self, code: str, trust_level: TrustLevel = TrustLevel.L3_RESTRICTED
    ) -> ValidationResult:
        """
        验证工具代码

        Args:
            code: Python 代码
            trust_level: 期望的信任等级

        Returns:
            ValidationResult
        """
        result = ValidationResult(valid=True, trust_level=trust_level)

        # 1. 正则模式检查（快速）
        self._check_forbidden_patterns(code, result)

        # 2. AST 分析（深度）
        try:
            tree = ast.parse(code)
            analyzer = CodeAnalyzer()
            analyzer.visit(tree)

            # 记录分析结果
            result.imported_modules = analyzer.get_all_imports()
            result.has_main_function = analyzer.has_main
            result.has_tool_class = analyzer.has_tool_class
            result.is_async = analyzer.is_main_async
            result.detected_risks = analyzer.risks

            # 检查导入
            self._check_imports(analyzer.get_all_imports(), result)

            # 检查风险
            for risk in analyzer.risks:
                result.add_error(risk)

            # 检查入口点
            if not analyzer.has_main and not analyzer.has_tool_class:
                result.add_error("代码必须包含 main 函数或 Tool 类")

        except SyntaxError as e:
            result.add_error(f"语法错误: {str(e)}")

        # 3. 计算代码哈希
        result.code_hash = f"sha256:{hashlib.sha256(code.encode()).hexdigest()}"

        # 4. 确定执行模式
        result.execution_mode = self._determine_execution_mode(result)

        # 5. 同步函数警告
        if not result.is_async and result.valid:
            result.add_warning("建议使用 async 函数以避免阻塞")

        return result

    def _check_forbidden_patterns(self, code: str, result: ValidationResult):
        """检查禁止的模式"""
        for pattern, message in FORBIDDEN_PATTERNS:
            if re.search(pattern, code):
                result.add_error(message)

    def _check_imports(self, imports: Set[str], result: ValidationResult):
        """检查导入的模块"""
        for module in imports:
            # 检查是否在禁止列表
            if module in FORBIDDEN_IMPORTS:
                result.add_error(f"禁止导入模块: {module}")

            # 检查是否在允许列表
            elif module not in self.allowed_imports:
                # 检查是否是网络模块
                if module in NETWORK_MODULES:
                    if not self.allow_network:
                        result.add_error(f"模块 {module} 需要网络权限")
                    else:
                        result.add_warning(f"使用网络模块: {module}")

                # 检查是否是特权模块
                elif module in PRIVILEGED_MODULES:
                    if not self.allow_privileged:
                        result.add_error(f"模块 {module} 需要特殊权限")
                    else:
                        result.add_warning(f"使用特权模块: {module}")

                # 未知模块
                else:
                    result.add_warning(f"未知模块: {module}（将在受限环境中验证）")

    def _determine_execution_mode(self, result: ValidationResult) -> ExecutionMode:
        """确定执行模式"""
        # L1/L2 可以直接执行
        if result.trust_level in (TrustLevel.L1_BUILTIN, TrustLevel.L2_REVIEWED):
            return ExecutionMode.DIRECT

        # L3 在受限环境执行
        return ExecutionMode.RESTRICTED

    def validate_function(self, func: Callable) -> ValidationResult:
        """
        验证函数对象

        Args:
            func: 函数对象

        Returns:
            ValidationResult
        """
        result = ValidationResult(valid=True)

        # 检查是否是异步函数
        result.is_async = asyncio.iscoroutinefunction(func)

        if not result.is_async:
            result.add_warning("函数不是异步的，将在线程池中执行")
            result.execution_mode = ExecutionMode.THREAD_POOL
        else:
            result.execution_mode = ExecutionMode.DIRECT

        # 检查函数签名
        try:
            sig = inspect.signature(func)

            # 检查是否有类型注解
            for name, param in sig.parameters.items():
                if name in ("self", "cls"):
                    continue
                if param.annotation == inspect.Parameter.empty:
                    result.add_warning(f"参数 '{name}' 缺少类型注解")

            # 检查返回值注解
            if sig.return_annotation == inspect.Signature.empty:
                result.add_warning("函数缺少返回值类型注解")

        except (ValueError, TypeError) as e:
            result.add_warning(f"无法解析函数签名: {str(e)}")

        # 已加载的函数默认信任等级为 L2
        result.trust_level = TrustLevel.L2_REVIEWED

        return result


# ============================================================
# 便捷函数
# ============================================================

_default_validator: Optional[ToolValidator] = None


def get_tool_validator(
    allow_network: bool = False, allow_privileged: bool = False
) -> ToolValidator:
    """获取工具验证器"""
    global _default_validator
    if _default_validator is None:
        _default_validator = ToolValidator(
            allow_network=allow_network, allow_privileged=allow_privileged
        )
    return _default_validator


def validate_tool_code(
    code: str, allow_network: bool = False, allow_privileged: bool = False
) -> ValidationResult:
    """
    快速验证工具代码

    Args:
        code: Python 代码
        allow_network: 是否允许网络访问
        allow_privileged: 是否允许特权模块

    Returns:
        ValidationResult
    """
    validator = ToolValidator(allow_network=allow_network, allow_privileged=allow_privileged)
    return validator.validate_code(code)


def validate_tool_schema(input_schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """快速验证输入 Schema"""
    validator = ToolValidator()
    return validator.validate_schema(input_schema)
