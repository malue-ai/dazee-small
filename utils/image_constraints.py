"""
按模型约束图片附件（大小/分辨率/像素）。

设计目标：
1. 后端统一兜底，避免模型侧 4xx 才暴露问题。
2. 规则可扩展（按模型前缀匹配）。
3. 无法读取远程图片像素时，至少校验文件大小（Content-Length）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from logger import get_logger
from utils.app_paths import get_storage_dir

logger = get_logger(__name__)

try:
    from PIL import Image as PILImage

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False
    PILImage = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ImageConstraint:
    """图片约束定义（按模型生效）。"""

    max_file_size_bytes: int
    max_width: int
    max_height: int
    max_pixels: int


DEFAULT_IMAGE_CONSTRAINT = ImageConstraint(
    max_file_size_bytes=20 * 1024 * 1024,  # 20MB
    max_width=8192,
    max_height=8192,
    max_pixels=40_000_000,
)

# 规则按前缀匹配，key 小写；可按需继续扩展
MODEL_IMAGE_CONSTRAINTS: Dict[str, ImageConstraint] = {
    "claude": ImageConstraint(
        max_file_size_bytes=5 * 1024 * 1024,  # 5MB
        max_width=8000,
        max_height=8000,
        max_pixels=33_000_000,
    ),
    "qwen3-vl": ImageConstraint(
        max_file_size_bytes=10 * 1024 * 1024,  # 10MB
        max_width=4096,
        max_height=4096,
        max_pixels=16_000_000,
    ),
    "qwen-vl": ImageConstraint(
        max_file_size_bytes=10 * 1024 * 1024,  # 10MB
        max_width=4096,
        max_height=4096,
        max_pixels=16_000_000,
    ),
}


def resolve_image_constraint(model_name: Optional[str]) -> Tuple[str, ImageConstraint]:
    """
    解析模型对应的图片约束。

    Returns:
        (matched_key, constraint)
    """
    if not model_name:
        return "default", DEFAULT_IMAGE_CONSTRAINT

    lowered = model_name.lower()
    for prefix in sorted(MODEL_IMAGE_CONSTRAINTS.keys(), key=len, reverse=True):
        if lowered.startswith(prefix):
            return prefix, MODEL_IMAGE_CONSTRAINTS[prefix]
    return "default", DEFAULT_IMAGE_CONSTRAINT


def _is_image_file(file_type: str) -> bool:
    return file_type.lower().startswith("image/")


def _get_field(file_ref: Any, key: str) -> Any:
    if isinstance(file_ref, dict):
        return file_ref.get(key)
    return getattr(file_ref, key, None)


def _resolve_local_path(file_ref: Any) -> Optional[Path]:
    local_path = _get_field(file_ref, "local_path")
    if local_path:
        return Path(str(local_path))

    file_url = _get_field(file_ref, "file_url")
    if isinstance(file_url, str) and file_url.startswith("/api/v1/files/"):
        relative = file_url[len("/api/v1/files/") :]
        return get_storage_dir() / relative

    return None


def _format_bytes(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f}MB"


def _inspect_local_image(path: Path) -> Tuple[int, Optional[int], Optional[int]]:
    """返回 (size_bytes, width, height)。"""
    size_bytes = path.stat().st_size
    if not PIL_AVAILABLE or PILImage is None:
        return size_bytes, None, None

    try:
        with PILImage.open(path) as img:
            width, height = img.size
        return size_bytes, width, height
    except Exception:
        # 只要文件大小可读，就继续走大小校验
        return size_bytes, None, None


def _build_violation_message(
    file_name: str,
    reason: str,
    model_name: Optional[str],
    matched_rule: str,
    constraint: ImageConstraint,
) -> str:
    return (
        f"图片 '{file_name}' 不符合模型限制：{reason}。"
        f"(model={model_name or 'unknown'}, rule={matched_rule}, "
        f"limit=size<={_format_bytes(constraint.max_file_size_bytes)}, "
        f"width<={constraint.max_width}, height<={constraint.max_height}, "
        f"pixels<={constraint.max_pixels})"
    )


async def validate_image_files_for_model(
    files: Sequence[Any],
    model_name: Optional[str],
) -> None:
    """
    校验聊天请求中的图片附件。

    Raises:
        ValueError: 任一图片不符合当前模型限制。
    """
    if not files:
        return

    matched_rule, constraint = resolve_image_constraint(model_name)
    async_client: Optional[httpx.AsyncClient] = None
    violations: List[str] = []

    try:
        for file_ref in files:
            file_type = str(_get_field(file_ref, "file_type") or "")
            file_name = str(_get_field(file_ref, "file_name") or "unknown")

            if not file_type or not _is_image_file(file_type):
                continue

            local_path = _resolve_local_path(file_ref)
            if local_path and local_path.exists():
                size_bytes, width, height = _inspect_local_image(local_path)
            else:
                # 远程文件：尽量做 HEAD 大小检查，像素未知则跳过像素限制
                size_bytes = int(_get_field(file_ref, "file_size") or 0)
                width = None
                height = None
                file_url = _get_field(file_ref, "file_url")
                if (not size_bytes) and isinstance(file_url, str) and file_url.startswith("http"):
                    if async_client is None:
                        async_client = httpx.AsyncClient(timeout=8.0)
                    try:
                        resp = await async_client.head(file_url, follow_redirects=True)
                        cl = resp.headers.get("content-length")
                        if cl and cl.isdigit():
                            size_bytes = int(cl)
                    except Exception:
                        logger.debug("远程图片 HEAD 检测失败", extra={"file_url": file_url})

            if size_bytes > constraint.max_file_size_bytes:
                violations.append(
                    _build_violation_message(
                        file_name=file_name,
                        reason=f"文件大小 {_format_bytes(size_bytes)} 超过上限 {_format_bytes(constraint.max_file_size_bytes)}",
                        model_name=model_name,
                        matched_rule=matched_rule,
                        constraint=constraint,
                    )
                )
                continue

            if width is None or height is None:
                continue

            if width > constraint.max_width or height > constraint.max_height:
                violations.append(
                    _build_violation_message(
                        file_name=file_name,
                        reason=f"分辨率 {width}x{height} 超过上限 {constraint.max_width}x{constraint.max_height}",
                        model_name=model_name,
                        matched_rule=matched_rule,
                        constraint=constraint,
                    )
                )
                continue

            pixels = width * height
            if pixels > constraint.max_pixels:
                violations.append(
                    _build_violation_message(
                        file_name=file_name,
                        reason=f"像素总量 {pixels} 超过上限 {constraint.max_pixels}",
                        model_name=model_name,
                        matched_rule=matched_rule,
                        constraint=constraint,
                    )
                )

        if violations:
            raise ValueError("；".join(violations))
    finally:
        if async_client is not None:
            await async_client.aclose()
