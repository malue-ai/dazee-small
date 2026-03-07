"""
Optional dependency registry.

Centralised registry for all optional runtime dependencies.
Provides pre-flight checks so the frontend can gate features
before users trigger actions that would fail with ImportError.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


@dataclass
class DependencyInfo:
    """Declaration of one optional dependency."""

    import_name: str
    pip_name: str
    purpose: str
    features: List[str] = field(default_factory=list)


@dataclass
class DependencyStatus:
    """Runtime availability of one dependency."""

    name: str
    available: bool
    pip_name: str
    purpose: str
    version: Optional[str] = None


@dataclass
class FeatureStatus:
    """Readiness of a feature that depends on several packages."""

    feature: str
    ready: bool
    missing: List[DependencyStatus] = field(default_factory=list)
    available: List[DependencyStatus] = field(default_factory=list)


# ------------------------------------------------------------------
# Registry: single source of truth for every optional dependency
# ------------------------------------------------------------------

OPTIONAL_DEPENDENCIES: Dict[str, DependencyInfo] = {
    # ---- semantic search (local) ----
    "huggingface_hub": DependencyInfo(
        import_name="huggingface_hub",
        pip_name="huggingface-hub",
        purpose="HuggingFace model download",
        features=["semantic_search_local"],
    ),
    "llama_cpp": DependencyInfo(
        import_name="llama_cpp",
        pip_name="llama-cpp-python",
        purpose="GGUF local embedding inference",
        features=["semantic_search_local"],
    ),
    # ---- memory / vector ----
    "sqlite_vec": DependencyInfo(
        import_name="sqlite_vec",
        pip_name="sqlite-vec",
        purpose="SQLite vector search extension",
        features=["memory", "knowledge"],
    ),
    "mem0ai": DependencyInfo(
        import_name="mem0",
        pip_name="mem0ai",
        purpose="Long-term memory storage and retrieval",
        features=["memory"],
    ),
    # ---- file processing ----
    "PIL": DependencyInfo(
        import_name="PIL",
        pip_name="Pillow",
        purpose="Image compression",
        features=["image_processing"],
    ),
    "pypdf": DependencyInfo(
        import_name="pypdf",
        pip_name="pypdf",
        purpose="PDF text extraction",
        features=["document_parsing"],
    ),
    "pdfplumber": DependencyInfo(
        import_name="pdfplumber",
        pip_name="pdfplumber",
        purpose="PDF table and text extraction",
        features=["document_parsing"],
    ),
    "docx": DependencyInfo(
        import_name="docx",
        pip_name="python-docx",
        purpose="Word document parsing",
        features=["document_parsing"],
    ),
    "pptx": DependencyInfo(
        import_name="pptx",
        pip_name="python-pptx",
        purpose="PowerPoint parsing and generation",
        features=["document_parsing"],
    ),
    "openpyxl": DependencyInfo(
        import_name="openpyxl",
        pip_name="openpyxl",
        purpose="Excel spreadsheet parsing",
        features=["document_parsing"],
    ),
    # ---- JSON ----
    "json5": DependencyInfo(
        import_name="json5",
        pip_name="json5",
        purpose="Lenient JSON parsing",
        features=["json_parsing"],
    ),
    "json_repair": DependencyInfo(
        import_name="json_repair",
        pip_name="json-repair",
        purpose="Broken JSON repair",
        features=["json_parsing"],
    ),
    # ---- channels ----
    "lark_oapi": DependencyInfo(
        import_name="lark_oapi",
        pip_name="lark-oapi",
        purpose="Feishu (Lark) channel integration",
        features=["channel_feishu"],
    ),
    "telegram": DependencyInfo(
        import_name="telegram",
        pip_name="python-telegram-bot",
        purpose="Telegram bot channel",
        features=["channel_telegram"],
    ),
    # ---- scheduling ----
    "apscheduler": DependencyInfo(
        import_name="apscheduler",
        pip_name="APScheduler",
        purpose="Scheduled task execution",
        features=["scheduling"],
    ),
    # ---- macOS native ----
    "objc": DependencyInfo(
        import_name="objc",
        pip_name="pyobjc-core",
        purpose="macOS native framework bridge",
        features=["macos_native"],
    ),
}


# ------------------------------------------------------------------
# Cache: avoid repeated importlib.import_module calls
# ------------------------------------------------------------------

_status_cache: Dict[str, DependencyStatus] = {}


def _check_single(name: str, info: DependencyInfo) -> DependencyStatus:
    """Check availability of one dependency (cached)."""
    if name in _status_cache:
        return _status_cache[name]

    available = False
    version: Optional[str] = None
    try:
        if info.import_name in sys.modules:
            mod = sys.modules[info.import_name]
            available = True
            version = getattr(mod, "__version__", None)
        else:
            spec = importlib.util.find_spec(info.import_name)
            available = spec is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    except Exception:
        pass

    st = DependencyStatus(
        name=name,
        available=available,
        pip_name=info.pip_name,
        purpose=info.purpose,
        version=version,
    )
    _status_cache[name] = st
    return st


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def check_dependency(name: str) -> DependencyStatus:
    """Check a single dependency by registry key."""
    info = OPTIONAL_DEPENDENCIES.get(name)
    if not info:
        return DependencyStatus(
            name=name, available=False, pip_name=name, purpose="unknown"
        )
    return _check_single(name, info)


def check_feature_deps(feature: str) -> FeatureStatus:
    """Check all dependencies required by *feature*."""
    missing: List[DependencyStatus] = []
    available: List[DependencyStatus] = []

    for name, info in OPTIONAL_DEPENDENCIES.items():
        if feature not in info.features:
            continue
        st = _check_single(name, info)
        if st.available:
            available.append(st)
        else:
            missing.append(st)

    return FeatureStatus(
        feature=feature,
        ready=len(missing) == 0,
        missing=missing,
        available=available,
    )


def get_all_status() -> Dict[str, DependencyStatus]:
    """Return status of every registered dependency."""
    return {
        name: _check_single(name, info)
        for name, info in OPTIONAL_DEPENDENCIES.items()
    }


def _is_fallback_only(name: str) -> bool:
    """Check if a dependency is only used as a fallback."""
    info = OPTIONAL_DEPENDENCIES.get(name)
    if not info:
        return False
    return all("fallback" in f for f in info.features)


def log_dependency_report() -> None:
    """Log a summary of all optional dependencies at startup."""
    all_status = get_all_status()
    available = [s for s in all_status.values() if s.available]
    missing = [s for s in all_status.values() if not s.available]

    logger.info(
        f"Dependency check: {len(available)}/{len(all_status)} available"
    )
    if missing:
        for s in missing:
            if _is_fallback_only(s.name):
                logger.debug(
                    f"  Optional fallback not installed: {s.pip_name} — "
                    f"{s.purpose}"
                )
            else:
                logger.warning(
                    f"  Missing: {s.pip_name} — {s.purpose} "
                    f"(install: pip install {s.pip_name})"
                )


def invalidate_cache() -> None:
    """Clear cached results (e.g. after pip install at runtime)."""
    _status_cache.clear()
