"""
OutputFormatter - 输出格式化器

职责：
- 支持多种输出格式（text/markdown/json/html）
- JSON 格式校验（使用 Pydantic）
- 输出长度限制
- 代码高亮（markdown 模式）

设计原则：
- 默认 text 输出（最简单、最兼容）
- JSON 格式使用 Pydantic 模型校验（Python 主流方案）
- 校验失败可选：警告 or 抛出错误

V6.3 改进：
- 使用 Pydantic 替代 jsonschema（更 Pythonic、更强大）
- 支持从 Pydantic 模型名称加载校验器
- 支持动态创建 Pydantic 模型
"""

import json
import re
from typing import Any, Dict, Optional, Type, get_type_hints

from pydantic import BaseModel, Field, ValidationError, create_model

from logger import get_logger

logger = get_logger(__name__)


class OutputFormatError(Exception):
    """输出格式化错误"""

    pass


class JSONValidationError(OutputFormatError):
    """JSON 校验错误（Pydantic 校验失败）"""

    pass


# ============================================================
# 常用 Pydantic 输出模型示例
# ============================================================


class BaseOutputModel(BaseModel):
    """输出模型基类"""

    class Config:
        extra = "allow"  # 允许额外字段
        json_encoders = {
            # 自定义 JSON 序列化
        }


class SimpleResponse(BaseOutputModel):
    """简单响应模型"""

    status: str = Field(description="状态：success/error")
    message: str = Field(default="", description="消息")
    data: Optional[Any] = Field(default=None, description="数据")


class APIResponse(BaseOutputModel):
    """API 响应模型"""

    status: str = Field(description="状态：success/error/pending")
    code: int = Field(default=0, description="状态码")
    message: str = Field(default="", description="消息")
    data: Optional[Dict[str, Any]] = Field(default=None, description="响应数据")
    error: Optional[str] = Field(default=None, description="错误信息")


class UserInfo(BaseOutputModel):
    """用户信息模型"""

    name: str = Field(description="用户名")
    email: Optional[str] = Field(default=None, description="邮箱")
    age: Optional[int] = Field(default=None, ge=0, le=150, description="年龄")
    tags: Optional[list] = Field(default_factory=list, description="标签")


class ListResponse(BaseOutputModel):
    """列表响应模型"""

    items: list = Field(default_factory=list, description="列表项")
    total: int = Field(default=0, ge=0, description="总数")
    page: int = Field(default=1, ge=1, description="当前页")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


# 预定义模型注册表
BUILTIN_OUTPUT_MODELS: Dict[str, Type[BaseModel]] = {
    "SimpleResponse": SimpleResponse,
    "APIResponse": APIResponse,
    "UserInfo": UserInfo,
    "ListResponse": ListResponse,
}


# ============================================================
# OutputFormatter 核心实现
# ============================================================


class OutputFormatter:
    """
    输出格式化器（使用 Pydantic 校验）

    功能：
    1. 多格式输出：text/markdown/json/html
    2. Pydantic 模型校验（替代 jsonschema）
    3. 输出长度限制
    4. 代码高亮（markdown）

    使用示例：
        # 方式 1：使用内置模型
        formatter = OutputFormatter(
            default_format="json",
            pydantic_model=SimpleResponse,
            strict_json_validation=True
        )

        # 方式 2：使用模型名称
        formatter = OutputFormatter(
            default_format="json",
            model_name="APIResponse"
        )

        # 方式 3：动态创建模型
        formatter = OutputFormatter(
            default_format="json",
            json_schema={
                "name": {"type": "str", "required": True},
                "age": {"type": "int", "default": 0}
            }
        )

        # 格式化输出
        result = formatter.format(
            content='{"status": "success", "message": "OK"}',
            format="json"
        )
    """

    def __init__(
        self,
        default_format: str = "text",
        pydantic_model: Optional[Type[BaseModel]] = None,
        model_name: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        strict_json_validation: bool = False,
        json_ensure_ascii: bool = False,
        json_indent: Optional[int] = 2,
        code_highlighting: bool = True,
        max_output_length: int = 50000,
    ):
        """
        初始化输出格式化器

        Args:
            default_format: 默认输出格式（text/markdown/json/html）
            pydantic_model: Pydantic 模型类（优先级最高）
            model_name: 内置模型名称（从 BUILTIN_OUTPUT_MODELS 加载）
            json_schema: 动态 Schema 定义（用于动态创建 Pydantic 模型）
            strict_json_validation: 严格校验（不通过则抛出错误）
            json_ensure_ascii: JSON 序列化时是否确保 ASCII
            json_indent: JSON 缩进空格数（None 为紧凑格式）
            code_highlighting: 是否启用代码高亮
            max_output_length: 最大输出长度
        """
        self.default_format = default_format
        self.strict_json_validation = strict_json_validation
        self.json_ensure_ascii = json_ensure_ascii
        self.json_indent = json_indent
        self.code_highlighting = code_highlighting
        self.max_output_length = max_output_length

        # 初始化 Pydantic 模型
        self.pydantic_model: Optional[Type[BaseModel]] = None

        if pydantic_model:
            # 优先使用传入的模型
            self.pydantic_model = pydantic_model
            logger.info(f"✅ 使用 Pydantic 模型: {pydantic_model.__name__}")
        elif model_name and model_name in BUILTIN_OUTPUT_MODELS:
            # 从内置模型加载
            self.pydantic_model = BUILTIN_OUTPUT_MODELS[model_name]
            logger.info(f"✅ 使用内置模型: {model_name}")
        elif json_schema:
            # 动态创建 Pydantic 模型
            self.pydantic_model = self._create_dynamic_model(json_schema)
            if self.pydantic_model:
                logger.info(f"✅ 动态创建 Pydantic 模型成功")
        else:
            logger.debug("○ 未配置 JSON 校验模型（跳过 JSON 校验）")

    def _create_dynamic_model(self, schema: Dict[str, Any]) -> Optional[Type[BaseModel]]:
        """
        根据 Schema 动态创建 Pydantic 模型

        Schema 格式（简化版）：
        {
            "name": {"type": "str", "required": True, "description": "名称"},
            "age": {"type": "int", "default": 0, "ge": 0, "le": 150},
            "tags": {"type": "list", "default": []}
        }

        Args:
            schema: 字段定义

        Returns:
            动态创建的 Pydantic 模型类
        """
        try:
            fields = {}

            for field_name, field_def in schema.items():
                # 解析类型
                type_str = field_def.get("type", "str")
                type_map = {
                    "str": str,
                    "string": str,
                    "int": int,
                    "integer": int,
                    "float": float,
                    "number": float,
                    "bool": bool,
                    "boolean": bool,
                    "list": list,
                    "array": list,
                    "dict": dict,
                    "object": dict,
                    "any": Any,
                }
                field_type = type_map.get(type_str, Any)

                # 是否可选
                is_required = field_def.get("required", False)
                default_value = field_def.get("default", ... if is_required else None)

                # 如果不是必需且无默认值，使用 Optional
                if not is_required and default_value is None:
                    field_type = Optional[field_type]

                # 创建 Field
                field_kwargs = {}
                if "description" in field_def:
                    field_kwargs["description"] = field_def["description"]
                if "ge" in field_def:
                    field_kwargs["ge"] = field_def["ge"]
                if "le" in field_def:
                    field_kwargs["le"] = field_def["le"]
                if "min_length" in field_def:
                    field_kwargs["min_length"] = field_def["min_length"]
                if "max_length" in field_def:
                    field_kwargs["max_length"] = field_def["max_length"]

                fields[field_name] = (field_type, Field(default=default_value, **field_kwargs))

            # 动态创建模型
            DynamicModel = create_model("DynamicOutputModel", **fields)
            return DynamicModel

        except Exception as e:
            logger.error(f"❌ 动态创建 Pydantic 模型失败: {str(e)}")
            return None

    def format(
        self, content: Any, format: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        格式化输出内容

        Args:
            content: 原始内容（可以是 str/dict/list）
            format: 输出格式（None 使用默认格式）
            metadata: 元数据（如 session_id, user_id 等）

        Returns:
            格式化后的字符串

        Raises:
            JSONValidationError: JSON 校验失败（strict_json_validation=True 时）
            OutputFormatError: 其他格式化错误
        """
        output_format = format or self.default_format

        try:
            # 根据格式选择处理方法
            if output_format == "json":
                result = self._format_json(content, metadata)
            elif output_format == "markdown":
                result = self._format_markdown(content, metadata)
            elif output_format == "text":
                result = self._format_text(content, metadata)
            elif output_format == "html":
                result = self._format_html(content, metadata)
            else:
                logger.warning(f"⚠️ 不支持的格式 '{output_format}'，回退到 text 格式")
                result = self._format_text(content, metadata)

            # 检查输出长度
            if len(result) > self.max_output_length:
                logger.warning(
                    f"⚠️ 输出超出最大长度 ({len(result)} > {self.max_output_length})，" f"将被截断"
                )
                result = result[: self.max_output_length] + "\n\n[输出已截断]"

            return result

        except JSONValidationError:
            raise  # JSON 校验错误直接抛出
        except Exception as e:
            error_msg = f"输出格式化失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise OutputFormatError(error_msg) from e

    def _format_json(self, content: Any, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        JSON 格式输出（使用 Pydantic 校验）

        流程：
        1. 尝试解析 content 为 JSON 对象
        2. 如果有 Pydantic 模型，进行校验
        3. 序列化为 JSON 字符串
        """
        # 步骤 1: 解析为 JSON 对象
        if isinstance(content, str):
            json_obj = self._extract_json_from_text(content)
        elif isinstance(content, (dict, list)):
            json_obj = content
        else:
            json_obj = {"content": str(content), "type": type(content).__name__}

        # 步骤 2: Pydantic 模型校验
        if self.pydantic_model and isinstance(json_obj, dict):
            try:
                # 使用 Pydantic 校验
                validated = self.pydantic_model(**json_obj)
                # 校验通过，使用校验后的数据
                json_obj = validated.model_dump(exclude_none=True)
                logger.info(f"✅ Pydantic 校验通过: {self.pydantic_model.__name__}")
            except ValidationError as e:
                error_details = e.errors()
                error_msg = f"Pydantic 校验失败: {len(error_details)} 个错误"
                logger.error(f"❌ {error_msg}")
                for err in error_details[:3]:  # 只显示前 3 个错误
                    logger.error(f"   - {err['loc']}: {err['msg']}")

                if self.strict_json_validation:
                    raise JSONValidationError(error_msg) from e
                else:
                    logger.warning("⚠️ 继续输出原始数据（非严格模式）")

        # 步骤 3: 序列化为 JSON 字符串
        try:
            result = json.dumps(
                json_obj, ensure_ascii=self.json_ensure_ascii, indent=self.json_indent, default=str
            )
            return result
        except Exception as e:
            error_msg = f"JSON 序列化失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise OutputFormatError(error_msg) from e

    def _extract_json_from_text(self, text: str) -> Any:
        """
        从文本中提取 JSON 对象

        策略：
        1. 尝试直接 json.loads(text)
        2. 如果失败，查找 ```json...``` 代码块
        3. 如果失败，查找第一个 {...} 或 [...]
        4. 如果失败，返回 {"content": text}
        """
        # 策略 1: 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 策略 2: 提取 ```json...``` 代码块
        json_block_pattern = r"```json\s*\n(.*?)\n```"
        match = re.search(json_block_pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 策略 3: 查找第一个 {...}
        brace_start = text.find("{")
        if brace_start >= 0:
            # 尝试找匹配的 }
            brace_count = 0
            for i, char in enumerate(text[brace_start:], brace_start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            return json.loads(text[brace_start : i + 1])
                        except json.JSONDecodeError:
                            pass
                        break

        # 查找第一个 [...]
        bracket_start = text.find("[")
        if bracket_start >= 0:
            bracket_count = 0
            for i, char in enumerate(text[bracket_start:], bracket_start):
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        try:
                            return json.loads(text[bracket_start : i + 1])
                        except json.JSONDecodeError:
                            pass
                        break

        # 策略 4: 包装为对象
        logger.warning("⚠️ 无法从文本提取 JSON，包装为对象")
        return {"content": text, "format": "raw_text"}

    def _format_markdown(self, content: Any, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Markdown 格式输出"""
        if isinstance(content, str):
            return content
        elif isinstance(content, (dict, list)):
            json_str = json.dumps(content, ensure_ascii=False, indent=2)
            return f"```json\n{json_str}\n```"
        else:
            return str(content)

    def _format_text(self, content: Any, metadata: Optional[Dict[str, Any]] = None) -> str:
        """纯文本格式输出（默认）"""
        if isinstance(content, str):
            return content
        elif isinstance(content, (dict, list)):
            return json.dumps(content, ensure_ascii=False, indent=2)
        else:
            return str(content)

    def _format_html(self, content: Any, metadata: Optional[Dict[str, Any]] = None) -> str:
        """HTML 格式输出（待扩展）"""
        logger.warning("⚠️ HTML 格式暂未实现，回退到 markdown")
        return self._format_markdown(content, metadata)

    def validate_json(
        self, content: str, model: Optional[Type[BaseModel]] = None
    ) -> tuple[bool, Optional[Any], Optional[str]]:
        """
        校验 JSON 输出（返回校验结果）

        Args:
            content: JSON 字符串
            model: Pydantic 模型（None 使用默认）

        Returns:
            (是否通过, 校验后的数据/None, 错误信息/None)
        """
        model_to_use = model or self.pydantic_model

        if not model_to_use:
            logger.warning("⚠️ 未配置 Pydantic 模型，跳过校验")
            return True, None, None

        try:
            json_obj = json.loads(content)
            validated = model_to_use(**json_obj)
            return True, validated.model_dump(), None
        except json.JSONDecodeError as e:
            return False, None, f"JSON 解析失败: {str(e)}"
        except ValidationError as e:
            errors = e.errors()
            error_msg = "; ".join([f"{err['loc']}: {err['msg']}" for err in errors[:3]])
            return False, None, error_msg


def create_output_formatter(config=None, **kwargs) -> OutputFormatter:  # OutputFormatterConfig
    """
    创建输出格式化器（工厂函数）

    Args:
        config: OutputFormatterConfig 配置对象
        **kwargs: 直接传递的参数（覆盖 config）

    Returns:
        OutputFormatter 实例
    """
    if config:
        # 确定 Pydantic 模型
        pydantic_model = kwargs.get("pydantic_model", None)
        model_name = kwargs.get("model_name", getattr(config, "json_model_name", None))

        return OutputFormatter(
            default_format=kwargs.get("default_format", config.default_format),
            pydantic_model=pydantic_model,
            model_name=model_name,
            json_schema=kwargs.get("json_schema", config.json_schema),
            strict_json_validation=kwargs.get(
                "strict_json_validation", config.strict_json_validation
            ),
            json_ensure_ascii=kwargs.get("json_ensure_ascii", config.json_ensure_ascii),
            json_indent=kwargs.get("json_indent", config.json_indent),
            code_highlighting=kwargs.get("code_highlighting", config.code_highlighting),
            max_output_length=kwargs.get("max_output_length", config.max_output_length),
        )
    else:
        return OutputFormatter(**kwargs)
