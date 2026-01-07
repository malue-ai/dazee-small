"""
Capability 类型定义

包含：
- CapabilityType (枚举)
- CapabilitySubtype (枚举)
- Capability (数据类)

这些类型被 Registry、Router、Selector、Executor 共享使用。
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional


class CapabilityType(Enum):
    """能力类型"""
    SKILL = "SKILL"    # 领域知识包（SKILL.md + scripts）
    TOOL = "TOOL"      # 预定义函数
    MCP = "MCP"        # MCP 服务器
    CODE = "CODE"      # 动态代码执行


class CapabilitySubtype(Enum):
    """能力子类型"""
    PREBUILT = "PREBUILT"    # Anthropic 预置
    CUSTOM = "CUSTOM"        # 用户自定义
    NATIVE = "NATIVE"        # 系统原生
    EXTERNAL = "EXTERNAL"    # 外部服务
    DYNAMIC = "DYNAMIC"      # 动态生成


@dataclass
class Capability:
    """
    统一能力定义
    
    抽象所有执行方式（Skills/Tools/MCP/Code）
    """
    name: str
    type: CapabilityType
    subtype: str
    provider: str
    capabilities: List[str]      # 能力标签（如 ppt_generation, data_analysis）
    priority: int                # 基础优先级 0-100
    cost: Dict[str, str]         # 成本 {time: fast/medium/slow, money: free/low/high}
    constraints: Dict[str, Any]  # 约束条件
    metadata: Dict[str, Any]     # 扩展信息（description, keywords, preferred_for 等）
    input_schema: Optional[Dict] = None  # 工具输入 Schema（用于 Claude API）
    fallback_tool: Optional[str] = None  # 替代工具（SKILL 无法执行时使用的 TOOL）
    skill_id: Optional[str] = None       # 🆕 Claude Skill ID（注册后由 Claude 返回）
    skill_path: Optional[str] = None     # 🆕 Skill 本地路径（用于注册）
    
    # 🆕 工具分层配置（V4.2.4）
    level: int = 2                       # 工具层级：1=核心（始终加载）, 2=动态（按需加载）
    cache_stable: bool = False           # 结果是否稳定可缓存（同输入同输出）
    
    def matches_keywords(self, keywords: List[str]) -> int:
        """
        计算关键词匹配度
        
        Args:
            keywords: 待匹配的关键词列表
            
        Returns:
            匹配分数（越高越匹配）
        """
        if not keywords:
            return 0
            
        score = 0
        cap_keywords = self.metadata.get('keywords', [])
        preferred_for = self.metadata.get('preferred_for', [])
        description = self.metadata.get('description', '')
        
        for kw in keywords:
            kw_lower = kw.lower()
            
            # 能力标签匹配（权重最高）
            if any(kw_lower in str(c).lower() for c in self.capabilities):
                score += 15
            
            # preferred_for 匹配（权重高）
            if any(kw_lower in str(p).lower() for p in preferred_for):
                score += 10
            
            # keywords 匹配（权重中）
            if any(kw_lower in str(k).lower() for k in cap_keywords):
                score += 5
            
            # description 匹配（权重低）
            if kw_lower in description.lower():
                score += 2
            
            # 名称匹配（权重中）
            if kw_lower in self.name.lower():
                score += 8
        
        return score
    
    def meets_constraints(self, context: Dict[str, Any] = None) -> bool:
        """
        检查是否满足约束条件
        
        Args:
            context: 当前上下文（如可用的 API、网络状态等）
            
        Returns:
            是否满足约束
        """
        if not context:
            return True
        
        # 检查 API 依赖
        if self.constraints.get('requires_api'):
            api_name = self.constraints.get('api_name')
            available_apis = context.get('available_apis', [])
            if api_name and api_name not in available_apis:
                return False
        
        # 检查网络依赖
        if self.constraints.get('requires_network'):
            if not context.get('network_available', True):
                return False
        
        # 检查认证依赖
        if self.constraints.get('requires_auth'):
            if not context.get('authenticated', False):
                return False
        
        return True
    
    def to_tool_schema(self) -> Optional[Dict]:
        """
        转换为 Claude API 的 tool schema 格式
        
        Returns:
            符合 Claude API 规范的 tool schema，或 None
        """
        if self.type != CapabilityType.TOOL:
            return None
        
        if not self.input_schema:
            return None
        
        return {
            "name": self.name,
            "description": self.metadata.get('description', self.name),
            "input_schema": self.input_schema
        }

