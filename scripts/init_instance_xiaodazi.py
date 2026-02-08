"""
Re-initialize instance xiaodazi: create .env from template, prompt_results.

Run from project root:
    python scripts/init_instance_xiaodazi.py
"""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTANCES = PROJECT_ROOT / "instances"
TEMPLATE = INSTANCES / "_template"
XIAODAZI = INSTANCES / "xiaodazi"


def main() -> int:
    if not XIAODAZI.is_dir():
        print(f"Error: instance dir not found: {XIAODAZI}")
        return 1

    # 1. .env (only if missing)
    env_dst = XIAODAZI / ".env"
    if not env_dst.exists():
        shutil.copy(TEMPLATE / "env.example", env_dst)
        print("Created instances/xiaodazi/.env (please set ANTHROPIC_API_KEY etc.)")
    else:
        print("instances/xiaodazi/.env already exists, skipped")

    # 2. prompt_results/
    pr = XIAODAZI / "prompt_results"
    pr.mkdir(parents=True, exist_ok=True)
    readme_pr = pr / "README.md"
    if not readme_pr.exists():
        shutil.copy(TEMPLATE / "prompt_results" / "README.md", readme_pr)
        print("Created instances/xiaodazi/prompt_results/README.md")
    print("instances/xiaodazi/prompt_results/ ready")

    print("instances/xiaodazi re-initialized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
