#!/usr/bin/env python3
"""
Gateway session mapper regression check.

Verifies:
1. conversation_key normalization is stable.
2. conversation mapping survives cache clear (simulates process restart).
"""

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


def _load_session_mapper_module():
    # Inject lightweight stubs to avoid importing heavy package side effects.
    utils_pkg = types.ModuleType("utils")
    app_paths_mod = types.ModuleType("utils.app_paths")
    json_store_mod = types.ModuleType("utils.json_file_store")

    def _get_instance_store_dir(instance_name: str) -> Path:
        base = Path(os.environ.get("ZENFLUX_DATA_DIR", ".")) / "data" / "instances" / instance_name / "store"
        base.mkdir(parents=True, exist_ok=True)
        return base

    class _JsonFileStore:
        def __init__(self, path: Path, default_factory):
            self.path = path
            self.default_factory = default_factory

        async def read_async(self):
            if not self.path.exists():
                return self.default_factory()
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return self.default_factory()

        async def update_async(self, mutator):
            data = await self.read_async()
            mutator(data)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    app_paths_mod.get_instance_store_dir = _get_instance_store_dir
    json_store_mod.JsonFileStore = _JsonFileStore

    sys.modules.setdefault("utils", utils_pkg)
    sys.modules["utils.app_paths"] = app_paths_mod
    sys.modules["utils.json_file_store"] = json_store_mod

    module_path = PROJECT_ROOT / "core" / "gateway" / "session_mapper.py"
    spec = importlib.util.spec_from_file_location("gateway_session_mapper", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["ZENFLUX_DATA_DIR"] = temp_dir
        os.environ["AGENT_INSTANCE"] = "gateway_mapper_test"

        mapper = _load_session_mapper_module()
        build_conversation_key = mapper.build_conversation_key
        clear_cache = mapper.clear_cache
        get_conversation_id = mapper.get_conversation_id
        persist_conversation_id = mapper.persist_conversation_id

        chat_id = "12345"
        key_no_thread = build_conversation_key("telegram", chat_id, None)
        key_empty_thread = build_conversation_key("telegram", chat_id, "")
        key_none_text_thread = build_conversation_key("telegram", chat_id, "None")

        print(f"key_no_thread={key_no_thread}")
        print(f"key_empty_thread={key_empty_thread}")
        print(f"key_none_text_thread={key_none_text_thread}")

        if not (key_no_thread == key_empty_thread == key_none_text_thread):
            print("FAIL: key normalization mismatch")
            return 1

        expected_conversation_id = "conv-gateway-regression-001"
        await persist_conversation_id(key_no_thread, expected_conversation_id)

        resolved_first = await get_conversation_id(key_no_thread)
        print(f"resolved_first={resolved_first}")
        if resolved_first != expected_conversation_id:
            print("FAIL: cannot read conversation mapping after persist")
            return 1

        clear_cache()
        resolved_after_clear = await get_conversation_id(key_no_thread)
        print(f"resolved_after_clear={resolved_after_clear}")
        if resolved_after_clear != expected_conversation_id:
            print("FAIL: mapping not restored from persistent store")
            return 1

        print("PASS: gateway session mapper persistence and normalization OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
