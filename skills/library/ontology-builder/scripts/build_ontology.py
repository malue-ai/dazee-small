"""
系统配置构建脚本 - 基于 Dify Workflow API

完整流程（三阶段）：
1. text2flowchart: 将自然语言描述转换为 Mermaid flowchart
2. build_ontology_part1: 预处理 Mermaid 图表
3. build_ontology_part2: 生成最终配置文件

Dify Workflow 配置：
- text2flowchart App ID: a83e8b00-a94e-4cdf-b5f7-ef721e7238c1
- Part1 App ID: 8b372c40-0b3f-4108-b7a8-3a5ef29af729
- Part2 App ID: c3046a09-1833-4914-ace3-7548844d1c35
- API Key: app-AUhGjUpkG34Su4iUAXoUZp0z

注意：
- 必须按顺序调用三个阶段
- 禁止跳过任何步骤
"""

import os
from logger import get_logger
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = get_logger(__name__)

# 脚本元数据
SKILL_NAME = "ontology_builder"
SKILL_VERSION = "1.1.0"

# ===== Dify API 配置 =====
DIFY_API_BASE_URL = os.getenv("DIFY_API_URL", "https://api.dify.ai/v1")

# 共享 API Key（如果三个 App 使用同一个 Key）
DIFY_SHARED_API_KEY = os.getenv("DIFY_ONTOLOGY_API_KEY", "app-AUhGjUpkG34Su4iUAXoUZp0z")

# text2flowchart 配置
DIFY_FLOWCHART_APP_ID = "a83e8b00-a94e-4cdf-b5f7-ef721e7238c1"
DIFY_FLOWCHART_API_KEY = os.getenv("DIFY_FLOWCHART_API_KEY", DIFY_SHARED_API_KEY)

# Part1 配置
DIFY_PART1_APP_ID = "8b372c40-0b3f-4108-b7a8-3a5ef29af729"
DIFY_PART1_API_KEY = os.getenv("DIFY_ONTOLOGY_PART1_API_KEY", DIFY_SHARED_API_KEY)

# Part2 配置
DIFY_PART2_APP_ID = "c3046a09-1833-4914-ace3-7548844d1c35"
DIFY_PART2_API_KEY = os.getenv("DIFY_ONTOLOGY_PART2_API_KEY", DIFY_SHARED_API_KEY)


class Language(Enum):
    """支持的语言"""
    ZH_CN = "zh_CN"
    EN_US = "en_US"
    AUTO = "auto"


@dataclass
class OntologyConfig:
    """系统配置构建配置"""
    query: str
    language: str = "auto"
    timeout: int = 180
    max_retries: int = 2


class DifyWorkflowClient:
    """
    Dify Workflow API 客户端
    
    文档: https://docs.dify.ai/
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = None,
        timeout: float = 300.0
    ):
        """
        初始化 Dify 客户端
        
        Args:
            api_key: Dify API 密钥
            base_url: Dify API 基础 URL
            timeout: 请求超时时间（秒）
        """
        self.api_key = api_key
        self.base_url = base_url or DIFY_API_BASE_URL
        self.timeout = timeout
        self._http_client = None
    
    async def _get_http_client(self):
        """获取 HTTP 客户端（懒加载）"""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def run_workflow(
        self,
        inputs: Dict[str, Any],
        user: str = "default_user",
        response_mode: str = "blocking"
    ) -> Dict[str, Any]:
        """
        执行 Dify Workflow
        
        Args:
            inputs: 工作流输入参数
            user: 用户标识
            response_mode: 响应模式 (blocking/streaming)
            
        Returns:
            工作流执行结果
        """
        client = await self._get_http_client()
        
        endpoint = f"{self.base_url}/workflows/run"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": inputs,
            "response_mode": response_mode,
            "user": user
        }
        
        logger.info(f"📡 调用 Dify Workflow API: {endpoint}")
        logger.debug(f"请求参数: inputs={inputs}, user={user}")
        
        try:
            response = await client.post(
                endpoint,
                json=payload,
                headers=headers
            )
            
            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Dify API 错误: {response.status_code} - {error_text}")
                raise Exception(f"Dify API 调用失败: {response.status_code} - {error_text}")
            
            result = response.json()
            logger.debug(f"Dify 响应状态: {result.get('data', {}).get('status', 'unknown')}")
            
            # 检查执行状态
            status = result.get("data", {}).get("status")
            if status == "failed":
                error = result.get("data", {}).get("error", "未知错误")
                raise Exception(f"Workflow 执行失败: {error}")
            
            return result
            
        except Exception as e:
            logger.error(f"Dify API 调用异常: {str(e)}", exc_info=True)
            raise


class OntologyBuilder:
    """
    系统配置构建器
    
    三阶段原子操作：
    1. text2flowchart (App: a83e8b00-...)：将自然语言转换为 Mermaid 图表
    2. part1 (App: 8b372c40-...)：预处理 Mermaid 图表
    3. part2 (App: c3046a09-...)：生成最终配置文件
    """
    
    def __init__(
        self,
        flowchart_api_key: str = None,
        part1_api_key: str = None,
        part2_api_key: str = None,
        base_url: str = None
    ):
        """
        初始化构建器
        
        Args:
            flowchart_api_key: text2flowchart App API 密钥
            part1_api_key: Part1 App API 密钥
            part2_api_key: Part2 App API 密钥
            base_url: Dify API 基础 URL
        """
        self.flowchart_client = DifyWorkflowClient(
            api_key=flowchart_api_key or DIFY_FLOWCHART_API_KEY,
            base_url=base_url
        )
        self.part1_client = DifyWorkflowClient(
            api_key=part1_api_key or DIFY_PART1_API_KEY,
            base_url=base_url
        )
        self.part2_client = DifyWorkflowClient(
            api_key=part2_api_key or DIFY_PART2_API_KEY,
            base_url=base_url
        )
    
    async def close(self):
        """关闭所有客户端"""
        await self.flowchart_client.close()
        await self.part1_client.close()
        await self.part2_client.close()
    
    async def text_to_flowchart(
        self,
        query: str,
        language: str = "auto",
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        步骤0：将自然语言描述转换为 Mermaid flowchart
        
        Dify App: a83e8b00-a94e-4cdf-b5f7-ef721e7238c1
        
        这个 Workflow 内置 Claude，将用户描述的业务流程转化为 Mermaid flowchart 代码。
        
        Args:
            query: 自然语言描述（业务实体、关联逻辑、流程设计等）
            language: 语言代码（zh_CN/en_US/auto）
            user_id: 用户标识
            
        Returns:
            {
                "success": bool,
                "chart_url": str,  # Mermaid 图表文件 URL
                "message": str,
                "error": str (仅失败时)
            }
        """
        logger.info(f"🎨 开始生成 Mermaid 流程图")
        logger.info(f"   App ID: {DIFY_FLOWCHART_APP_ID}")
        logger.info(f"   Query: {query[:80]}...")
        
        try:
            # 验证参数
            if not query:
                raise ValueError("缺少必需参数: query")
            if len(query) < 5:
                raise ValueError("query 太短，请提供更详细的描述")
            
            # 标准化语言代码
            language = self._normalize_language(language)
            
            # 调用 Dify Workflow - text2flowchart
            # 输入参数名需要根据实际 Workflow 配置调整
            inputs = {
                "query": query,
                "language": language
            }
            
            result = await self.flowchart_client.run_workflow(
                inputs=inputs,
                user=user_id,
                response_mode="blocking"
            )
            
            # 解析结果
            outputs = result.get("data", {}).get("outputs", {})
            
            # 尝试多种可能的输出字段名
            chart_url = (
                outputs.get("chart_url") or
                outputs.get("flowchart_url") or
                outputs.get("mermaid_url") or
                outputs.get("output") or
                outputs.get("result") or
                outputs.get("url")
            )
            
            if not chart_url:
                logger.error(f"text2flowchart 返回的 outputs: {outputs}")
                raise Exception("text2flowchart 未返回有效的图表 URL")
            
            logger.info(f"✅ Mermaid 流程图生成完成")
            logger.info(f"   图表 URL: {chart_url[:60]}...")
            
            return {
                "success": True,
                "chart_url": chart_url,
                "message": "流程图生成完成，请继续构建系统配置",
                "workflow_run_id": result.get("workflow_run_id"),
                "raw_outputs": outputs
            }
            
        except ValueError as e:
            logger.error(f"参数验证失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "参数验证失败"
            }
        except Exception as e:
            logger.error(f"text2flowchart 执行失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "流程图生成失败"
            }
    
    async def build_part1(
        self,
        chart_url: str,
        query: str,
        language: str = "auto",
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        步骤1：预处理 Mermaid 图表
        
        Dify App: 8b372c40-0b3f-4108-b7a8-3a5ef29af729
        
        Args:
            chart_url: Mermaid 图表文件 URL（来自 text2flowchart 输出）
            query: 自然语言描述，必须与 text2flowchart 的 query 一致
            language: 语言代码（zh_CN/en_US/auto）
            user_id: 用户标识
            
        Returns:
            {
                "success": bool,
                "intermediate_url": str,  # 中间结果 URL
                "message": str
            }
        """
        logger.info(f"🔧 开始构建系统配置 Part1")
        logger.info(f"   App ID: {DIFY_PART1_APP_ID}")
        
        try:
            # 验证参数
            self._validate_url_param(chart_url, "chart_url")
            if not query:
                raise ValueError("缺少必需参数: query")
            
            # 标准化语言代码
            language = self._normalize_language(language)
            
            # 调用 Dify Workflow - Part1
            inputs = {
                "chart_url": chart_url,
                "query": query,
                "language": language
            }
            
            result = await self.part1_client.run_workflow(
                inputs=inputs,
                user=user_id,
                response_mode="blocking"
            )
            
            # 解析结果
            outputs = result.get("data", {}).get("outputs", {})
            
            # Part1 输出字段名可能是 intermediate_url 或 ontology_json_url
            intermediate_url = outputs.get("ontology_json_url")  # 🆕 Dify 实际返回的字段名
            
            if not intermediate_url:
                logger.error(f"Part1 返回的 outputs: {outputs}")
                raise Exception("Part1 未返回有效的中间结果 URL")
            
            logger.info(f"✅ Part1 完成")
            logger.info(f"   中间结果 URL: {intermediate_url[:60]}...")
            
            return {
                "success": True,
                "intermediate_url": intermediate_url,
                "message": "第一阶段处理完成，请继续调用 part2",
                "workflow_run_id": result.get("workflow_run_id"),
                "raw_outputs": outputs
            }
            
        except ValueError as e:
            logger.error(f"参数验证失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "参数验证失败"
            }
        except Exception as e:
            logger.error(f"Part1 执行失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "第一阶段处理失败"
            }
    
    async def build_part2(
        self,
        intermediate_url: str,
        query: str,
        language: str = "auto",
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        步骤2：生成最终配置文件
        
        Dify App: c3046a09-1833-4914-ace3-7548844d1c35
        
        Args:
            intermediate_url: Part1 的输出 URL（中间结果）
            query: 自然语言描述，必须与 part1 的 query 一致
            language: 语言代码，必须与 part1 的 language 一致
            user_id: 用户标识
            
        Returns:
            {
                "success": bool,
                "ontology_json_url": str,  # 最终配置文件 URL
                "message": str
            }
        """
        logger.info(f"🔧 开始构建系统配置 Part2")
        logger.info(f"   App ID: {DIFY_PART2_APP_ID}")
        
        try:
            # 验证参数
            self._validate_url_param(intermediate_url, "intermediate_url")
            if not query:
                raise ValueError("缺少必需参数: query")
            
            # 标准化语言代码
            language = self._normalize_language(language)
            
            # 调用 Dify Workflow - Part2
            # 参数名根据 Dify Workflow 配置：ontology_url, query, language
            inputs = {
                "ontology_url": intermediate_url,
                "query": query,
                "language": language
            }
            
            result = await self.part2_client.run_workflow(
                inputs=inputs,
                user=user_id,
                response_mode="blocking"
            )
            
            # 解析结果
            outputs = result.get("data", {}).get("outputs", {})
            
            ontology_json_url = (
                outputs.get("ontology_json_url") 
            )
            
            if not ontology_json_url:
                logger.error(f"Part2 返回的 outputs: {outputs}")
                raise Exception("Part2 未返回有效的最终配置 URL")
            
            logger.info(f"✅ Part2 完成")
            logger.info(f"   最终配置 URL: {ontology_json_url[:60]}...")
            
            return {
                "success": True,
                "ontology_json_url": ontology_json_url,
                "message": "系统配置构建完成",
                "workflow_run_id": result.get("workflow_run_id"),
                "raw_outputs": outputs
            }
            
        except ValueError as e:
            logger.error(f"参数验证失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "message": "参数验证失败"
            }
        except Exception as e:
            logger.error(f"Part2 执行失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "第二阶段处理失败"
            }
    
    async def build_full(
        self,
        query: str,
        language: str = "auto",
        user_id: str = "default_user",
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        完整构建流程（自动执行三个阶段）
        
        流程：
        1. text2flowchart → chart_url
        2. build_part1(chart_url) → intermediate_url
        3. build_part2(intermediate_url) → ontology_json_url
        
        Args:
            query: 自然语言描述（业务流程、实体关系等）
            language: 语言代码
            user_id: 用户标识
            max_retries: 每个阶段的最大重试次数
            
        Returns:
            {
                "success": bool,
                "ontology_json_url": str,
                "chart_url": str,  # 中间产物
                "intermediate_url": str,  # 中间产物
                "message": str
            }
        """
        logger.info(f"🚀 开始完整构建流程（三阶段）")
        logger.info(f"   Query: {query[:80]}...")
        
        # 阶段 0：生成 Mermaid 流程图
        flowchart_result = await self._retry_operation(
            lambda: self.text_to_flowchart(query, language, user_id),
            max_retries=max_retries,
            stage_name="text2flowchart"
        )
        
        if not flowchart_result["success"]:
            return flowchart_result
        
        chart_url = flowchart_result["chart_url"]
        logger.info(f"📍 Step 0 完成 → chart_url: {chart_url[:50]}...")
        
        # 阶段 1：预处理
        part1_result = await self._retry_operation(
            lambda: self.build_part1(chart_url, query, language, user_id),
            max_retries=max_retries,
            stage_name="Part1"
        )
        
        if not part1_result["success"]:
            return part1_result
        
        intermediate_url = part1_result["intermediate_url"]
        logger.info(f"📍 Step 1 完成 → intermediate_url: {intermediate_url[:50]}...")
        
        # 阶段 2：生成最终配置
        part2_result = await self._retry_operation(
            lambda: self.build_part2(intermediate_url, query, language, user_id),
            max_retries=max_retries,
            stage_name="Part2"
        )
        
        if part2_result["success"]:
            logger.info(f"🎉 完整构建流程成功！")
            # 添加中间产物到结果
            part2_result["chart_url"] = chart_url
            part2_result["intermediate_url"] = intermediate_url
        
        return part2_result
    
    async def build_from_chart(
        self,
        chart_url: str,
        query: str,
        language: str = "auto",
        user_id: str = "default_user",
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        从已有的 Mermaid 图表构建（跳过 text2flowchart 阶段）
        
        适用于已经有 chart_url 的情况。
        
        流程：
        1. build_part1(chart_url) → intermediate_url
        2. build_part2(intermediate_url) → ontology_json_url
        
        Args:
            chart_url: 已有的 Mermaid 图表 URL
            query: 自然语言描述
            language: 语言代码
            user_id: 用户标识
            max_retries: 每个阶段的最大重试次数
            
        Returns:
            {
                "success": bool,
                "ontology_json_url": str,
                "message": str
            }
        """
        logger.info(f"🚀 从已有图表开始构建（两阶段）")
        logger.info(f"   Chart URL: {chart_url[:60]}...")
        
        # 阶段 1：预处理
        part1_result = await self._retry_operation(
            lambda: self.build_part1(chart_url, query, language, user_id),
            max_retries=max_retries,
            stage_name="Part1"
        )
        
        if not part1_result["success"]:
            return part1_result
        
        intermediate_url = part1_result["intermediate_url"]
        logger.info(f"📍 Part1 完成 → intermediate_url: {intermediate_url[:50]}...")
        
        # 阶段 2：生成最终配置
        part2_result = await self._retry_operation(
            lambda: self.build_part2(intermediate_url, query, language, user_id),
            max_retries=max_retries,
            stage_name="Part2"
        )
        
        if part2_result["success"]:
            logger.info(f"🎉 构建流程成功！")
        
        return part2_result
    
    # ===== 内部方法 =====
    
    def _validate_url_param(self, url: str, param_name: str) -> None:
        """验证 URL 参数"""
        if not url:
            raise ValueError(f"缺少必需参数: {param_name}")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"{param_name} 必须是有效的 HTTP/HTTPS URL")
    
    def _normalize_language(self, language: str) -> str:
        """标准化语言代码"""
        language = (language or "auto").lower().strip()
        
        mapping = {
            "zh": "zh_CN",
            "zh-cn": "zh_CN",
            "chinese": "zh_CN",
            "中文": "zh_CN",
            "en": "en_US",
            "en-us": "en_US",
            "english": "en_US",
            "英文": "en_US",
        }
        
        return mapping.get(language, language)
    
    async def _retry_operation(
        self,
        operation,
        max_retries: int,
        stage_name: str
    ) -> Dict[str, Any]:
        """带重试的操作执行"""
        last_error = None
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait_time = 2 ** attempt
                logger.warning(f"⚠️ {stage_name} 失败，{wait_time}s 后重试 ({attempt}/{max_retries})")
                await asyncio.sleep(wait_time)
            
            result = await operation()
            
            if result["success"]:
                return result
            
            last_error = result.get("error", "未知错误")
            logger.error(f"❌ {stage_name} 尝试 {attempt + 1} 失败: {last_error}")
        
        return {
            "success": False,
            "error": f"重试 {max_retries} 次后仍然失败: {last_error}",
            "message": f"{stage_name} 处理失败"
        }


# ===== 便捷函数（供外部调用） =====

async def text_to_flowchart(
    query: str,
    language: str = "auto",
    user_id: str = "default_user",
    api_key: str = None
) -> Dict[str, Any]:
    """
    将自然语言描述转换为 Mermaid flowchart
    
    Args:
        query: 自然语言描述（业务流程、实体关系等）
        language: 语言代码
        user_id: 用户标识
        api_key: Dify API 密钥（可选）
        
    Returns:
        {
            "success": bool,
            "chart_url": str,
            "message": str
        }
    """
    builder = OntologyBuilder(flowchart_api_key=api_key)
    try:
        return await builder.text_to_flowchart(query, language, user_id)
    finally:
        await builder.close()


async def build_ontology_part1(
    chart_url: str,
    query: str,
    language: str = "auto",
    user_id: str = "default_user",
    api_key: str = None
) -> Dict[str, Any]:
    """
    Part1：预处理 Mermaid 图表
    
    ⚠️ 警告：必须继续调用 build_ontology_part2
    """
    builder = OntologyBuilder(part1_api_key=api_key)
    try:
        return await builder.build_part1(chart_url, query, language, user_id)
    finally:
        await builder.close()


async def build_ontology_part2(
    intermediate_url: str,
    query: str,
    language: str = "auto",
    user_id: str = "default_user",
    api_key: str = None
) -> Dict[str, Any]:
    """
    Part2：生成最终配置文件
    """
    builder = OntologyBuilder(part2_api_key=api_key)
    try:
        return await builder.build_part2(intermediate_url, query, language, user_id)
    finally:
        await builder.close()


async def build_ontology_full(
    query: str,
    language: str = "auto",
    user_id: str = "default_user",
    max_retries: int = 2,
    api_key: str = None
) -> Dict[str, Any]:
    """
    完整构建流程（三阶段：text2flowchart → part1 → part2）
    
    Args:
        query: 自然语言描述（业务流程、实体关系等）
        language: 语言代码
        user_id: 用户标识
        max_retries: 每个阶段的最大重试次数
        api_key: Dify API 密钥（可选，用于所有阶段）
        
    Returns:
        {
            "success": bool,
            "ontology_json_url": str,
            "chart_url": str,
            "intermediate_url": str,
            "message": str
        }
    """
    builder = OntologyBuilder(
        flowchart_api_key=api_key,
        part1_api_key=api_key,
        part2_api_key=api_key
    )
    try:
        return await builder.build_full(query, language, user_id, max_retries)
    finally:
        await builder.close()


async def build_ontology_from_chart(
    chart_url: str,
    query: str,
    language: str = "auto",
    user_id: str = "default_user",
    max_retries: int = 2,
    api_key: str = None
) -> Dict[str, Any]:
    """
    从已有图表构建（两阶段：part1 → part2）
    
    适用于已经有 chart_url 的情况。
    """
    builder = OntologyBuilder(
        part1_api_key=api_key,
        part2_api_key=api_key
    )
    try:
        return await builder.build_from_chart(chart_url, query, language, user_id, max_retries)
    finally:
        await builder.close()


# ===== 配置信息 =====

def get_config_info() -> Dict[str, Any]:
    """获取当前配置信息"""
    return {
        "skill_name": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "dify_api_url": DIFY_API_BASE_URL,
        "text2flowchart": {
            "app_id": DIFY_FLOWCHART_APP_ID,
            "api_key_prefix": DIFY_FLOWCHART_API_KEY[:10] + "..." if DIFY_FLOWCHART_API_KEY else None
        },
        "part1": {
            "app_id": DIFY_PART1_APP_ID,
            "api_key_prefix": DIFY_PART1_API_KEY[:10] + "..." if DIFY_PART1_API_KEY else None
        },
        "part2": {
            "app_id": DIFY_PART2_APP_ID,
            "api_key_prefix": DIFY_PART2_API_KEY[:10] + "..." if DIFY_PART2_API_KEY else None
        }
    }


# ===== 测试入口 =====

if __name__ == "__main__":
    async def test():
        """测试"""
        print("🧪 测试系统配置构建（三阶段）...")
        print(f"\n📋 配置信息:")
        import json
        print(json.dumps(get_config_info(), indent=2, ensure_ascii=False))
        
        builder = OntologyBuilder()
        
        print("\n🔍 测试参数验证...")
        
        # 测试 text2flowchart
        result = await builder.text_to_flowchart("")
        assert not result["success"]
        print(f"✅ text2flowchart 空 query 验证: {result['error']}")
        
        # 测试 Part1
        result = await builder.build_part1("", "test")
        assert not result["success"]
        print(f"✅ Part1 空 URL 验证: {result['error']}")
        
        # 测试 Part2
        result = await builder.build_part2("", "test")
        assert not result["success"]
        print(f"✅ Part2 空 URL 验证: {result['error']}")
        
        await builder.close()
        print("\n✅ 所有参数验证测试通过！")
    
    asyncio.run(test())
