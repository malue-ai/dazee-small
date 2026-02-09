"""
Embedding 提供商抽象层

支持三种 Embedding 模型，统一接口：
- 本地 GGUF（推荐）: BGE-M3 Q4 量化，424MB，中英文双语，离线可用
- 本地 sentence-transformers（备选）: 需要 PyTorch，体积更大
- OpenAI 云端: text-embedding-3-small，需要 API Key 和网络

模型存储位置：
- GGUF 模型: data/shared/models/ （首次使用自动下载，多实例共享）
- sentence-transformers: ~/.cache/huggingface/hub/

Auto 模式优先级：GGUF 本地 → sentence-transformers → OpenAI 云端

使用示例：
    provider = await create_embedding_provider("auto")
    vec = await provider.embed("如何优化性能")
    vecs = await provider.embed_batch(["文本1", "文本2"])
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import numpy as np

from logger import get_logger

logger = get_logger("knowledge.embeddings")

# ==================== 模型存储目录 ====================

# GGUF models stored in shared directory (reused across instances)
from utils.app_paths import get_shared_models_dir

DEFAULT_MODELS_DIR = get_shared_models_dir()

# 默认 GGUF 模型（BGE-M3 Q4 量化，424MB，中英文双语）
DEFAULT_GGUF_REPO = "lm-kit/bge-m3-gguf"
DEFAULT_GGUF_FILE = "bge-m3-Q4_K_M.gguf"
DEFAULT_GGUF_DIMS = 1024

# HuggingFace 镜像站（国内加速）
HF_MIRROR_ENDPOINT = "https://hf-mirror.com"
HF_OFFICIAL_ENDPOINT = "https://huggingface.co"

# 探测缓存（进程生命周期内只探测一次）
_hf_endpoint_cache: Optional[str] = None


class ModelNotAvailableError(RuntimeError):
    """Raised when GGUF model file is not downloaded yet."""

    def __init__(self, model_name: str, model_dir: Path):
        self.model_name = model_name
        self.model_dir = model_dir
        super().__init__(
            f"Embedding model not found: {model_name}\n"
            f"Expected at: {model_dir / model_name}\n"
            f"Please enable semantic search in settings to download."
        )


def _detect_hf_endpoint(timeout: float = 3.0) -> str:
    """
    Auto-detect the best HuggingFace endpoint.

    Priority:
    1. HF_ENDPOINT env var (user explicit override)
    2. huggingface.co reachability probe (3s timeout)
    3. Fallback to hf-mirror.com (China mirror)

    Result is cached for the process lifetime.

    Returns:
        Best available endpoint URL
    """
    global _hf_endpoint_cache

    if _hf_endpoint_cache is not None:
        return _hf_endpoint_cache

    # User explicitly set → respect it
    user_endpoint = os.getenv("HF_ENDPOINT")
    if user_endpoint:
        _hf_endpoint_cache = user_endpoint
        logger.debug(f"Using user-configured HF_ENDPOINT: {user_endpoint}")
        return user_endpoint

    # Probe huggingface.co connectivity
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(
            HF_OFFICIAL_ENDPOINT, method="HEAD"
        )
        urllib.request.urlopen(req, timeout=timeout)
        _hf_endpoint_cache = HF_OFFICIAL_ENDPOINT
        logger.debug("HuggingFace official site reachable, using direct source")
    except (urllib.error.URLError, OSError, TimeoutError):
        _hf_endpoint_cache = HF_MIRROR_ENDPOINT
        logger.info(
            f"HuggingFace official site unreachable, "
            f"auto-switching to mirror: {HF_MIRROR_ENDPOINT}"
        )

    return _hf_endpoint_cache


def is_gguf_model_downloaded(
    filename: str = DEFAULT_GGUF_FILE,
) -> bool:
    """
    Check if GGUF model file exists locally.

    Args:
        filename: model filename to check

    Returns:
        True if model file exists
    """
    return (get_models_dir() / filename).exists()


async def download_gguf_model(
    repo_id: str = DEFAULT_GGUF_REPO,
    filename: str = DEFAULT_GGUF_FILE,
) -> str:
    """
    Explicitly download GGUF embedding model.

    Auto-detects best source (official vs China mirror).
    Called from settings API after user confirmation.

    Args:
        repo_id: HuggingFace repo id
        filename: model filename

    Returns:
        Path to downloaded model file

    Raises:
        ImportError: huggingface-hub not installed
        RuntimeError: download failed
    """
    import asyncio

    models_dir = get_models_dir()
    local_path = models_dir / filename

    if local_path.exists():
        logger.info(f"Model already exists: {local_path}")
        return str(local_path)

    endpoint = _detect_hf_endpoint()
    source_label = (
        "mirror (hf-mirror.com)"
        if endpoint == HF_MIRROR_ENDPOINT
        else "official (huggingface.co)"
    )
    logger.info(
        f"Downloading embedding model: {filename} "
        f"(~438MB, source: {source_label})"
    )

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise ImportError(
            "huggingface-hub is required to download models.\n"
            "Install: pip install huggingface-hub"
        )

    def _do_download() -> str:
        return hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=str(models_dir),
            local_dir_use_symlinks=False,
            endpoint=endpoint,
        )

    loop = asyncio.get_event_loop()
    downloaded_path = await loop.run_in_executor(None, _do_download)

    logger.info(f"Model downloaded to: {downloaded_path}")
    return downloaded_path


# ==================== L2 归一化工具 ====================


def normalize_l2(vec: np.ndarray) -> np.ndarray:
    """
    L2 归一化向量

    保证余弦相似度计算正确，处理零向量和非有限值。

    Args:
        vec: 输入向量

    Returns:
        归一化后的单位向量
    """
    # Step 1: 清理非有限值（NaN/Infinity → 0）
    sanitized = np.where(np.isfinite(vec), vec, 0.0)

    # Step 2: 计算 L2 范数
    magnitude = np.linalg.norm(sanitized)

    # Step 3: 归一化（零向量保护）
    if magnitude < 1e-10:
        return sanitized.astype(np.float32)

    return (sanitized / magnitude).astype(np.float32)


def normalize_l2_list(vec: List[float]) -> List[float]:
    """
    L2 归一化（List[float] 版本）

    Args:
        vec: 输入向量列表

    Returns:
        归一化后的向量列表
    """
    return normalize_l2(np.array(vec, dtype=np.float32)).tolist()


def get_models_dir() -> Path:
    """
    获取本地模型存储目录

    默认 data/shared/models/，首次调用自动创建。

    Returns:
        模型目录路径
    """
    models_dir = Path(
        os.getenv("ZENFLUX_MODELS_DIR", str(DEFAULT_MODELS_DIR))
    )
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


# ==================== 提供商抽象接口 ====================


class EmbeddingProvider(ABC):
    """Embedding 提供商抽象接口"""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider identifier (e.g. 'openai', 'local-gguf', 'local-st')"""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name"""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Output vector dimensions"""

    @abstractmethod
    async def embed(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            L2-normalized embedding vector
        """

    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts.

        Default: sequential calls to embed(). Subclasses may override
        with batch API for better performance.

        Args:
            texts: List of input texts

        Returns:
            List of L2-normalized embedding vectors
        """
        results = []
        for text in texts:
            try:
                vec = await self.embed(text)
                results.append(vec)
            except Exception as e:
                logger.warning(f"Batch embed failed for one chunk: {e}")
                results.append(np.zeros(self.dimensions, dtype=np.float32))
        return results


# ==================== OpenAI 提供商 ====================


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI Embedding 提供商

    使用 text-embedding-3-small（1536 维，$0.02/1M tokens）。
    需要 OPENAI_API_KEY 环境变量。
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self._model = model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._base_url = base_url or os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        self._dimensions = 1536 if "small" in model else 3072

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, text: str) -> np.ndarray:
        """Generate embedding via OpenAI API."""
        import httpx

        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not set")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": text[:8000]},
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        raw = np.array(data["data"][0]["embedding"], dtype=np.float32)
        return normalize_l2(raw)

    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Batch embedding via OpenAI API (up to 100 per request)."""
        import httpx

        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not set")

        if not texts:
            return []

        truncated = [t[:8000] for t in texts]
        batch_size = 100
        all_vectors: List[np.ndarray] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(0, len(truncated), batch_size):
                batch = truncated[i : i + batch_size]
                try:
                    response = await client.post(
                        f"{self._base_url}/embeddings",
                        json={"model": self._model, "input": batch},
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                    sorted_data = sorted(
                        data["data"], key=lambda x: x["index"]
                    )
                    for item in sorted_data:
                        raw = np.array(
                            item["embedding"], dtype=np.float32
                        )
                        all_vectors.append(normalize_l2(raw))
                except Exception as e:
                    logger.warning(
                        f"OpenAI batch embed failed [{i}:{i+len(batch)}]: {e}"
                    )
                    for _ in batch:
                        all_vectors.append(
                            np.zeros(self._dimensions, dtype=np.float32)
                        )

        return all_vectors


# ==================== GGUF 本地提供商（推荐） ====================


class GGUFEmbeddingProvider(EmbeddingProvider):
    """
    GGUF 本地 Embedding 提供商（推荐方案）

    使用 llama-cpp-python 加载 GGUF 量化模型：
    - 默认模型: BGE-M3 Q4（424MB，1024 维，中英文双语）
    - 依赖: pip install llama-cpp-python
    - 模型存储: data/shared/models/bge-m3-Q4_K_M.gguf
    - 首次使用自动从 HuggingFace 下载

    相比 sentence-transformers 方案的优势：
    - 总安装体积小（~500MB vs ~1.8GB，因不需要 PyTorch）
    - CPU 推理速度快（~20ms/条）
    - 内存占用低
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        repo_id: Optional[str] = None,
        filename: Optional[str] = None,
        dimensions: int = DEFAULT_GGUF_DIMS,
    ):
        self._repo_id = repo_id or os.getenv("GGUF_REPO", DEFAULT_GGUF_REPO)
        self._filename = filename or os.getenv("GGUF_MODEL", DEFAULT_GGUF_FILE)
        self._dimensions = dimensions
        self._model_path = model_path
        self._model = None  # Lazy init

    @property
    def provider_id(self) -> str:
        return "local-gguf"

    @property
    def model_name(self) -> str:
        return f"{self._repo_id}/{self._filename}"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _resolve_model_path(self) -> str:
        """
        Resolve GGUF model file path.

        Does NOT auto-download. If model is missing, raises ModelNotAvailableError.
        Use download_gguf_model() to explicitly download after user confirmation.

        Returns:
            Absolute path to .gguf file

        Raises:
            ModelNotAvailableError: model not downloaded yet
        """
        if self._model_path:
            return self._model_path

        models_dir = get_models_dir()
        local_path = models_dir / self._filename

        if local_path.exists():
            return str(local_path)

        raise ModelNotAvailableError(self._filename, models_dir)

    def _ensure_model(self):
        """Lazy load GGUF model via llama-cpp-python."""
        if self._model is not None:
            return

        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python is required for local GGUF embedding.\n"
                "Install: pip install llama-cpp-python\n"
                "Model: BGE-M3 Q4 (424MB, auto-downloaded on first use)"
            )

        model_path = self._resolve_model_path()

        logger.info(f"Loading GGUF embedding model: {model_path}")
        self._model = Llama(
            model_path=model_path,
            embedding=True,
            n_ctx=8192,
            n_gpu_layers=0,  # CPU only for compatibility
            verbose=False,
        )

        logger.info(
            f"GGUF embedding model loaded: {self._filename} "
            f"(dim={self._dimensions})"
        )

    async def embed(self, text: str) -> np.ndarray:
        """Generate embedding using GGUF model."""
        import asyncio

        self._ensure_model()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._model.embed(text[:8000]),
        )

        # llama-cpp-python embed() returns List[float] (flat 1D vector)
        raw = np.array(result, dtype=np.float32)
        return normalize_l2(raw)

    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Batch embedding using GGUF model (sequential, CPU)."""
        import asyncio

        if not texts:
            return []

        self._ensure_model()

        truncated = [t[:8000] for t in texts]

        def _batch_encode():
            results = []
            for text in truncated:
                try:
                    result = self._model.embed(text)
                    raw = np.array(result, dtype=np.float32)
                    results.append(normalize_l2(raw))
                except Exception as e:
                    logger.warning(f"GGUF embed failed for chunk: {e}")
                    results.append(
                        np.zeros(self._dimensions, dtype=np.float32)
                    )
            return results

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _batch_encode)


# ==================== sentence-transformers 本地提供商（备选） ====================


class SentenceTransformerProvider(EmbeddingProvider):
    """
    sentence-transformers 本地 Embedding 提供商（备选方案）

    注意：需要安装 PyTorch（~700MB），总安装体积约 1.5-2GB。
    如果追求轻量，优先使用 GGUFEmbeddingProvider。

    模型存储: ~/.cache/huggingface/hub/
    """

    _KNOWN_DIMS = {
        "BAAI/bge-m3": 1024,
        "BAAI/bge-small-zh-v1.5": 512,
        "intfloat/multilingual-e5-small": 384,
        "intfloat/multilingual-e5-base": 768,
    }

    def __init__(self, model: str = "BAAI/bge-m3"):
        self._model_name = model
        self._dimensions = self._KNOWN_DIMS.get(model, 1024)
        self._model = None

    @property
    def provider_id(self) -> str:
        return "local-st"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _ensure_model(self):
        """Lazy load sentence-transformers model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers is required.\n"
                "Install: pip install sentence-transformers\n"
                "Note: This also installs PyTorch (~700MB). "
                "For a lighter option, use: pip install llama-cpp-python"
            )

        logger.info(
            f"Loading sentence-transformers model: {self._model_name}"
        )
        self._model = SentenceTransformer(self._model_name)

        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim and actual_dim != self._dimensions:
            self._dimensions = actual_dim

        logger.info(
            f"Model loaded: {self._model_name} (dim={self._dimensions}), "
            f"stored at: ~/.cache/huggingface/hub/"
        )

    async def embed(self, text: str) -> np.ndarray:
        """Generate embedding using sentence-transformers."""
        import asyncio

        self._ensure_model()

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                text[:8000], normalize_embeddings=True
            ),
        )
        return np.array(raw, dtype=np.float32)

    async def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Batch embedding (sentence-transformers native batch)."""
        import asyncio

        if not texts:
            return []

        self._ensure_model()

        truncated = [t[:8000] for t in texts]

        loop = asyncio.get_event_loop()
        raw_batch = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                truncated, normalize_embeddings=True, batch_size=32
            ),
        )
        return [np.array(v, dtype=np.float32) for v in raw_batch]


# ==================== 兼容别名 ====================

# 保持向后兼容
LocalEmbeddingProvider = GGUFEmbeddingProvider


# ==================== 工厂函数 ====================


async def create_embedding_provider(
    provider: str = "auto",
    model: Optional[str] = None,
) -> EmbeddingProvider:
    """
    Create an embedding provider with auto-detection and fallback.

    Auto mode priority:
    1. GGUF local (llama-cpp-python) — lightest, ~500MB total
    2. sentence-transformers local — heavier, ~1.8GB total
    3. OpenAI cloud — needs API key + internet

    Args:
        provider: 'auto' | 'openai' | 'local' | 'local-gguf' | 'local-st'
        model: Override model name (None = default for provider)

    Returns:
        Configured EmbeddingProvider

    Raises:
        RuntimeError: No available provider
    """
    if provider == "openai":
        return OpenAIEmbeddingProvider(
            model=model or "text-embedding-3-small"
        )

    if provider in ("local", "local-gguf"):
        return GGUFEmbeddingProvider()

    if provider == "local-st":
        return SentenceTransformerProvider(model=model or "BAAI/bge-m3")

    # Auto mode: gguf → sentence-transformers → openai
    if provider == "auto":
        errors: List[str] = []

        # 1. Try GGUF (lightest)
        try:
            gguf_provider = GGUFEmbeddingProvider()
            gguf_provider._ensure_model()
            logger.info(
                f"Auto-selected GGUF embedding: {gguf_provider.model_name}"
            )
            return gguf_provider
        except ImportError as e:
            errors.append(f"GGUF: {e}")
            logger.debug(f"GGUF embedding not available: {e}")
        except Exception as e:
            errors.append(f"GGUF: {e}")
            logger.debug(f"GGUF embedding failed: {e}")

        # 2. Try sentence-transformers (heavier but stable)
        try:
            st_provider = SentenceTransformerProvider(
                model=model or "BAAI/bge-m3"
            )
            st_provider._ensure_model()
            logger.info(
                f"Auto-selected sentence-transformers: "
                f"{st_provider.model_name}"
            )
            return st_provider
        except ImportError as e:
            errors.append(f"sentence-transformers: {e}")
        except Exception as e:
            errors.append(f"sentence-transformers: {e}")

        # 3. Try OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            logger.info("Auto-selected OpenAI embedding")
            return OpenAIEmbeddingProvider(
                model=model or "text-embedding-3-small"
            )
        else:
            errors.append("OpenAI: OPENAI_API_KEY not set")

        raise RuntimeError(
            "No embedding provider available.\n"
            "Options (pick one):\n"
            "  1. pip install llama-cpp-python + enable semantic search in settings\n"
            "     Model: BGE-M3 Q4 (438MB, Chinese+English)\n"
            f"     Stored at: {get_models_dir()}\n"
            "  2. pip install sentence-transformers   "
            "← Heavier (~1.8GB, needs PyTorch)\n"
            "  3. Set OPENAI_API_KEY   "
            "← Cloud, needs internet\n"
            "\nDetails:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    raise ValueError(f"Unknown provider: {provider}")
