"""
缓存工具模块 - Instance Cache Utils

职责：
1. 计算文件/目录内容的 hash（SHA256）
2. 加载和保存实例缓存（Schema、工具推断结果）
3. 检测缓存是否有效（基于源文件 hash）
4. 缓存失效和清理

设计原则：
- 使用 SHA256 hash 检测文件变更
- 缓存结构清晰：schema.json + tools_inference.json + cache_metadata.json
- 支持增量更新：只重新分析变更的部分
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from datetime import datetime

from logger import get_logger

logger = get_logger("cache_utils")

# 缓存格式版本（用于兼容性检查）
CACHE_VERSION = "1.0"


# ============================================================
# 文件 Hash 计算
# ============================================================

def compute_file_hash(filepath: Path) -> str:
    """
    计算文件内容的 SHA256 hash
    
    Args:
        filepath: 文件路径
        
    Returns:
        "sha256:..." 格式的 hash 字符串
    """
    if not filepath.exists():
        return "sha256:not_found"
    
    try:
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            # 分块读取，避免大文件内存问题
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return f"sha256:{hasher.hexdigest()}"
    except Exception as e:
        logger.warning(f"计算文件 hash 失败 {filepath}: {str(e)}")
        return "sha256:error"


def compute_dir_hash(dirpath: Path, pattern: str = "*.md") -> Dict[str, str]:
    """
    计算目录下匹配文件的 hash 字典
    
    Args:
        dirpath: 目录路径
        pattern: 文件匹配模式（如 "*.md"）
        
    Returns:
        {相对路径: hash} 字典
    """
    if not dirpath.exists() or not dirpath.is_dir():
        return {}
    
    hashes = {}
    for filepath in dirpath.rglob(pattern):
        if filepath.is_file():
            relative_path = str(filepath.relative_to(dirpath))
            hashes[relative_path] = compute_file_hash(filepath)
    
    return hashes


def compute_tool_hash(tool_name: str, tool_description: str) -> str:
    """
    计算工具的 hash（用于工具推断缓存）
    
    Args:
        tool_name: 工具名称
        tool_description: 工具描述
        
    Returns:
        "sha256:..." 格式的 hash 字符串
    """
    content = f"{tool_name}|{tool_description}"
    hasher = hashlib.sha256(content.encode('utf-8'))
    return f"sha256:{hasher.hexdigest()}"


# ============================================================
# 缓存元数据管理
# ============================================================

def get_source_files_hashes(instance_path: Path) -> Dict[str, str]:
    """
    获取实例所有源文件的 hash
    
    监控的文件：
    - prompt.md
    - config.yaml
    - api_desc/*.md
    - skills/*/SKILL.md
    
    Args:
        instance_path: 实例目录路径
        
    Returns:
        {文件相对路径: hash} 字典
    """
    hashes = {}
    
    # 1. prompt.md
    prompt_file = instance_path / "prompt.md"
    if prompt_file.exists():
        hashes["prompt.md"] = compute_file_hash(prompt_file)
    
    # 2. config.yaml
    config_file = instance_path / "config.yaml"
    if config_file.exists():
        hashes["config.yaml"] = compute_file_hash(config_file)
    
    # 3. api_desc/*.md
    api_desc_dir = instance_path / "api_desc"
    if api_desc_dir.exists():
        api_hashes = compute_dir_hash(api_desc_dir, "*.md")
        for rel_path, hash_val in api_hashes.items():
            hashes[f"api_desc/{rel_path}"] = hash_val
    
    # 4. skills/*/SKILL.md
    skills_dir = instance_path / "skills"
    if skills_dir.exists():
        skill_hashes = compute_dir_hash(skills_dir, "SKILL.md")
        for rel_path, hash_val in skill_hashes.items():
            hashes[f"skills/{rel_path}"] = hash_val
    
    return hashes


def create_cache_metadata(instance_path: Path) -> Dict[str, Any]:
    """
    创建缓存元数据
    
    Args:
        instance_path: 实例目录路径
        
    Returns:
        缓存元数据字典
    """
    return {
        "version": CACHE_VERSION,
        "created_at": datetime.now().isoformat(),
        "source_hashes": get_source_files_hashes(instance_path)
    }


# ============================================================
# 缓存有效性检查
# ============================================================

def is_cache_valid(cache_dir: Path, instance_path: Path) -> bool:
    """
    检查缓存是否有效
    
    策略：
    1. 检查缓存文件是否存在
    2. 检查缓存版本是否匹配
    3. 对比源文件 hash，如果任一文件变更则失效
    
    Args:
        cache_dir: 缓存目录（.cache/）
        instance_path: 实例目录
        
    Returns:
        True 表示缓存有效，False 表示需要重新生成
    """
    # 1. 检查缓存文件是否存在
    metadata_file = cache_dir / "cache_metadata.json"
    schema_file = cache_dir / "schema.json"
    tools_file = cache_dir / "tools_inference.json"
    
    if not all([metadata_file.exists(), schema_file.exists(), tools_file.exists()]):
        logger.info("缓存文件缺失，需要重新生成")
        return False
    
    # 2. 加载并检查元数据
    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        logger.warning(f"读取缓存元数据失败: {str(e)}")
        return False
    
    # 3. 检查版本
    if metadata.get("version") != CACHE_VERSION:
        logger.info(f"缓存版本不匹配: {metadata.get('version')} != {CACHE_VERSION}")
        return False
    
    # 4. 对比源文件 hash
    cached_hashes = metadata.get("source_hashes", {})
    current_hashes = get_source_files_hashes(instance_path)
    
    # 检查是否有文件变更或新增
    for filepath, current_hash in current_hashes.items():
        cached_hash = cached_hashes.get(filepath)
        if cached_hash != current_hash:
            logger.info(f"源文件变更: {filepath}")
            logger.debug(f"  缓存 hash: {cached_hash}")
            logger.debug(f"  当前 hash: {current_hash}")
            return False
    
    # 检查是否有文件被删除
    for filepath in cached_hashes.keys():
        if filepath not in current_hashes:
            logger.info(f"源文件已删除: {filepath}")
            return False
    
    logger.info("✅ 缓存有效，可以复用")
    return True


# ============================================================
# 缓存加载
# ============================================================

def load_schema_cache(cache_dir: Path) -> Optional[Dict[str, Any]]:
    """
    加载 Schema 缓存
    
    Args:
        cache_dir: 缓存目录
        
    Returns:
        Schema 字典，失败返回 None
    """
    schema_file = cache_dir / "schema.json"
    
    if not schema_file.exists():
        return None
    
    try:
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_data = json.load(f)
        logger.info(f"✅ 加载 Schema 缓存成功: {schema_data.get('name', 'Unknown')}")
        return schema_data
    except Exception as e:
        logger.error(f"加载 Schema 缓存失败: {str(e)}")
        return None


def load_tools_inference_cache(cache_dir: Path) -> Dict[str, List[str]]:
    """
    加载工具推断缓存
    
    Args:
        cache_dir: 缓存目录
        
    Returns:
        {tool_hash: [capabilities]} 字典
    """
    tools_file = cache_dir / "tools_inference.json"
    
    if not tools_file.exists():
        return {}
    
    try:
        with open(tools_file, 'r', encoding='utf-8') as f:
            tools_cache = json.load(f)
        logger.info(f"✅ 加载工具推断缓存成功，包含 {len(tools_cache)} 个工具")
        return tools_cache
    except Exception as e:
        logger.error(f"加载工具推断缓存失败: {str(e)}")
        return {}


# ============================================================
# 缓存保存
# ============================================================

def save_schema_cache(cache_dir: Path, schema_data: Dict[str, Any]) -> bool:
    """
    保存 Schema 缓存
    
    Args:
        cache_dir: 缓存目录
        schema_data: Schema 字典
        
    Returns:
        成功返回 True
    """
    # 确保缓存目录存在
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    schema_file = cache_dir / "schema.json"
    
    try:
        with open(schema_file, 'w', encoding='utf-8') as f:
            json.dump(schema_data, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 保存 Schema 缓存: {schema_file}")
        return True
    except Exception as e:
        logger.error(f"保存 Schema 缓存失败: {str(e)}")
        return False


def save_tools_inference_cache(cache_dir: Path, tools_cache: Dict[str, List[str]]) -> bool:
    """
    保存工具推断缓存
    
    Args:
        cache_dir: 缓存目录
        tools_cache: {tool_hash: [capabilities]} 字典
        
    Returns:
        成功返回 True
    """
    # 确保缓存目录存在
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    tools_file = cache_dir / "tools_inference.json"
    
    try:
        with open(tools_file, 'w', encoding='utf-8') as f:
            json.dump(tools_cache, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 保存工具推断缓存: {len(tools_cache)} 个工具")
        return True
    except Exception as e:
        logger.error(f"保存工具推断缓存失败: {str(e)}")
        return False


def save_cache_metadata(cache_dir: Path, instance_path: Path) -> bool:
    """
    保存缓存元数据
    
    Args:
        cache_dir: 缓存目录
        instance_path: 实例目录
        
    Returns:
        成功返回 True
    """
    # 确保缓存目录存在
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_file = cache_dir / "cache_metadata.json"
    metadata = create_cache_metadata(instance_path)
    
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ 保存缓存元数据: {metadata_file}")
        return True
    except Exception as e:
        logger.error(f"保存缓存元数据失败: {str(e)}")
        return False


def save_all_cache(
    cache_dir: Path,
    instance_path: Path,
    schema_data: Dict[str, Any],
    tools_cache: Dict[str, List[str]]
) -> bool:
    """
    保存所有缓存（Schema + 工具推断 + 元数据）
    
    Args:
        cache_dir: 缓存目录
        instance_path: 实例目录
        schema_data: Schema 字典
        tools_cache: 工具推断缓存
        
    Returns:
        成功返回 True
    """
    success = True
    success &= save_schema_cache(cache_dir, schema_data)
    success &= save_tools_inference_cache(cache_dir, tools_cache)
    success &= save_cache_metadata(cache_dir, instance_path)
    
    if success:
        logger.info(f"✅ 缓存保存完成: {cache_dir}")
    else:
        logger.warning(f"⚠️ 部分缓存保存失败")
    
    return success


# ============================================================
# 缓存清理
# ============================================================

def clear_cache(cache_dir: Path) -> bool:
    """
    清除缓存目录
    
    Args:
        cache_dir: 缓存目录
        
    Returns:
        成功返回 True
    """
    if not cache_dir.exists():
        logger.info("缓存目录不存在，无需清理")
        return True
    
    try:
        import shutil
        shutil.rmtree(cache_dir)
        logger.info(f"✅ 清除缓存: {cache_dir}")
        return True
    except Exception as e:
        logger.error(f"清除缓存失败: {str(e)}")
        return False


# ============================================================
# 便捷函数
# ============================================================

def ensure_cache_dir(instance_path: Path) -> Path:
    """
    确保缓存目录存在
    
    Args:
        instance_path: 实例目录
        
    Returns:
        缓存目录路径
    """
    cache_dir = instance_path / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir
