"""
ResultCompactor - 工具结果精简器

职责：
1. 根据工具类型和结果大小选择精简策略
2. 将大结果转换为引用或摘要
3. 保留原始结果的访问路径

核心思想：
- 工具结果应该是"指针"而非"内容"
- LLM 需要时通过工具显式读取
- 避免 context 被冗余信息占据

参考：Anthropic Blog - Effective harnesses for long-running agents
"""

import json
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

from logger import get_logger

logger = get_logger(__name__)


class CompactionStrategy(Enum):
    """精简策略"""
    NONE = "none"              # 不精简（小结果）
    REFERENCE = "reference"    # 返回引用（文件、URL）
    TRUNCATE = "truncate"      # 截断（长文本）
    SUMMARIZE = "summarize"    # 总结（复杂数据）
    STRUCTURED = "structured"  # 结构化摘要（JSON、表格）
    CUSTOM = "custom"          # 自定义精简函数


@dataclass
class CompactionRule:
    """精简规则"""
    tool_name: str
    result_type: str  # "file" | "url" | "text" | "json" | "dataframe" | "search_results"
    strategy: CompactionStrategy
    max_size: int = 10000  # 最大保留大小（字符）
    summary_max_chars: int = 200  # 摘要最大字符数
    max_items: int = 10  # 列表最大保留条目数


class ResultCompactor:
    """
    工具结果精简器
    
    职责：
    1. 根据工具类型和结果大小选择精简策略
    2. 将大结果转换为引用或摘要
    3. 保留原始结果的访问路径
    
    核心思想：
    - 工具结果应该是"指针"而非"内容"
    - LLM 需要时通过工具显式读取
    - 避免 context 被冗余信息占据
    """
    
    def __init__(
        self, 
        custom_rules: Optional[Dict[str, CompactionRule]] = None,
        capability_registry = None
    ):
        """
        初始化结果精简器
        
        Args:
            custom_rules: 自定义精简规则（会覆盖默认规则）
            capability_registry: 能力注册表（从 capabilities.yaml 读取规则）
        """
        # 优先从 capabilities.yaml 加载规则
        if capability_registry:
            self.rules = self._load_rules_from_registry(capability_registry)
        else:
            self.rules = self._init_default_rules()
        
        # 自定义规则覆盖
        if custom_rules:
            self.rules.update(custom_rules)
        
        # 统计信息
        self._stats = {
            "total_compacted": 0,
            "total_bytes_saved": 0,
        }
    
    def _init_default_rules(self) -> Dict[str, CompactionRule]:
        """
        默认 Fallback 规则
        
        说明：
        - 仅作为 fallback，优先从 capabilities.yaml 加载
        - 只返回空字典，所有规则应在 capabilities.yaml 中配置
        """
        logger.warning("⚠️ 使用默认 fallback 规则（应在 capabilities.yaml 中配置 compaction）")
        return {}
    
    def _load_rules_from_registry(self, registry) -> Dict[str, CompactionRule]:
        """
        从 CapabilityRegistry 加载精简规则
        
        Args:
            registry: CapabilityRegistry 实例
            
        Returns:
            工具精简规则字典
        """
        rules = {}
        
        # 获取所有工具
        all_capabilities = registry.get_all_capabilities()
        
        for cap in all_capabilities:
            tool_name = cap.get("name")
            compaction_config = cap.get("compaction")
            
            # 如果工具没有配置 compaction，使用默认规则
            if not compaction_config:
                continue
            
            # 解析精简策略
            strategy_str = compaction_config.get("strategy", "none")
            try:
                strategy = CompactionStrategy(strategy_str)
            except ValueError:
                logger.warning(f"⚠️ 工具 {tool_name} 的 strategy '{strategy_str}' 无效，使用 NONE")
                strategy = CompactionStrategy.NONE
            
            # 创建规则
            rule = CompactionRule(
                tool_name=tool_name,
                result_type=compaction_config.get("result_type", "mixed"),
                strategy=strategy,
                max_size=compaction_config.get("max_size", 10000),
                summary_max_chars=compaction_config.get("summary_chars", 200),
                max_items=compaction_config.get("max_items", 10)
            )
            
            rules[tool_name] = rule
            logger.debug(f"📋 已加载 {tool_name} 精简规则: {strategy.value}")
        
        # 如果没有从配置加载任何规则，使用默认规则
        if not rules:
            logger.info("⚠️ 未从 capabilities.yaml 加载到精简规则，使用默认规则")
            return self._init_default_rules()
        
        logger.info(f"✅ 从 capabilities.yaml 加载了 {len(rules)} 个工具精简规则")
        return rules
    
    def compact(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        精简工具结果
        
        Args:
            tool_name: 工具名称
            result: 原始结果
            
        Returns:
            精简后的结果
        """
        # 获取精简规则
        rule = self.rules.get(tool_name)
        
        # 没有规则，应用默认策略
        if not rule:
            return self._default_compact(tool_name, result)
        
        # 估算原始大小
        original_size = self._estimate_size(result)
        
        # 结果很小，不需要精简
        if rule.strategy != CompactionStrategy.CUSTOM and original_size <= rule.max_size:
            return result
        
        # 根据策略精简
        compacted = result
        
        if rule.strategy == CompactionStrategy.REFERENCE:
            compacted = self._compact_as_reference(tool_name, result)
        
        elif rule.strategy == CompactionStrategy.TRUNCATE:
            compacted = self._compact_by_truncate(result, rule.max_size)
        
        elif rule.strategy == CompactionStrategy.STRUCTURED:
            compacted = self._compact_as_structured(result, rule.max_size, rule.max_items)
        
        elif rule.strategy == CompactionStrategy.CUSTOM:
            # 搜索工具使用自定义精简
            compacted = self._compact_search_results(tool_name, result, rule)
        
        # 记录精简效果
        compacted_size = self._estimate_size(compacted)
        if original_size != compacted_size:
            self._stats["total_compacted"] += 1
            self._stats["total_bytes_saved"] += (original_size - compacted_size)
            
            reduction = (1 - compacted_size / original_size) * 100 if original_size > 0 else 0
            logger.info(
                f"🔧 Result compacted: {tool_name} "
                f"{original_size} → {compacted_size} bytes "
                f"({reduction:.1f}% reduction)"
            )
        
        return compacted
    
    def _compact_search_results(
        self,
        tool_name: str,
        result: Dict[str, Any],
        rule: CompactionRule
    ) -> Dict[str, Any]:
        """
        搜索结果的精简策略
        
        核心思想：
        - 只返回 URL + 简短摘要（前 200 字符）
        - 不返回完整网页内容
        - LLM 需要时通过 exa_crawl 或浏览器工具显式读取
        
        精简效果：
        - 原始：10个结果 × 2000字符 = ~25KB
        - 精简后：10个结果 × 300字符 = ~3KB
        - 减少：88%
        """
        # 错误结果不精简
        if not result.get("success", True) and result.get("status") != "success":
            if "status" in result and result["status"] == "error":
                return result
        
        # 获取原始结果列表
        original_results = result.get("results", [])
        if not original_results:
            return result
        
        summary_max_chars = rule.summary_max_chars
        max_items = rule.max_items
        
        # 精简结果列表
        compacted_results = []
        for item in original_results[:max_items]:
            compacted_item = {
                "title": item.get("title", item.get("name", "")),
                "url": item.get("url", item.get("link", "")),
            }
            
            # 保留评分（如果有）
            if "score" in item:
                compacted_item["score"] = item["score"]
            
            # 只保留简短摘要（而不是完整内容）
            text_content = (
                item.get("text") or 
                item.get("content") or 
                item.get("snippet") or 
                item.get("description") or 
                ""
            )
            
            if text_content:
                text_content = text_content.strip()
                if len(text_content) > summary_max_chars:
                    compacted_item["summary"] = text_content[:summary_max_chars] + "..."
                    compacted_item["has_more_content"] = True
                else:
                    compacted_item["summary"] = text_content
                    compacted_item["has_more_content"] = False
            
            # 保留元数据（发布时间、作者等）
            if "published_date" in item or "publishedDate" in item:
                compacted_item["published_date"] = item.get("published_date") or item.get("publishedDate")
            if "author" in item:
                compacted_item["author"] = item["author"]
            
            compacted_results.append(compacted_item)
        
        # 构建精简后的结果
        compacted = {
            "success": True,
            "status": "success",
            "query": result.get("query", ""),
            "num_results": len(compacted_results),
            "results": compacted_results,
            # 添加访问提示
            "access_hint": self._get_search_access_hint(tool_name),
            # 保留元数据
            "metadata": {
                **result.get("metadata", {}),
                "compacted": True,
                "original_result_count": len(original_results),
                "summary_max_chars": summary_max_chars,
            }
        }
        
        # 保留 AI 摘要（如果有，Tavily 特有）
        if "answer" in result:
            compacted["ai_answer"] = result["answer"]
        elif result.get("raw_response", {}).get("answer"):
            compacted["ai_answer"] = result["raw_response"]["answer"]
        
        # 保留 autoprompt（Exa 特有）
        if "autoprompt" in result.get("metadata", {}):
            compacted["metadata"]["autoprompt"] = result["metadata"]["autoprompt"]
        
        return compacted
    
    def _get_search_access_hint(self, tool_name: str) -> str:
        """获取搜索工具的访问提示"""
        hints = {
            "exa_search": (
                "如需查看完整网页内容，请使用以下工具：\n"
                "- exa_crawl(url) - 使用 Exa 获取完整内容\n"
                "- browser_navigate(url) - 使用浏览器访问\n"
                "当前仅返回 URL 和摘要，以减少 context 占用"
            ),
            "exa_web_search": (
                "如需查看完整网页内容，请使用 exa_crawl(url) 获取"
            ),
            "exa_code_search": (
                "如需查看完整代码，请直接访问 URL 或使用 exa_crawl(url)"
            ),
            "tavily_search": (
                "如需查看完整网页内容，请使用 browser_navigate(url) 访问"
            ),
            "web_search": (
                "如需查看完整网页内容，请使用浏览器工具访问 URL"
            ),
        }
        return hints.get(tool_name, "如需完整内容，请通过 URL 访问")
    
    def _compact_as_reference(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        引用式精简（推荐方案）
        
        示例：
            原始: {"success": True, "content": "100KB of text..."}
            精简: {"success": True, "message": "File saved to /path/foo.txt", 
                   "reference": "file:///path/foo.txt"}
        """
        compacted = {
            "success": result.get("success", True),
            "message": self._generate_summary_message(tool_name, result)
        }
        
        # 添加引用
        if "path" in result:
            compacted["reference"] = f"file://{result['path']}"
        elif "url" in result:
            compacted["reference"] = result["url"]
        elif "id" in result:
            compacted["reference"] = f"{tool_name}://{result['id']}"
        
        # 提示 LLM 如何访问完整内容
        compacted["access_hint"] = self._generate_access_hint(tool_name, result)
        
        return compacted
    
    def _compact_by_truncate(
        self,
        result: Dict[str, Any],
        max_size: int
    ) -> Dict[str, Any]:
        """
        截断式精简
        
        保留前 N 个字符，添加截断标记
        """
        compacted = {}
        
        for key, value in result.items():
            if isinstance(value, str) and len(value) > max_size:
                truncated = value[:max_size]
                compacted[key] = truncated
                compacted[f"_{key}_truncated"] = True
                compacted[f"_{key}_original_size"] = len(value)
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                compacted[key] = self._compact_by_truncate(value, max_size)
            else:
                compacted[key] = value
        
        return compacted
    
    def _compact_as_structured(
        self,
        result: Dict[str, Any],
        max_size: int,
        max_items: int = 10
    ) -> Dict[str, Any]:
        """
        结构化摘要
        
        对于 JSON、DataFrame 等结构化数据，提取关键信息
        """
        compacted = result.copy()
        
        # 处理列表数据
        if "data" in result and isinstance(result["data"], list):
            data = result["data"]
            if len(data) > max_items:
                compacted["data"] = data[:max_items]
                compacted["_data_summary"] = {
                    "total_count": len(data),
                    "showing": max_items,
                    "truncated": True
                }
        
        # 处理 results 列表
        if "results" in result and isinstance(result["results"], list):
            results = result["results"]
            if len(results) > max_items:
                compacted["results"] = results[:max_items]
                compacted["_results_summary"] = {
                    "total_count": len(results),
                    "showing": max_items,
                    "truncated": True
                }
        
        return compacted
    
    def _generate_summary_message(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> str:
        """生成摘要消息"""
        messages = {
            "file_write": lambda r: f"File saved to {r.get('path', 'unknown path')}",
            "browser_navigate": lambda r: f"Navigated to {r.get('url', 'unknown URL')}",
            "web_search": lambda r: f"Found {len(r.get('results', []))} search results",
            "exa_search": lambda r: f"Found {len(r.get('results', []))} search results",
            "tavily_search": lambda r: f"Found {len(r.get('results', []))} search results",
        }
        
        if tool_name in messages:
            return messages[tool_name](result)
        return f"{tool_name} completed successfully"
    
    def _generate_access_hint(
        self,
        tool_name: str,
        result: Dict[str, Any]
    ) -> str:
        """生成访问提示"""
        if tool_name == "file_write" and "path" in result:
            return f"Use sandbox_read_file('{result['path']}') to access full content if needed"
        elif tool_name == "browser_navigate" and "url" in result:
            return f"Revisit {result['url']} if needed"
        return "Content available on request"
    
    def _estimate_size(self, result: Dict[str, Any]) -> int:
        """估算结果大小（字节）"""
        try:
            return len(json.dumps(result, ensure_ascii=False))
        except (TypeError, ValueError):
            return 0
    
    def _default_compact(self, tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """默认精简策略"""
        size = self._estimate_size(result)
        if size > 10000:
            logger.debug(f"Applying default truncation for {tool_name} ({size} bytes)")
            return self._compact_by_truncate(result, 10000)
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取精简统计信息"""
        return {
            **self._stats,
            "rules_count": len(self.rules),
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self._stats = {
            "total_compacted": 0,
            "total_bytes_saved": 0,
        }


# 便捷函数
def create_result_compactor(
    custom_rules: Optional[Dict[str, CompactionRule]] = None,
    capability_registry = None
) -> ResultCompactor:
    """
    创建结果精简器
    
    Args:
        custom_rules: 自定义精简规则
        capability_registry: 能力注册表（从 capabilities.yaml 自动加载规则）
        
    Returns:
        ResultCompactor 实例
    """
    return ResultCompactor(
        custom_rules=custom_rules,
        capability_registry=capability_registry
    )

