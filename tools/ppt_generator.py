"""
高质量闭环 PPT 生成工具

完整流程：
1. 需求分析 - 解析主题、受众、风格、时间范围
2. 素材搜集 - 自动搜索相关资料（可选）
3. 内容规划 - 生成大纲和每页结构
4. PPT 渲染 - 调用 SlideSpeak API
5. 质量检查 - 验证内容完整性
6. 交付 - 返回文件路径

配置说明：
- input_schema 在 config/capabilities.yaml 中定义
- 运营可直接修改 YAML 调整参数，无需改代码
"""

import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from core.tool.base import BaseTool, ToolContext
from logger import get_logger

logger = get_logger(__name__)


class PPTGeneratorTool(BaseTool):
    """
    高质量闭环 PPT 生成工具（input_schema 由 capabilities.yaml 定义）
    
    整合素材搜索、内容规划、PPT渲染的完整流程。
    """
    
    name = "ppt_generator"
    
    def __init__(self):
        """初始化工具"""
        self.slidespeak_api_key = os.getenv("SLIDESPEAK_API_KEY")
        self.exa_api_key = os.getenv("EXA_API_KEY")
        
        # 依赖的工具（延迟加载）
        self._slidespeak_tool = None
        self._exa_tool = None
    
    async def execute(
        self,
        params: Dict[str, Any],
        context: ToolContext
    ) -> Dict[str, Any]:
        """
        执行高质量PPT生成
        
        Args:
            params: 工具输入参数（由 capabilities.yaml 定义）
            context: 工具执行上下文
            
        完整流程：
        1. 需求分析
        2. 素材搜集（如果提供search_queries）
        3. 内容规划
        4. PPT渲染
        5. 质量检查
        6. 交付
        """
        # 从 params 提取参数
        topic = params.get("topic", "")
        if not topic:
            return {"success": False, "error": "缺少必需参数: topic"}
        
        description = params.get("description")
        search_queries = params.get("search_queries")
        style = params.get("style", "professional")
        slide_count = params.get("slide_count")
        language = params.get("language", "ORIGINAL")
        time_context = params.get("time_context")
        audience = params.get("audience")
        custom_outline = params.get("custom_outline")
        include_charts = params.get("include_charts", True)
        include_images = params.get("include_images", True)
        materials = params.get("materials")
        
        # 从 context 获取 conversation_id
        conversation_id = context.conversation_id
        
        result = {
            "status": "pending",
            "topic": topic,
            "phases": {},
            "warnings": [],
            "errors": []
        }
        
        try:
            # ========== Phase 1: 需求分析 ==========
            result["phases"]["requirement_analysis"] = {
                "status": "in_progress",
                "started_at": datetime.now().isoformat()
            }
            
            requirement = self._analyze_requirement(
                topic=topic,
                description=description,
                style=style,
                slide_count=slide_count,
                audience=audience,
                time_context=time_context,
                custom_outline=custom_outline
            )
            
            result["phases"]["requirement_analysis"]["status"] = "completed"
            result["phases"]["requirement_analysis"]["requirement"] = requirement
            
            # ========== Phase 2: 素材搜集（可选）==========
            collected_materials = materials or []
            
            if search_queries and len(search_queries) > 0:
                result["phases"]["material_collection"] = {
                    "status": "in_progress",
                    "queries": search_queries,
                    "started_at": datetime.now().isoformat()
                }
                
                search_results = await self._collect_materials(
                    queries=search_queries,
                    time_context=time_context
                )
                
                collected_materials.extend(search_results)
                
                result["phases"]["material_collection"]["status"] = "completed"
                result["phases"]["material_collection"]["materials_count"] = len(search_results)
                result["phases"]["material_collection"]["materials"] = search_results[:5]  # 只存前5个
            
            # ========== Phase 3: 内容规划 ==========
            result["phases"]["content_planning"] = {
                "status": "in_progress",
                "started_at": datetime.now().isoformat()
            }
            
            slides_config = self._plan_content(
                requirement=requirement,
                materials=collected_materials,
                include_charts=include_charts
            )
            
            result["phases"]["content_planning"]["status"] = "completed"
            result["phases"]["content_planning"]["slides_count"] = len(slides_config)
            
            # ========== Phase 4: PPT渲染 ==========
            result["phases"]["ppt_rendering"] = {
                "status": "in_progress",
                "started_at": datetime.now().isoformat()
            }
            
            # 构建 SlideSpeak 配置
            slidespeak_config = self._build_slidespeak_config(
                requirement=requirement,
                slides=slides_config,
                language=language,
                include_images=include_images
            )
            
            # 调用 SlideSpeak 渲染
            render_result = await self._render_ppt(
                config=slidespeak_config,
                conversation_id=conversation_id
            )
            
            if not render_result.get("success"):
                result["phases"]["ppt_rendering"]["status"] = "failed"
                result["phases"]["ppt_rendering"]["error"] = render_result.get("error")
                result["status"] = "failed"
                result["errors"].append(f"PPT渲染失败: {render_result.get('error')}")
                return result
            
            result["phases"]["ppt_rendering"]["status"] = "completed"
            result["phases"]["ppt_rendering"]["download_url"] = render_result.get("download_url")
            result["phases"]["ppt_rendering"]["local_path"] = render_result.get("local_path")
            
            # ========== Phase 5: 质量检查 ==========
            result["phases"]["quality_check"] = {
                "status": "in_progress",
                "started_at": datetime.now().isoformat()
            }
            
            quality_result = self._check_quality(
                requirement=requirement,
                slides_config=slides_config,
                render_result=render_result
            )
            
            result["phases"]["quality_check"]["status"] = "completed"
            result["phases"]["quality_check"]["score"] = quality_result["score"]
            result["phases"]["quality_check"]["checks"] = quality_result["checks"]
            
            if quality_result["warnings"]:
                result["warnings"].extend(quality_result["warnings"])
            
            # ========== Phase 6: 交付 ==========
            result["status"] = "success"
            result["output"] = {
                "download_url": render_result.get("download_url"),
                "local_path": render_result.get("local_path"),
                "slides_count": len(slides_config) + 2,  # +封面+结尾
                "quality_score": quality_result["score"],
                "style": style,
                "language": language
            }
            
            # 生成摘要
            result["summary"] = self._generate_summary(result)
            
            return result
            
        except Exception as e:
            result["status"] = "error"
            result["errors"].append(str(e))
            return result
    
    def _analyze_requirement(
        self,
        topic: str,
        description: Optional[str],
        style: str,
        slide_count: Optional[int],
        audience: Optional[str],
        time_context: Optional[str],
        custom_outline: Optional[List[str]]
    ) -> Dict[str, Any]:
        """
        分析需求，提取关键信息
        """
        # 推断幻灯片数量
        if slide_count:
            target_slides = slide_count
        elif custom_outline:
            target_slides = len(custom_outline)
        else:
            # 根据主题复杂度估算
            topic_words = len(topic.split())
            target_slides = min(max(8, topic_words * 2), 15)
        
        # 推断时间范围
        year_context = time_context
        if not year_context:
            # 默认使用当前年份
            current_year = datetime.now().year
            year_context = f"{current_year}年"
        
        return {
            "topic": topic,
            "description": description or f"关于{topic}的专业演示文稿",
            "style": style,
            "target_slides": target_slides,
            "audience": audience or "通用",
            "time_context": year_context,
            "custom_outline": custom_outline,
            "template_mapping": self._get_template_for_style(style)
        }
    
    def _get_template_for_style(self, style: str) -> str:
        """根据风格返回模板名称"""
        template_map = {
            "professional": "DEFAULT",
            "academic": "MINIMALIST",
            "creative": "COLORFUL",
            "minimal": "MINIMALIST",
            "corporate": "CORPORATE"
        }
        return template_map.get(style, "DEFAULT")
    
    async def _collect_materials(
        self,
        queries: List[str],
        time_context: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        搜索并收集素材
        """
        materials = []
        
        # 延迟导入 exa_search
        if self._exa_tool is None:
            try:
                from tools.exa_search import ExaSearchTool
                self._exa_tool = ExaSearchTool()
            except Exception as e:
                # 如果 exa 不可用，返回空
                return materials
        
        # 为每个查询添加时间上下文
        from core.tool.base import create_tool_context
        
        for query in queries[:5]:  # 最多5个查询
            search_query = query
            if time_context:
                search_query = f"{query} {time_context}"
            
            try:
                result = await self._exa_tool.execute(
                    params={"query": search_query, "num_results": 5, "include_text": True},
                    context=create_tool_context()
                )
                
                if result.get("success"):
                    for item in result.get("results", [])[:3]:
                        materials.append({
                            "title": item.get("title", ""),
                            "content": item.get("text", "")[:500],  # 截取前500字
                            "source": item.get("url", ""),
                            "date": item.get("published_date", ""),
                            "query": query
                        })
            except Exception:
                continue
        
        return materials
    
    def _plan_content(
        self,
        requirement: Dict[str, Any],
        materials: List[Dict[str, Any]],
        include_charts: bool
    ) -> List[Dict[str, Any]]:
        """
        规划PPT内容结构
        
        返回 slides 配置列表
        """
        slides = []
        topic = requirement["topic"]
        target_slides = requirement["target_slides"]
        custom_outline = requirement.get("custom_outline")
        
        # 如果有自定义大纲，按大纲生成
        if custom_outline:
            for i, section in enumerate(custom_outline):
                slides.append(self._create_slide_config(
                    title=section,
                    content=self._generate_content_for_section(section, materials),
                    layout="ITEMS",
                    item_amount=4
                ))
        else:
            # 自动生成大纲
            standard_structure = self._generate_standard_structure(topic, target_slides)
            
            for section in standard_structure:
                layout = section.get("layout", "ITEMS")
                item_amount = section.get("item_amount", 4)
                
                # 从素材中提取相关内容
                relevant_content = self._extract_relevant_content(
                    section["title"],
                    materials
                )
                
                slides.append(self._create_slide_config(
                    title=section["title"],
                    content=relevant_content or section.get("default_content", ""),
                    layout=layout,
                    item_amount=item_amount,
                    chart=section.get("chart") if include_charts else None
                ))
        
        return slides
    
    def _generate_standard_structure(self, topic: str, target_slides: int) -> List[Dict[str, Any]]:
        """
        生成标准PPT结构
        """
        # 基础结构模板
        base_structure = [
            {"title": f"{topic}概述", "layout": "ITEMS", "item_amount": 4},
            {"title": "背景与现状", "layout": "ITEMS", "item_amount": 4},
            {"title": "核心要点", "layout": "ITEMS", "item_amount": 5},
            {"title": "数据分析", "layout": "CHART", "item_amount": 0, "chart": {
                "type": "BAR",
                "title": "关键数据",
                "labels": ["指标1", "指标2", "指标3", "指标4"],
                "datasets": [{"name": "数据", "values": [65, 78, 85, 72]}]
            }},
            {"title": "发展趋势", "layout": "TIMELINE", "item_amount": 4},
            {"title": "挑战与机遇", "layout": "COMPARISON", "item_amount": 2},
            {"title": "实施建议", "layout": "ITEMS", "item_amount": 4},
            {"title": "总结", "layout": "ITEMS", "item_amount": 3}
        ]
        
        # 根据目标数量调整
        if target_slides < len(base_structure):
            # 删除一些非核心页
            priority_order = [0, 2, 3, 7, 1, 4, 5, 6]  # 按重要性排序
            selected_indices = sorted(priority_order[:target_slides])
            return [base_structure[i] for i in selected_indices]
        elif target_slides > len(base_structure):
            # 添加更多详细页
            extra_slides = target_slides - len(base_structure)
            for i in range(extra_slides):
                base_structure.insert(3 + i, {
                    "title": f"深入分析 {i+1}",
                    "layout": "ITEMS",
                    "item_amount": 4
                })
        
        return base_structure
    
    def _create_slide_config(
        self,
        title: str,
        content: str,
        layout: str,
        item_amount: int,
        chart: Optional[Dict] = None,
        images: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """创建单页幻灯片配置"""
        config = {
            "title": title,
            "layout": layout,
            "item_amount": item_amount,
            "content": content
        }
        
        if chart:
            config["chart"] = chart
        
        if images:
            config["images"] = images
        
        return config
    
    def _generate_content_for_section(
        self,
        section_title: str,
        materials: List[Dict[str, Any]]
    ) -> str:
        """为特定章节生成内容"""
        relevant = self._extract_relevant_content(section_title, materials)
        if relevant:
            return relevant
        
        # 默认内容
        return f"关于{section_title}的详细内容。请根据实际情况补充具体信息。"
    
    def _extract_relevant_content(
        self,
        section_title: str,
        materials: List[Dict[str, Any]]
    ) -> str:
        """从素材中提取与章节相关的内容"""
        if not materials:
            return ""
        
        # 简单的关键词匹配（实际应用中可以使用更复杂的相关性算法）
        keywords = section_title.lower().split()
        relevant_pieces = []
        
        for material in materials:
            content = material.get("content", "").lower()
            title = material.get("title", "").lower()
            
            # 计算相关性分数
            score = sum(1 for kw in keywords if kw in content or kw in title)
            
            if score > 0:
                relevant_pieces.append({
                    "content": material.get("content", ""),
                    "score": score
                })
        
        # 按相关性排序，取前2个
        relevant_pieces.sort(key=lambda x: x["score"], reverse=True)
        
        # 组合内容
        combined = []
        for piece in relevant_pieces[:2]:
            # 提取关键句子（简化处理）
            sentences = piece["content"].split("。")[:3]
            combined.extend(sentences)
        
        return "。".join(combined) if combined else ""
    
    def _build_slidespeak_config(
        self,
        requirement: Dict[str, Any],
        slides: List[Dict[str, Any]],
        language: str,
        include_images: bool
    ) -> Dict[str, Any]:
        """构建 SlideSpeak API 配置"""
        config = {
            "template": requirement.get("template_mapping", "DEFAULT"),
            "language": language,
            "fetch_images": include_images,
            "verbosity": "standard",
            "include_cover": True,
            "include_table_of_contents": True,
            "add_speaker_notes": False,
            "slides": slides
        }
        
        # 添加封面信息
        config["title"] = requirement["topic"]
        
        return config
    
    async def _render_ppt(
        self,
        config: Dict[str, Any],
        conversation_id: Optional[str]
    ) -> Dict[str, Any]:
        """调用 SlideSpeak 渲染 PPT"""
        # 延迟加载 SlideSpeak 工具
        if self._slidespeak_tool is None:
            try:
                from tools.slidespeak import SlideSpeakTool
                self._slidespeak_tool = SlideSpeakTool()
            except Exception as e:
                return {"success": False, "error": f"SlideSpeak工具初始化失败: {str(e)}"}
        
        try:
            from core.tool.base import create_tool_context
            result = await self._slidespeak_tool.execute(
                params={"config": config},
                context=create_tool_context(conversation_id=conversation_id)
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _check_quality(
        self,
        requirement: Dict[str, Any],
        slides_config: List[Dict[str, Any]],
        render_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        质量检查
        """
        checks = {
            "slides_count": False,
            "content_completeness": False,
            "structure_coherence": False,
            "file_generated": False
        }
        warnings = []
        
        # 1. 检查幻灯片数量
        actual_slides = len(slides_config)
        target_slides = requirement.get("target_slides", 8)
        
        if abs(actual_slides - target_slides) <= 2:
            checks["slides_count"] = True
        else:
            warnings.append(f"幻灯片数量({actual_slides})与预期({target_slides})偏差较大")
        
        # 2. 检查内容完整性
        empty_slides = sum(1 for s in slides_config if not s.get("content"))
        if empty_slides == 0:
            checks["content_completeness"] = True
        else:
            warnings.append(f"有{empty_slides}页内容为空")
        
        # 3. 检查结构连贯性
        has_intro = any("概述" in s.get("title", "") or "背景" in s.get("title", "") for s in slides_config)
        has_conclusion = any("总结" in s.get("title", "") or "建议" in s.get("title", "") for s in slides_config)
        
        if has_intro and has_conclusion:
            checks["structure_coherence"] = True
        else:
            if not has_intro:
                warnings.append("缺少概述/背景部分")
            if not has_conclusion:
                warnings.append("缺少总结/建议部分")
        
        # 4. 检查文件生成
        if render_result.get("success") and render_result.get("local_path"):
            checks["file_generated"] = True
        else:
            warnings.append("文件生成可能存在问题")
        
        # 计算总分
        passed = sum(1 for v in checks.values() if v)
        total = len(checks)
        score = round(passed / total * 100)
        
        return {
            "score": score,
            "checks": checks,
            "warnings": warnings
        }
    
    def _generate_summary(self, result: Dict[str, Any]) -> str:
        """生成执行摘要"""
        if result["status"] != "success":
            return f"PPT生成失败: {', '.join(result.get('errors', ['未知错误']))}"
        
        output = result.get("output", {})
        phases = result.get("phases", {})
        
        summary_parts = [
            f"✅ PPT生成成功",
            f"📊 幻灯片数量: {output.get('slides_count', 'N/A')}页",
            f"🎨 风格: {output.get('style', 'N/A')}",
            f"⭐ 质量评分: {output.get('quality_score', 'N/A')}分"
        ]
        
        # 添加素材搜集信息
        if "material_collection" in phases:
            mc = phases["material_collection"]
            summary_parts.append(f"🔍 搜索素材: {mc.get('materials_count', 0)}条")
        
        # 添加文件路径
        if output.get("local_path"):
            summary_parts.append(f"📁 文件路径: {output['local_path']}")
        
        # 添加警告
        if result.get("warnings"):
            summary_parts.append(f"⚠️ 警告: {len(result['warnings'])}条")
        
        return "\n".join(summary_parts)


# 便捷工厂函数
def create_ppt_generator() -> PPTGeneratorTool:
    """创建PPT生成器实例"""
    return PPTGeneratorTool()


