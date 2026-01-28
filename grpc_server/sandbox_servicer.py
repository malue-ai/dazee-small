"""
Sandbox gRPC Servicer

沙盒管理的 gRPC 服务实现，对应 routers/workspace.py 中的沙盒相关接口
"""

import grpc
from typing import Optional

from logger import get_logger
from services.sandbox_service import (
    get_sandbox_service,
    SandboxServiceError,
    SandboxNotFoundError,
)
from grpc_server.generated import tool_service_pb2 as pb2
from grpc_server.generated import tool_service_pb2_grpc as pb2_grpc

logger = get_logger("grpc.sandbox")


class SandboxServicer(pb2_grpc.SandboxServiceServicer):
    """
    Sandbox gRPC 服务实现
    
    提供沙盒生命周期管理、项目运行、文件操作等功能
    """
    
    def __init__(self):
        """初始化 Servicer"""
        logger.info("✅ SandboxServicer 初始化完成")
    
    async def GetStatus(
        self,
        request: pb2.SandboxStatusRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxStatusResponse:
        """获取沙盒状态"""
        try:
            service = get_sandbox_service()
            info = await service.get_sandbox_status(request.conversation_id)
            
            if not info:
                return pb2.SandboxStatusResponse(
                    conversation_id=request.conversation_id,
                    status="none"
                )
            
            return pb2.SandboxStatusResponse(
                conversation_id=request.conversation_id,
                sandbox_id=info.id,
                e2b_sandbox_id=info.e2b_sandbox_id,
                status=info.status,
                stack=info.stack,
                preview_url=info.preview_url,
                active_project_path=info.active_project_path,
                active_project_stack=info.active_project_stack,
                created_at=info.created_at,
                last_active_at=info.last_active_at
            )
        
        except Exception as e:
            logger.error(f"获取沙盒状态失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("获取沙盒状态失败")
            return pb2.SandboxStatusResponse()
    
    async def Init(
        self,
        request: pb2.SandboxInitRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxStatusResponse:
        """初始化沙盒"""
        try:
            service = get_sandbox_service()
            info = await service.get_or_create_sandbox(
                conversation_id=request.conversation_id,
                user_id=request.user_id,
                stack=request.stack if request.HasField("stack") else None
            )
            
            return pb2.SandboxStatusResponse(
                conversation_id=request.conversation_id,
                sandbox_id=info.id,
                e2b_sandbox_id=info.e2b_sandbox_id,
                status=info.status,
                stack=info.stack,
                preview_url=info.preview_url,
                active_project_path=info.active_project_path,
                active_project_stack=info.active_project_stack,
                created_at=info.created_at,
                last_active_at=info.last_active_at
            )
        
        except SandboxServiceError as e:
            logger.error(f"初始化沙盒失败: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SandboxStatusResponse()
        except Exception as e:
            logger.error(f"初始化沙盒失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("初始化沙盒失败")
            return pb2.SandboxStatusResponse()
    
    async def Pause(
        self,
        request: pb2.SandboxPauseRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxOperationResponse:
        """暂停沙盒"""
        try:
            service = get_sandbox_service()
            success = await service.pause_sandbox(request.conversation_id)
            
            if not success:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("沙盒不存在或已暂停")
                return pb2.SandboxOperationResponse(
                    success=False,
                    message="沙盒不存在或已暂停"
                )
            
            return pb2.SandboxOperationResponse(
                success=True,
                message="沙盒已暂停"
            )
        
        except SandboxServiceError as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SandboxOperationResponse(success=False, message=str(e))
        except Exception as e:
            logger.error(f"暂停沙盒失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("暂停沙盒失败")
            return pb2.SandboxOperationResponse(success=False, message="暂停沙盒失败")
    
    async def Resume(
        self,
        request: pb2.SandboxResumeRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxStatusResponse:
        """恢复沙盒"""
        try:
            service = get_sandbox_service()
            info = await service.resume_sandbox(request.conversation_id)
            
            return pb2.SandboxStatusResponse(
                conversation_id=request.conversation_id,
                sandbox_id=info.id,
                e2b_sandbox_id=info.e2b_sandbox_id,
                status=info.status,
                stack=info.stack,
                preview_url=info.preview_url,
                active_project_path=info.active_project_path,
                active_project_stack=info.active_project_stack,
                created_at=info.created_at,
                last_active_at=info.last_active_at
            )
        
        except SandboxNotFoundError as e:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return pb2.SandboxStatusResponse()
        except SandboxServiceError as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SandboxStatusResponse()
        except Exception as e:
            logger.error(f"恢复沙盒失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("恢复沙盒失败")
            return pb2.SandboxStatusResponse()
    
    async def Kill(
        self,
        request: pb2.SandboxKillRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxOperationResponse:
        """终止沙盒"""
        try:
            service = get_sandbox_service()
            success = await service.kill_sandbox(request.conversation_id)
            
            return pb2.SandboxOperationResponse(
                success=success,
                message="沙盒已终止" if success else "终止沙盒失败"
            )
        
        except SandboxServiceError as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SandboxOperationResponse(success=False, message=str(e))
        except Exception as e:
            logger.error(f"终止沙盒失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("终止沙盒失败")
            return pb2.SandboxOperationResponse(success=False, message="终止沙盒失败")
    
    async def RunCommand(
        self,
        request: pb2.SandboxCommandRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxCommandResponse:
        """执行命令"""
        try:
            service = get_sandbox_service()
            timeout = request.timeout if request.timeout > 0 else 60
            result = await service.run_command(
                conversation_id=request.conversation_id,
                command=request.command,
                timeout=timeout
            )
            
            return pb2.SandboxCommandResponse(
                success=result.get("success", False),
                exit_code=result.get("exit_code"),
                stdout=result.get("stdout"),
                stderr=result.get("stderr"),
                error=result.get("error")
            )
        
        except SandboxNotFoundError as e:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return pb2.SandboxCommandResponse(success=False, error=str(e))
        except SandboxServiceError as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SandboxCommandResponse(success=False, error=str(e))
        except Exception as e:
            logger.error(f"执行命令失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("执行命令失败")
            return pb2.SandboxCommandResponse(success=False, error="执行命令失败")
    
    async def ListFiles(
        self,
        request: pb2.SandboxListFilesRequest,
        context: grpc.aio.ServicerContext
    ) -> pb2.SandboxListFilesResponse:
        """获取文件列表"""
        try:
            service = get_sandbox_service()
            path = request.path if request.path else "/home/user/project"
            
            # 根据 tree 参数选择方法
            if request.tree:
                files = await service.list_files_tree(request.conversation_id, path)
            else:
                files = await service.list_files(request.conversation_id, path)
            
            # 转换为 protobuf 消息
            def convert_file_info(f) -> pb2.SandboxFileInfo:
                return pb2.SandboxFileInfo(
                    path=f.path,
                    name=f.name,
                    type=f.type,
                    size=f.size if f.size else 0,
                    modified_at=f.modified_at if f.modified_at else "",
                    children=[convert_file_info(c) for c in f.children] if f.children else []
                )
            
            return pb2.SandboxListFilesResponse(
                conversation_id=request.conversation_id,
                files=[convert_file_info(f) for f in files],
                source="sandbox"
            )
        
        except SandboxNotFoundError:
            # 沙盒不存在时返回空列表
            return pb2.SandboxListFilesResponse(
                conversation_id=request.conversation_id,
                files=[],
                source="sandbox"
            )
        except SandboxServiceError as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.SandboxListFilesResponse()
        except Exception as e:
            logger.error(f"获取文件列表失败: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("获取文件列表失败")
            return pb2.SandboxListFilesResponse()
