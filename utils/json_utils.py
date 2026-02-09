"""
通用 JSON 提取与修复工具

用于从 LLM 响应中提取和解析 JSON 数据
"""

import json
import re
from typing import Any, Dict, List, Optional, Union

import json5

from logger import get_logger

logger = get_logger("json_utils")


class JSONExtractor:
    """
    JSON 提取器

    从 AI/LLM 响应中提取和修复 JSON 数据

    使用示例：
        text = '''根据你的需求，我生成了以下问题：
        ```json
        {"questions": ["问题1", "问题2", "问题3"]}
        ```
        '''
        result = JSONExtractor.process_response(text)
        # result = {"questions": ["问题1", "问题2", "问题3"]}
    """

    @staticmethod
    def process_response(text: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
        """
        从给定文本中提取最可能的 JSON 数据，并尝试解析与修复

        步骤：
          1. 提取 JSON 块
          2. 尝试 json.loads
          3. 尝试 json5.loads（如果可用）
          4. 自定义修复后再尝试 json.loads
          5. 失败则返回 None

        Args:
            text: 包含 JSON 的文本

        Returns:
            解析后的 JSON 对象，或 None（解析失败时）
        """
        raw = JSONExtractor.extract_json_block(text)
        if raw is None or raw.strip() == "":
            logger.debug("JSON 块未找到或为空")
            return None

        logger.debug(f"提取的 JSON 块 (前200字符): {raw[:200]}...")

        # 1. 直接解析
        try:
            result = json.loads(raw)
            logger.debug("✅ json.loads 解析成功")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"json.loads 失败: {e}，尝试 json5...")

        # 2. 宽松解析（json5）
        try:
            result = json5.loads(raw)
            logger.debug("✅ json5.loads 解析成功")
            return result
        except ImportError:
            logger.debug("json5 未安装，跳过")
        except Exception as e:
            logger.debug(f"json5.loads 失败: {e}，尝试修复...")

        # 3. 自定义修复
        result = JSONExtractor._repair_and_load(raw)
        if result is not None:
            logger.debug("✅ 修复后解析成功")
        else:
            # 降级为 DEBUG：JSON 解析失败是预期场景，调用方会处理 None 返回值
            logger.debug("JSON 解析失败，返回 None（调用方会处理）")
        return result

    @staticmethod
    def extract_json_block(text: str) -> Optional[str]:
        """
        提取 JSON 块

        优先级：
          1. ```json ... ``` 代码块
          2. { ... } 或 [ ... ] 直接匹配
          3. 全文作为 JSON 尝试

        Args:
            text: 原始文本

        Returns:
            提取的 JSON 字符串
        """
        # 1. 优先匹配 ```json ... ``` 格式
        # 使用贪婪匹配 .* 确保提取完整的 JSON（包含嵌套的 [] 和 {}）
        triple_pattern = re.compile(r"```json\s*([\{\[].*[\}\]])\s*```", re.DOTALL)
        m = triple_pattern.search(text)
        if m:
            return m.group(1).strip()

        # 2. 匹配 ``` ... ``` 格式（不带 json 标记）
        generic_pattern = re.compile(r"```\s*([\{\[].*[\}\]])\s*```", re.DOTALL)
        m = generic_pattern.search(text)
        if m:
            return m.group(1).strip()

        # 3. 直接匹配 { ... } 或 [ ... ]
        # 找到第一个 { 或 [ 和最后一个 } 或 ]
        first_brace = -1
        last_brace = -1

        for i, char in enumerate(text):
            if char in "{[" and first_brace == -1:
                first_brace = i
            if char in "}]":
                last_brace = i

        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace : last_brace + 1].strip()

        # 4. 未匹配到，直接返回全文
        return text.strip()

    @staticmethod
    def _repair_and_load(raw: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
        """
        修复常见的 JSON 问题并尝试加载

        修复的问题：
          - BOM 字符
          - 未闭合的字符串
          - 单引号 -> 双引号
          - 未加引号的 key
          - 尾随逗号
        """
        s = raw.lstrip("\ufeff")
        s = JSONExtractor._fix_unclosed_strings(s)

        # 单引号 -> 双引号
        s = s.replace("'", '"')

        # 给 key 添加双引号
        s = re.sub(r"([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', s)

        # 移除尾随逗号
        s = re.sub(r",\s*([}\]])", r"\1", s)

        try:
            return json.loads(s)
        except Exception as e:
            logger.debug(f"JSON 修复后仍然失败: {e}")
            return None

    @staticmethod
    def _fix_unclosed_strings(text: str) -> str:
        """
        简单修复未闭合的字符串并转义换行符
        """
        lines = text.splitlines()
        out = []
        for line in lines:
            line_stripped = line.rstrip()
            # 如果行以一个引号开始但未闭合，补上闭合引号
            if re.match(r'^\s*"[^"]+$', line_stripped):
                line_stripped += '"'
            # 转义换行
            line_stripped = line_stripped.replace("\n", "\\n")
            out.append(line_stripped)
        return "\n".join(out)

    @staticmethod
    def extract_list(text: str, key: Optional[str] = None) -> List[str]:
        """
        便捷方法：从文本中提取字符串列表

        Args:
            text: 包含 JSON 的文本
            key: 如果 JSON 是对象，指定要提取的 key

        Returns:
            字符串列表（解析失败返回空列表）

        示例：
            # 直接数组
            extract_list('["a", "b", "c"]')  # ["a", "b", "c"]

            # 带 key 的对象
            extract_list('{"questions": ["a", "b"]}', key="questions")  # ["a", "b"]
        """
        result = JSONExtractor.process_response(text)

        if result is None:
            return []

        # 如果是列表，直接返回
        if isinstance(result, list):
            return [str(item) for item in result]

        # 如果是对象且指定了 key
        if isinstance(result, dict) and key:
            value = result.get(key, [])
            if isinstance(value, list):
                return [str(item) for item in value]

        return []


def extract_json(text: str) -> Optional[Union[Dict[str, Any], List[Any]]]:
    """
    便捷函数：从文本中提取 JSON

    Args:
        text: 包含 JSON 的文本

    Returns:
        解析后的 JSON 对象
    """
    return JSONExtractor.process_response(text)


def extract_json_list(text: str, key: Optional[str] = None) -> List[str]:
    """
    便捷函数：从文本中提取字符串列表

    Args:
        text: 包含 JSON 的文本
        key: 如果 JSON 是对象，指定要提取的 key

    Returns:
        字符串列表
    """
    return JSONExtractor.extract_list(text, key)
