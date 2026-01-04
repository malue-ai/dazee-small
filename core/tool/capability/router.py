"""
能力路由器 - 智能选择最合适的能力

职责：
1. 分析用户请求
2. 查找候选能力
3. 计算评分
4. 选择最佳能力

设计原则：
- 智能路由：根据请求特点选择最佳能力
- 评分算法：综合考虑优先级、匹配度、成本
- 可配置：路由规则可通过配置调整

注意：具体的工具选择使用 ToolSelector，Router 专注于评分和推荐
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import yaml

from .registry import CapabilityRegistry
from .types import Capability, CapabilityType


@dataclass
class RoutingResult:
    """路由结果"""
    capability: Capability
    score: float
    reason: str
    alternatives: List[Tuple[Capability, float]] = None  # 备选方案


class CapabilityRouter:
    """
    能力路由器
    
    智能选择最合适的能力执行用户请求
    专注于评分和推荐算法
    """
    
    def __init__(
        self,
        registry: CapabilityRegistry,
        rules_path: Optional[str] = None
    ):
        """
        初始化能力路由器
        
        Args:
            registry: 能力注册表
            rules_path: 路由规则配置文件路径
        """
        self.registry = registry
        self._rules_path = rules_path or self._default_rules_path()
        self._load_rules()
        
        # 默认类型权重
        self.type_weights = {
            CapabilityType.SKILL: 10,   # Skills 优先
            CapabilityType.TOOL: 8,
            CapabilityType.MCP: 6,
            CapabilityType.CODE: 4
        }
        
        # 默认子类型权重
        self.subtype_weights = {
            "CUSTOM": 15,      # 自定义最高
            "PREBUILT": 10,
            "NATIVE": 8,
            "EXTERNAL": 5,
            "DYNAMIC": 3
        }
    
    def _default_rules_path(self) -> str:
        """获取默认规则文件路径"""
        return str(Path(__file__).parent.parent.parent.parent / "config" / "routing_rules.yaml")
    
    def _load_rules(self):
        """加载路由规则配置"""
        rules_path = Path(self._rules_path)
        
        if not rules_path.exists():
            self.rules = {}
            return
        
        try:
            with open(rules_path, 'r', encoding='utf-8') as f:
                self.rules = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"⚠️ Warning: Failed to load routing rules: {e}")
            self.rules = {}
        
        # 更新权重（如果配置中有）
        if 'type_weights' in self.rules:
            for cap_type, weight in self.rules['type_weights'].items():
                try:
                    self.type_weights[CapabilityType(cap_type)] = weight
                except:
                    pass
        
        if 'subtype_weights' in self.rules:
            self.subtype_weights.update(self.rules['subtype_weights'])
    
    def route(
        self,
        keywords: List[str],
        task_type: str = None,
        quality_requirement: str = "medium",
        explicit_capability: str = None,
        context: Dict[str, Any] = None
    ) -> Optional[RoutingResult]:
        """
        路由到最合适的能力
        
        Args:
            keywords: 用户请求中的关键词
            task_type: 任务类型（如 ppt_generation）
            quality_requirement: 质量要求（low/medium/high）
            explicit_capability: 用户明确指定的能力名称
            context: 上下文（可用 API、网络状态等）
            
        Returns:
            RoutingResult 或 None
        """
        # 1. 如果用户明确指定，直接返回
        if explicit_capability:
            cap = self.registry.get(explicit_capability)
            if cap:
                return RoutingResult(
                    capability=cap,
                    score=10000,  # 最高分
                    reason=f"Explicitly requested: {explicit_capability}"
                )
        
        # 2. 查找候选能力
        candidates = self.registry.find_candidates(keywords, task_type, context)
        
        if not candidates:
            return None
        
        # 3. 计算评分
        scored: List[Tuple[Capability, float]] = []
        for cap in candidates:
            score = self._calculate_score(
                cap, keywords, quality_requirement, context
            )
            scored.append((cap, score))
        
        # 4. 排序
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # 5. 返回最佳结果
        best_cap, best_score = scored[0]
        
        return RoutingResult(
            capability=best_cap,
            score=best_score,
            reason=self._explain_selection(best_cap, keywords, best_score),
            alternatives=scored[1:4] if len(scored) > 1 else None
        )
    
    def _calculate_score(
        self,
        cap: Capability,
        keywords: List[str],
        quality_requirement: str,
        context: Dict[str, Any] = None
    ) -> float:
        """
        计算能力评分
        
        评分算法：
        Score = base_priority           # 基础优先级 (0-100)
              + type_weight × 5         # 类型权重
              + subtype_weight × 5      # 子类型权重
              + keyword_match × 2       # 关键词匹配
              + quality_match × 20      # 质量要求匹配
              + context_bonus           # 上下文加分
              - cost_penalty            # 成本惩罚
        """
        score = float(cap.priority)
        
        # 类型权重
        type_weight = self.type_weights.get(cap.type, 0)
        score += type_weight * 5
        
        # 子类型权重
        subtype_weight = self.subtype_weights.get(cap.subtype, 0)
        score += subtype_weight * 5
        
        # 关键词匹配
        keyword_score = cap.matches_keywords(keywords)
        score += keyword_score * 2
        
        # 质量要求匹配
        score += self._quality_match_score(cap, quality_requirement)
        
        # 上下文加分
        if context:
            score += self._context_bonus(cap, context)
        
        # 成本惩罚
        score -= self._cost_penalty(cap)
        
        return max(score, 0)
    
    def _quality_match_score(self, cap: Capability, requirement: str) -> float:
        """计算质量匹配分数"""
        quality_levels = {'low': 1, 'medium': 2, 'high': 3}
        
        min_quality = cap.constraints.get('min_quality', 'low')
        cap_quality = quality_levels.get(min_quality, 1)
        req_quality = quality_levels.get(requirement, 2)
        
        if cap_quality >= req_quality:
            return 20  # 完全满足
        elif cap_quality == req_quality - 1:
            return 10  # 部分满足
        else:
            return 0   # 不满足
    
    def _context_bonus(self, cap: Capability, context: Dict[str, Any]) -> float:
        """计算上下文加分"""
        bonus = 0
        
        # 如果能力已在使用中（上下文连续性）
        if context.get('current_capability') == cap.name:
            bonus += 15
        
        # 如果最近成功使用过（经验加分）
        recent_successes = context.get('recent_success_capabilities', [])
        if cap.name in recent_successes:
            bonus += 10
        
        return bonus
    
    def _cost_penalty(self, cap: Capability) -> float:
        """计算成本惩罚"""
        penalty = 0
        
        # 时间成本
        time_cost = cap.cost.get('time', 'fast')
        time_penalties = {'fast': 0, 'medium': 5, 'slow': 15, 'variable': 10}
        penalty += time_penalties.get(time_cost, 0)
        
        # 金钱成本
        money_cost = cap.cost.get('money', 'free')
        money_penalties = {'free': 0, 'low': 5, 'medium': 15, 'high': 30}
        penalty += money_penalties.get(money_cost, 0)
        
        return penalty
    
    def _explain_selection(
        self,
        cap: Capability,
        keywords: List[str],
        score: float
    ) -> str:
        """解释为什么选择这个能力"""
        reasons = []
        
        # 基本信息
        reasons.append(f"Type: {cap.type.value}")
        reasons.append(f"Subtype: {cap.subtype}")
        reasons.append(f"Priority: {cap.priority}")
        reasons.append(f"Total Score: {score:.1f}")
        
        # 关键词匹配
        matched_keywords = []
        for kw in keywords:
            if cap.matches_keywords([kw]) > 0:
                matched_keywords.append(kw)
        
        if matched_keywords:
            reasons.append(f"Matched: {', '.join(matched_keywords)}")
        
        # 质量信息
        min_quality = cap.constraints.get('min_quality', 'N/A')
        reasons.append(f"Quality: {min_quality}")
        
        return " | ".join(reasons)
    
    def route_multiple(
        self,
        keywords: List[str],
        task_type: str = None,
        top_k: int = 3,
        context: Dict[str, Any] = None
    ) -> List[RoutingResult]:
        """
        返回前 K 个最佳能力
        
        Args:
            keywords: 关键词列表
            task_type: 任务类型
            top_k: 返回数量
            context: 上下文
            
        Returns:
            RoutingResult 列表
        """
        candidates = self.registry.find_candidates(keywords, task_type, context)
        
        scored = []
        for cap in candidates:
            score = self._calculate_score(cap, keywords, "medium", context)
            scored.append(RoutingResult(
                capability=cap,
                score=score,
                reason=self._explain_selection(cap, keywords, score)
            ))
        
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]
    
    def suggest_capability_type(
        self,
        task_description: str,
        data_volume: str = "small",
        call_frequency: int = 1,
        needs_validation: bool = False
    ) -> str:
        """
        根据任务特点建议使用哪种能力类型
        
        Args:
            task_description: 任务描述
            data_volume: 数据量 (small/medium/large)
            call_frequency: 工具调用次数预估
            needs_validation: 是否需要验证
            
        Returns:
            建议的能力类型描述
        """
        suggestions = []
        
        # 基于调用次数决策
        if call_frequency == 1:
            suggestions.append("Direct Function Call (单次调用)")
        elif call_frequency >= 3:
            suggestions.append("Programmatic Tool Call (批量调用)")
        
        # 基于数据量决策
        if data_volume == "large":
            suggestions.append("Code Execution (大数据处理)")
        
        # 基于验证需求
        if needs_validation:
            suggestions.append("Agent Skills (需要验证规范)")
        
        # 检查是否是复杂工作流
        complex_keywords = ['ppt', 'presentation', 'report', 'excel', '专业', '复杂']
        if any(kw in task_description.lower() for kw in complex_keywords):
            suggestions.insert(0, "Agent Skills (复杂工作流)")
        
        if not suggestions:
            suggestions.append("Direct Function Call (默认)")
        
        return " → ".join(suggestions)


# ==================== 便捷函数 ====================

def create_capability_router(
    registry: CapabilityRegistry = None,
    rules_path: str = None
) -> CapabilityRouter:
    """
    创建能力路由器
    
    Args:
        registry: 能力注册表（如果为 None 则自动创建）
        rules_path: 路由规则配置路径
        
    Returns:
        配置好的 CapabilityRouter 实例
    """
    if registry is None:
        from .registry import create_capability_registry
        registry = create_capability_registry()
    
    return CapabilityRouter(registry=registry, rules_path=rules_path)


def extract_keywords(text: str) -> List[str]:
    """
    从文本中提取关键词
    
    Args:
        text: 输入文本
        
    Returns:
        关键词列表
    """
    keywords = []
    text_lower = text.lower()
    
    # 常见关键词模式
    keyword_patterns = [
        # PPT 相关
        "ppt", "presentation", "slides", "演示", "幻灯片", "slidespeak",
        # Excel 相关
        "excel", "spreadsheet", "数据分析", "表格", "xlsx",
        # 文档相关
        "document", "word", "文档", "docx",
        # PDF 相关
        "pdf", "报告",
        # 搜索相关
        "search", "搜索", "查询", "查找",
        # 代码相关
        "code", "代码", "程序", "脚本",
        # 规划相关
        "plan", "规划", "计划", "任务",
        # 质量相关
        "专业", "高质量", "professional", "business",
        # 产品相关
        "产品", "product", "介绍", "客户"
    ]
    
    for kw in keyword_patterns:
        if kw in text_lower:
            keywords.append(kw)
    
    return keywords

