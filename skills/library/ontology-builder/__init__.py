"""
系统配置构建 Skill

基于 Dify Workflow API 实现三阶段原子操作：
1. text2flowchart: 自然语言 → Mermaid 流程图
2. build_ontology_part1: 预处理
3. build_ontology_part2: 生成最终配置
"""

from .scripts.build_ontology import (
    OntologyBuilder,
    DifyWorkflowClient,
    text_to_flowchart,
    build_ontology_part1,
    build_ontology_part2,
    build_ontology_full,
    build_ontology_from_chart,
    get_config_info,
    SKILL_NAME,
    SKILL_VERSION,
)

__all__ = [
    # 主要类
    "OntologyBuilder",
    "DifyWorkflowClient",
    # 便捷函数
    "text_to_flowchart",
    "build_ontology_part1",
    "build_ontology_part2",
    "build_ontology_full",
    "build_ontology_from_chart",
    # 工具函数
    "get_config_info",
    # 元数据
    "SKILL_NAME",
    "SKILL_VERSION",
]
