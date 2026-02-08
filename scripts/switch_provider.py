#!/usr/bin/env python3
"""
LLM Provider Switch Tool

Switch all LLM configurations by changing agent.provider in config.yaml.
The provider_templates in config/llm_profiles.yaml handle the rest.

Usage:
    python scripts/switch_provider.py --to claude
    python scripts/switch_provider.py --to qwen
    python scripts/switch_provider.py --status
"""

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTANCES_DIR = PROJECT_ROOT / "instances"

# ============================================================
# ANSI colors
# ============================================================

def color(text: str, c: str) -> str:
    """Apply ANSI color."""
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "bold": "1"}
    return f"\033[{codes.get(c, '0')}m{text}\033[0m"


# ============================================================
# Core functions
# ============================================================

def find_instance_dir(instance_name: str = "") -> Path:
    """Find instance directory. Auto-detect if only one exists."""
    if instance_name:
        d = INSTANCES_DIR / instance_name
        if d.exists():
            return d
        print(color(f"Instance '{instance_name}' not found", "red"))
        sys.exit(1)

    # Auto-detect: list non-template instances
    candidates = [
        d for d in INSTANCES_DIR.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and not d.name.endswith("_backup")
        and (d / "config.yaml").exists()
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        print(color("No instances found", "red"))
        sys.exit(1)

    print("Multiple instances found, specify with --instance:")
    for c in candidates:
        print(f"  {c.name}")
    sys.exit(1)


def get_current_provider(instance_dir: Path) -> str:
    """Read current agent.provider from config.yaml."""
    config_path = instance_dir / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config.get("agent", {}).get("provider", "(not set)")


def get_provider_templates(instance_dir: Path) -> dict:
    """Read provider_templates from config/llm_profiles.yaml."""
    llm_path = instance_dir / "config" / "llm_profiles.yaml"
    if not llm_path.exists():
        return {}
    with open(llm_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("provider_templates", {})


def show_status(instance_dir: Path):
    """Display current provider status."""
    current = get_current_provider(instance_dir)
    templates = get_provider_templates(instance_dir)

    print(f"\nInstance: {color(instance_dir.name, 'cyan')}")
    print(f"Provider: {color(current, 'green' if current in templates else 'yellow')}")

    if current in templates:
        tmpl = templates[current]
        print(f"\nModel assignment:")
        print(f"  Agent:  {tmpl.get('agent_model', '?')}")
        heavy = tmpl.get("heavy", {})
        light = tmpl.get("light", {})
        print(f"  Heavy:  {heavy.get('model', '?')} ({heavy.get('provider', '?')})")
        print(f"  Light:  {light.get('model', '?')} ({light.get('provider', '?')})")

        agent_llm = tmpl.get("agent_llm", {})
        if agent_llm:
            print(f"\n  Agent LLM params:")
            for k, v in agent_llm.items():
                print(f"    {k}: {v}")

    print(f"\nAvailable providers: {', '.join(templates.keys()) or '(none)'}")


def switch_provider(instance_dir: Path, target: str, dry_run: bool = False):
    """Switch agent.provider in config.yaml."""
    templates = get_provider_templates(instance_dir)
    if target not in templates:
        print(color(
            f"Provider '{target}' not in templates. "
            f"Available: {', '.join(templates.keys())}",
            "red"
        ))
        sys.exit(1)

    current = get_current_provider(instance_dir)
    if current == target:
        print(f"Already using {color(target, 'green')}, nothing to do.")
        return

    config_path = instance_dir / "config.yaml"

    # Read file as text to preserve formatting/comments
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace provider value (handles both quoted and unquoted)
    import re
    new_content = re.sub(
        r'(provider:\s*)"?[\w-]+"?',
        f'\\1"{target}"',
        content,
        count=1,
    )

    if new_content == content:
        print(color("Could not find 'provider:' field in config.yaml", "red"))
        sys.exit(1)

    if dry_run:
        print(f"[DRY RUN] Would switch: {color(current, 'yellow')} → {color(target, 'green')}")
        tmpl = templates[target]
        print(f"  Agent model: {tmpl.get('agent_model')}")
        print(f"  Heavy: {tmpl.get('heavy', {}).get('model')}")
        print(f"  Light: {tmpl.get('light', {}).get('model')}")
        return

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Switched: {color(current, 'yellow')} → {color(target, 'green')}")

    tmpl = templates[target]
    print(f"\nNew model assignment:")
    print(f"  Agent:  {tmpl.get('agent_model')}")
    print(f"  Heavy:  {tmpl.get('heavy', {}).get('model')}")
    print(f"  Light:  {tmpl.get('light', {}).get('model')}")

    # Check API key
    heavy_env = tmpl.get("heavy", {}).get("api_key_env", "")
    if heavy_env and not __import__("os").getenv(heavy_env):
        print(color(f"\n  Warning: {heavy_env} not set in environment", "yellow"))


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Switch LLM provider for an instance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/switch_provider.py --status
  python scripts/switch_provider.py --to claude
  python scripts/switch_provider.py --to qwen --dry-run
  python scripts/switch_provider.py --to claude --instance xiaodazi
""",
    )
    parser.add_argument("--to", type=str, help="Target provider (qwen / claude)")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes")
    parser.add_argument("--instance", type=str, default="", help="Instance name")
    args = parser.parse_args()

    instance_dir = find_instance_dir(args.instance)

    if args.status or not args.to:
        show_status(instance_dir)
    else:
        switch_provider(instance_dir, args.to, args.dry_run)


if __name__ == "__main__":
    main()
