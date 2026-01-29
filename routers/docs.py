"""
文档浏览 API
提供项目文档的结构和内容访问
"""

from fastapi import APIRouter, HTTPException, status

from models.docs import DocsStructureResponse, DocContentResponse
from services.docs_service import get_docs_structure, get_doc_content


router = APIRouter(prefix="/api/v1/docs", tags=["文档浏览"])


@router.get(
    "/structure",
    response_model=DocsStructureResponse,
    summary="获取文档目录结构",
    description="返回所有文档分类和文件列表"
)
async def api_get_docs_structure() -> DocsStructureResponse:
    """获取文档目录结构"""
    structure = await get_docs_structure()
    return DocsStructureResponse(success=True, data=structure)


@router.get(
    "/content/{doc_path:path}",
    response_model=DocContentResponse,
    summary="获取文档内容",
    description="根据路径获取文档的 Markdown 内容"
)
async def api_get_doc_content(doc_path: str) -> DocContentResponse:
    """
    获取文档内容
    
    Args:
        doc_path: 文档相对路径，如 "architecture/01-MEMORY-PROTOCOL.md"
    """
    content = await get_doc_content(doc_path)
    
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文档不存在: {doc_path}"
        )
    
    return DocContentResponse(success=True, data=content)
