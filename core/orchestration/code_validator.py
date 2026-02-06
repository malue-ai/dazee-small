"""
CodeValidator - 代码验证器

职责：
- 语法验证：执行前检查代码语法正确性
- 依赖检查：检测代码需要的包是否已安装
- 安全检查：检测危险操作（可配置）
- 结果验证：执行后验证输出是否符合预期
- 错误分析：分析执行错误并提供修复建议

设计原则：
- 快速失败：语法错误在执行前捕获
- 可配置性：安全规则可自定义
- 可扩展性：支持多种语言（目前仅 Python）

使用方式：
    validator = create_code_validator()

    # 执行前验证
    result = validator.validate_syntax(code)
    if not result.is_valid:
        print(f"语法错误: {result.errors}")

    # 执行后验证
    result = validator.validate_execution_result(
        code=code,
        stdout=stdout,
        stderr=stderr,
        expected_outputs=["sales.xlsx"]
    )
"""

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from logger import get_logger

logger = get_logger("code_validator")


class ValidationLevel(Enum):
    """验证级别"""

    ERROR = "error"  # 必须修复
    WARNING = "warning"  # 建议修复
    INFO = "info"  # 信息提示


@dataclass
class ValidationIssue:
    """验证问题"""

    level: ValidationLevel
    code: str  # 错误代码
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    suggestion: Optional[str] = None  # 修复建议

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "suggestion": self.suggestion,
        }


@dataclass
class ValidationResult:
    """验证结果"""

    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[ValidationIssue]:
        """获取所有错误"""
        return [i for i in self.issues if i.level == ValidationLevel.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """获取所有警告"""
        return [i for i in self.issues if i.level == ValidationLevel.WARNING]

    @property
    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }

    def get_error_summary(self) -> str:
        """获取错误摘要"""
        if not self.errors:
            return "无错误"

        lines = ["代码验证发现以下问题:"]
        for i, error in enumerate(self.errors, 1):
            loc = f"第{error.line}行" if error.line else ""
            lines.append(f"  {i}. [{error.code}] {error.message} {loc}")
            if error.suggestion:
                lines.append(f"     建议: {error.suggestion}")

        return "\n".join(lines)


class CodeValidator:
    """
    代码验证器

    支持的验证类型：
    1. 语法验证（syntax）
    2. 依赖验证（dependencies）
    3. 安全验证（security）
    4. 执行结果验证（execution_result）
    """

    # 内置模块列表
    BUILTIN_MODULES = {
        "os",
        "sys",
        "re",
        "json",
        "time",
        "datetime",
        "math",
        "random",
        "collections",
        "itertools",
        "functools",
        "typing",
        "pathlib",
        "io",
        "pickle",
        "copy",
        "shutil",
        "tempfile",
        "glob",
        "fnmatch",
        "subprocess",
        "threading",
        "multiprocessing",
        "asyncio",
        "concurrent",
        "socket",
        "ssl",
        "http",
        "urllib",
        "email",
        "html",
        "xml",
        "logging",
        "warnings",
        "traceback",
        "inspect",
        "dis",
        "gc",
        "abc",
        "contextlib",
        "dataclasses",
        "enum",
        "types",
        "hashlib",
        "hmac",
        "secrets",
        "base64",
        "binascii",
        "struct",
        "codecs",
        "unicodedata",
        "string",
        "textwrap",
        "difflib",
        "csv",
        "configparser",
        "argparse",
        "getopt",
        "unittest",
        "doctest",
        "pdb",
        "profile",
        "timeit",
        "platform",
        "ctypes",
        "uuid",
        "weakref",
        "operator",
        "heapq",
        "bisect",
        "array",
        "queue",
        "decimal",
        "fractions",
        "statistics",
        "cmath",
        "numbers",
        "builtins",
        "__future__",
        "zipfile",
        "tarfile",
        "gzip",
        "bz2",
        "lzma",
        "zlib",
    }

    # 包名映射（import名 → pip包名）
    PACKAGE_MAPPING = {
        "cv2": "opencv-python",
        "PIL": "Pillow",
        "sklearn": "scikit-learn",
        "bs4": "beautifulsoup4",
        "yaml": "pyyaml",
    }

    # 危险操作模式
    DANGEROUS_PATTERNS = [
        (r"os\.system\s*\(", "os.system() 调用", "考虑使用 subprocess.run() 替代"),
        (r"eval\s*\(", "eval() 调用", "避免使用 eval()，考虑更安全的替代方案"),
        (r"exec\s*\(", "exec() 调用", "避免使用 exec()"),
        (r"__import__\s*\(", "动态导入", "使用显式 import 语句"),
        (r"subprocess\..*shell\s*=\s*True", "shell=True", "考虑使用 shell=False"),
        (r"rm\s+-rf\s+/", "危险的 rm 命令", "请确认删除路径"),
    ]

    def __init__(
        self, enable_security_check: bool = True, custom_dangerous_patterns: List[tuple] = None
    ):
        """
        初始化验证器

        Args:
            enable_security_check: 是否启用安全检查
            custom_dangerous_patterns: 自定义危险模式
        """
        self.enable_security_check = enable_security_check

        # 合并自定义危险模式
        self.dangerous_patterns = list(self.DANGEROUS_PATTERNS)
        if custom_dangerous_patterns:
            self.dangerous_patterns.extend(custom_dangerous_patterns)

        logger.debug("CodeValidator 初始化完成")

    def validate_syntax(self, code: str) -> ValidationResult:
        """
        验证 Python 代码语法

        Args:
            code: Python 代码

        Returns:
            ValidationResult
        """
        issues = []

        try:
            # 使用 AST 解析验证语法
            ast.parse(code)
            logger.debug("✓ 语法验证通过")

        except SyntaxError as e:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="SYNTAX_ERROR",
                    message=str(e.msg) if e.msg else "语法错误",
                    line=e.lineno,
                    column=e.offset,
                    suggestion=self._get_syntax_fix_suggestion(e),
                )
            )
            logger.warning(f"✗ 语法错误: {e.msg} (行 {e.lineno})")

        except Exception as e:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="PARSE_ERROR",
                    message=f"代码解析失败: {str(e)}",
                )
            )

        return ValidationResult(
            is_valid=len(issues) == 0, issues=issues, metadata={"validation_type": "syntax"}
        )

    def validate_dependencies(
        self, code: str, installed_packages: Set[str] = None
    ) -> ValidationResult:
        """
        验证代码依赖

        Args:
            code: Python 代码
            installed_packages: 已安装的包列表

        Returns:
            ValidationResult 包含需要安装的包列表
        """
        issues = []
        installed = installed_packages or set()

        # 提取 import 语句
        imports = self._extract_imports(code)

        # 检查每个导入
        missing_packages = []
        for pkg in imports:
            # 跳过内置模块
            if pkg in self.BUILTIN_MODULES:
                continue

            # 映射到 pip 包名
            pip_name = self.PACKAGE_MAPPING.get(pkg, pkg)

            # 检查是否已安装
            if pip_name.lower() not in {p.lower() for p in installed}:
                missing_packages.append(pip_name)

        if missing_packages:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    code="MISSING_DEPENDENCY",
                    message=f"缺少依赖包: {', '.join(missing_packages)}",
                    suggestion=f"pip install {' '.join(missing_packages)}",
                )
            )

        return ValidationResult(
            is_valid=True,  # 依赖缺失不是致命错误
            issues=issues,
            metadata={
                "validation_type": "dependencies",
                "detected_imports": list(imports),
                "missing_packages": missing_packages,
            },
        )

    def validate_security(self, code: str) -> ValidationResult:
        """
        安全性验证

        Args:
            code: Python 代码

        Returns:
            ValidationResult
        """
        if not self.enable_security_check:
            return ValidationResult(is_valid=True)

        issues = []

        for pattern, name, suggestion in self.dangerous_patterns:
            matches = list(re.finditer(pattern, code, re.MULTILINE))
            for match in matches:
                # 计算行号
                line_num = code[: match.start()].count("\n") + 1

                issues.append(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        code="SECURITY_WARNING",
                        message=f"检测到潜在危险操作: {name}",
                        line=line_num,
                        suggestion=suggestion,
                    )
                )

        return ValidationResult(
            is_valid=True,  # 安全警告不阻止执行
            issues=issues,
            metadata={"validation_type": "security"},
        )

    def validate_execution_result(
        self,
        code: str,
        stdout: str,
        stderr: str,
        exit_code: int = 0,
        expected_outputs: List[str] = None,
        expected_patterns: List[str] = None,
    ) -> ValidationResult:
        """
        验证执行结果

        Args:
            code: 执行的代码
            stdout: 标准输出
            stderr: 标准错误
            exit_code: 退出码
            expected_outputs: 期望的输出文件列表
            expected_patterns: 期望在 stdout 中匹配的模式

        Returns:
            ValidationResult
        """
        issues = []

        # 检查退出码
        if exit_code != 0:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    code="EXIT_CODE_ERROR",
                    message=f"执行退出码非零: {exit_code}",
                    suggestion="检查 stderr 获取错误详情",
                )
            )

        # 检查 stderr
        if stderr:
            # 分析错误类型
            error_info = self._analyze_error(stderr)
            issues.append(
                ValidationIssue(
                    level=(
                        ValidationLevel.ERROR if error_info["is_fatal"] else ValidationLevel.WARNING
                    ),
                    code=error_info["code"],
                    message=error_info["message"],
                    suggestion=error_info.get("suggestion"),
                )
            )

        # 检查期望的输出模式
        if expected_patterns:
            for pattern in expected_patterns:
                if not re.search(pattern, stdout):
                    issues.append(
                        ValidationIssue(
                            level=ValidationLevel.WARNING,
                            code="OUTPUT_PATTERN_MISSING",
                            message=f"输出中未找到期望的模式: {pattern}",
                        )
                    )

        return ValidationResult(
            is_valid=len([i for i in issues if i.level == ValidationLevel.ERROR]) == 0,
            issues=issues,
            metadata={
                "validation_type": "execution_result",
                "exit_code": exit_code,
                "stdout_length": len(stdout),
                "stderr_length": len(stderr),
            },
        )

    def validate_all(self, code: str, installed_packages: Set[str] = None) -> ValidationResult:
        """
        执行所有验证

        Args:
            code: Python 代码
            installed_packages: 已安装的包列表

        Returns:
            合并的 ValidationResult
        """
        all_issues = []
        metadata = {}

        # 1. 语法验证
        syntax_result = self.validate_syntax(code)
        all_issues.extend(syntax_result.issues)
        metadata["syntax"] = syntax_result.metadata

        # 如果语法有错误，直接返回
        if syntax_result.has_errors:
            return ValidationResult(is_valid=False, issues=all_issues, metadata=metadata)

        # 2. 依赖验证
        dep_result = self.validate_dependencies(code, installed_packages)
        all_issues.extend(dep_result.issues)
        metadata["dependencies"] = dep_result.metadata

        # 3. 安全验证
        security_result = self.validate_security(code)
        all_issues.extend(security_result.issues)
        metadata["security"] = security_result.metadata

        # 计算最终结果
        has_errors = any(i.level == ValidationLevel.ERROR for i in all_issues)

        return ValidationResult(is_valid=not has_errors, issues=all_issues, metadata=metadata)

    def _extract_imports(self, code: str) -> Set[str]:
        """提取代码中的 import 语句"""
        imports = set()

        # 匹配 import xxx
        pattern1 = r"^import\s+([\w\.]+)"
        # 匹配 from xxx import yyy
        pattern2 = r"^from\s+([\w\.]+)\s+import"

        for line in code.split("\n"):
            line = line.strip()

            match1 = re.match(pattern1, line)
            if match1:
                pkg = match1.group(1).split(".")[0]
                imports.add(pkg)

            match2 = re.match(pattern2, line)
            if match2:
                pkg = match2.group(1).split(".")[0]
                imports.add(pkg)

        return imports

    def _get_syntax_fix_suggestion(self, error: SyntaxError) -> str:
        """根据语法错误生成修复建议"""
        msg = str(error.msg).lower() if error.msg else ""

        if "expected ':'" in msg:
            return "在语句末尾添加冒号 ':'"
        elif "unexpected indent" in msg:
            return "检查缩进，确保使用一致的空格或 Tab"
        elif "unindent" in msg:
            return "检查缩进级别是否匹配"
        elif "unterminated string" in msg:
            return "检查字符串是否正确闭合"
        elif "unexpected eof" in msg or "eof" in msg:
            return "代码不完整，检查是否缺少闭合括号或引号"
        elif "invalid syntax" in msg:
            return "检查该行的语法，可能有拼写错误或缺少符号"

        return "检查该行的语法"

    def _analyze_error(self, stderr: str) -> Dict[str, Any]:
        """分析错误信息"""
        stderr_lower = stderr.lower()

        # 常见错误模式
        if "modulenotfounderror" in stderr_lower or "no module named" in stderr_lower:
            # 提取模块名
            match = re.search(r"no module named ['\"]?(\w+)['\"]?", stderr_lower)
            module = match.group(1) if match else "unknown"
            return {
                "code": "MODULE_NOT_FOUND",
                "message": f"模块未找到: {module}",
                "suggestion": f"运行 pip install {module}",
                "is_fatal": True,
            }

        elif "filenotfounderror" in stderr_lower or "no such file" in stderr_lower:
            return {
                "code": "FILE_NOT_FOUND",
                "message": "文件未找到",
                "suggestion": "检查文件路径是否正确",
                "is_fatal": True,
            }

        elif "permissionerror" in stderr_lower:
            return {
                "code": "PERMISSION_ERROR",
                "message": "权限不足",
                "suggestion": "检查文件/目录权限",
                "is_fatal": True,
            }

        elif "typeerror" in stderr_lower:
            return {
                "code": "TYPE_ERROR",
                "message": "类型错误",
                "suggestion": "检查变量类型是否匹配",
                "is_fatal": True,
            }

        elif "valueerror" in stderr_lower:
            return {
                "code": "VALUE_ERROR",
                "message": "值错误",
                "suggestion": "检查传入的参数值",
                "is_fatal": True,
            }

        elif "keyerror" in stderr_lower:
            return {
                "code": "KEY_ERROR",
                "message": "键错误",
                "suggestion": "检查字典键是否存在",
                "is_fatal": True,
            }

        elif "indexerror" in stderr_lower:
            return {
                "code": "INDEX_ERROR",
                "message": "索引越界",
                "suggestion": "检查列表索引范围",
                "is_fatal": True,
            }

        elif "warning" in stderr_lower and "error" not in stderr_lower:
            return {
                "code": "EXECUTION_WARNING",
                "message": "执行警告",
                "suggestion": None,
                "is_fatal": False,
            }

        else:
            return {
                "code": "EXECUTION_ERROR",
                "message": f"执行错误: {stderr[:200]}",
                "suggestion": "检查完整的错误堆栈",
                "is_fatal": True,
            }


def create_code_validator(
    enable_security_check: bool = True, custom_dangerous_patterns: List[tuple] = None
) -> CodeValidator:
    """
    创建代码验证器

    Args:
        enable_security_check: 是否启用安全检查
        custom_dangerous_patterns: 自定义危险模式

    Returns:
        CodeValidator 实例
    """
    return CodeValidator(
        enable_security_check=enable_security_check,
        custom_dangerous_patterns=custom_dangerous_patterns,
    )
