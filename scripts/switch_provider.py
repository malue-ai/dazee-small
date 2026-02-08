#!/usr/bin/env python3
"""
LLM Provider Switch Tool

Quickly switch all LLM configurations between Claude and Qwen.

Usage:
    python scripts/switch_provider.py --to claude
    python scripts/switch_provider.py --to qwen --region singapore
    python scripts/switch_provider.py --status
    python scripts/switch_provider.py --to claude --dry-run
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# Constants
# ============================================================

PROFILES_YAML = PROJECT_ROOT / "config" / "llm_config" / "profiles.yaml"

# Model mappings: qwen ↔ claude
QWEN_TO_CLAUDE = {
    "qwen3-max": "claude-sonnet-4-5-20250929",
    "qwen-plus": "claude-haiku-3-5-20241022",
    "qwen-vl-max": "claude-sonnet-4-5-20250929",
}
CLAUDE_TO_QWEN = {
    "claude-sonnet-4-5-20250929": "qwen3-max",
    "claude-haiku-3-5-20241022": "qwen-plus",
    "claude-opus-4-20250514": "qwen3-max",
    "claude-sonnet-4-20250514": "qwen3-max",
}

API_KEY_ENVS = {"claude": "ANTHROPIC_API_KEY", "qwen": "DASHSCOPE_API_KEY"}
CACHING_DEFAULTS = {"claude": "true", "qwen": "false"}
FLAGSHIP_MODELS = {"claude": "claude-sonnet-4-5-20250929", "qwen": "qwen3-max"}

CLAUDE_MAX_OUTPUT = 128000
QWEN_MAIN_MAX_TOKENS = 262144


# ============================================================
# Utilities
# ============================================================


def color(text: str, code: str) -> str:
    """ANSI color wrapper."""
    codes = {
        "green": "32",
        "red": "31",
        "yellow": "33",
        "cyan": "36",
        "bold": "1",
        "dim": "2",
    }
    return f"\033[{codes.get(code, '0')}m{text}\033[0m"


def map_model(current: str, target: str) -> str:
    """Map model name to target provider's equivalent."""
    if target == "claude":
        return QWEN_TO_CLAUDE.get(current, current)
    return CLAUDE_TO_QWEN.get(current, current)


def extract_quoted(line: str) -> Optional[str]:
    """Extract first quoted value from a line."""
    m = re.search(r'["\']([^"\']+)["\']', line)
    return m.group(1) if m else None


def extract_value(line: str) -> str:
    """Extract raw value after the first colon."""
    return line.split(":", 1)[1].strip()


def get_indent(line: str) -> str:
    """Get leading whitespace of a line."""
    return line[: len(line) - len(line.lstrip())]


def detect_provider(content: str) -> str:
    """Detect current provider from first provider: line in file."""
    for line in content.split("\n"):
        stripped = line.strip()
        if re.match(r"provider:\s*", stripped) and not stripped.startswith("#"):
            return extract_quoted(line) or extract_value(line)
    return "unknown"


# ============================================================
# Processors
# ============================================================


def process_profiles_yaml(
    content: str, target: str, region: str
) -> Tuple[str, List[str]]:
    """Process profiles.yaml line by line, preserving all comments and formatting.

    Returns:
        (new_content, list_of_change_descriptions)
    """
    lines = content.split("\n")
    out: List[str] = []
    changes: List[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip comments and blanks
        if not stripped or stripped.startswith("#"):
            out.append(line)
            i += 1
            continue

        indent = get_indent(line)

        # --- provider ---
        if re.match(r"provider:\s*", stripped):
            old = extract_quoted(line) or extract_value(line)
            if old != target:
                out.append(f'{indent}provider: "{target}"')
                changes.append(f"provider: {old} → {target}")
            else:
                out.append(line)
            i += 1
            continue

        # --- model ---
        if re.match(r"model:\s*", stripped):
            old = extract_quoted(line) or extract_value(line)
            new = map_model(old, target)
            if old != new:
                cm = re.search(r"(#.*)$", line)
                comment = f"  {cm.group(1)}" if cm else ""
                out.append(f'{indent}model: "{new}"{comment}')
                changes.append(f"model: {old} → {new}")
            else:
                out.append(line)
            i += 1
            continue

        # --- api_key_env ---
        if re.match(r"api_key_env:\s*", stripped):
            old = extract_quoted(line) or extract_value(line)
            new_env = API_KEY_ENVS[target]
            if old != new_env:
                out.append(f'{indent}api_key_env: "{new_env}"')
                changes.append(f"api_key_env: {old} → {new_env}")
                # Insert region for qwen if next line is not region
                if target == "qwen":
                    nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    if not nxt.startswith("region:"):
                        out.append(f'{indent}region: "{region}"')
                        changes.append(f"+ region: {region}")
            else:
                out.append(line)
            i += 1
            continue

        # --- region ---
        if re.match(r"region:\s*", stripped):
            if target == "claude":
                # Remove region line for Claude
                changes.append("- region (removed)")
                i += 1
                continue
            else:
                old = extract_quoted(line) or extract_value(line)
                if old != region:
                    out.append(f'{indent}region: "{region}"')
                    changes.append(f"region: {old} → {region}")
                else:
                    out.append(line)
            i += 1
            continue

        # --- enable_caching ---
        if re.match(r"enable_caching:\s*", stripped):
            old = extract_value(line)
            new_val = CACHING_DEFAULTS[target]
            if old != new_val:
                out.append(f"{indent}enable_caching: {new_val}")
                changes.append(f"enable_caching: {old} → {new_val}")
            else:
                out.append(line)
            i += 1
            continue

        # --- max_tokens: cap for Claude ---
        if re.match(r"max_tokens:\s*\d", stripped):
            m = re.search(r"(\d+)", stripped)
            if m:
                val = int(m.group(1))
                # Cap for Claude
                if target == "claude" and val > CLAUDE_MAX_OUTPUT:
                    out.append(
                        f"{indent}max_tokens: {CLAUDE_MAX_OUTPUT}  # capped (was {val})"
                    )
                    changes.append(f"max_tokens: {val} → {CLAUDE_MAX_OUTPUT}")
                    i += 1
                    continue
                # Restore from cap comment
                cap = re.search(r"#.*was (\d+)", line)
                if target == "qwen" and cap:
                    restored = cap.group(1)
                    out.append(f"{indent}max_tokens: {restored}")
                    changes.append(f"max_tokens: {val} → {restored}")
                    i += 1
                    continue
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out), changes


def process_config_yaml(content: str, target: str) -> Tuple[str, List[str]]:
    """Process instance config.yaml (agent section only).

    Returns:
        (new_content, list_of_change_descriptions)
    """
    lines = content.split("\n")
    out: List[str] = []
    changes: List[str] = []
    in_agent = False
    in_llm = False

    for line in lines:
        stripped = line.strip()

        # Track agent section entry
        if line.startswith("agent:"):
            in_agent = True
            out.append(line)
            continue

        # Track agent section exit (next top-level key)
        if (
            in_agent
            and line
            and not line[0].isspace()
            and stripped
            and not stripped.startswith("#")
        ):
            in_agent = False
            in_llm = False

        # Track llm subsection
        if in_agent and stripped == "llm:":
            in_llm = True
            out.append(line)
            continue

        if not in_agent:
            out.append(line)
            continue

        indent = get_indent(line)

        # agent.model (not under llm)
        if not in_llm and re.match(r"model:\s*", stripped):
            old = extract_quoted(line) or extract_value(line)
            new_model = FLAGSHIP_MODELS[target]
            if old != new_model:
                out.append(f'{indent}model: "{new_model}"')
                changes.append(f"agent.model: {old} → {new_model}")
            else:
                out.append(line)
            continue

        # agent.llm.enable_caching
        if in_llm and re.match(r"enable_caching:\s*", stripped):
            old = extract_value(line)
            new_val = CACHING_DEFAULTS[target]
            if old != new_val:
                out.append(f"{indent}enable_caching: {new_val}")
                changes.append(f"agent.llm.enable_caching: {old} → {new_val}")
            else:
                out.append(line)
            continue

        # agent.llm.max_tokens
        if in_llm and re.match(r"max_tokens:\s*", stripped):
            m = re.search(r"(\d+)", stripped)
            if m:
                val = int(m.group(1))
                if target == "claude" and val > CLAUDE_MAX_OUTPUT:
                    out.append(f"{indent}max_tokens: {CLAUDE_MAX_OUTPUT}")
                    changes.append(
                        f"agent.llm.max_tokens: {val} → {CLAUDE_MAX_OUTPUT}"
                    )
                    continue
                if target == "qwen" and val == CLAUDE_MAX_OUTPUT:
                    out.append(f"{indent}max_tokens: {QWEN_MAIN_MAX_TOKENS}")
                    changes.append(
                        f"agent.llm.max_tokens: {val} → {QWEN_MAIN_MAX_TOKENS}"
                    )
                    continue
            out.append(line)
            continue

        out.append(line)

    return "\n".join(out), changes


# ============================================================
# API Key Check
# ============================================================


def check_api_key(instance: str, target: str) -> bool:
    """Check if target provider's API key is available."""
    env_var = API_KEY_ENVS[target]

    # Check .env file
    env_path = PROJECT_ROOT / "instances" / instance / ".env"
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            line = line.strip()
            if line.startswith(env_var) and "=" in line:
                val = line.split("=", 1)[1].strip()
                if val and not val.startswith("#"):
                    return True

    # Check system environment
    return bool(os.environ.get(env_var))


# ============================================================
# Status Display
# ============================================================


def show_status(instance: str) -> None:
    """Display current provider configuration status."""
    print(f"\n{color('=== LLM Provider Status ===', 'bold')}\n")

    # profiles.yaml
    if PROFILES_YAML.exists():
        content = PROFILES_YAML.read_text()
        provider = detect_provider(content)
        print(f"  profiles.yaml provider: {color(provider, 'cyan')}")

        # Count models
        models: Dict[str, int] = {}
        for line in content.split("\n"):
            stripped = line.strip()
            if re.match(r"model:\s*", stripped) and not stripped.startswith("#"):
                model = extract_quoted(line) or extract_value(line)
                models[model] = models.get(model, 0) + 1
        print("  Models in use:")
        for m, count in sorted(models.items()):
            print(f"    {m}: {count} profile(s)")
    else:
        print(color(f"  ⚠ profiles.yaml not found", "yellow"))

    # Instance config.yaml
    config_path = PROJECT_ROOT / "instances" / instance / "config.yaml"
    if config_path.exists():
        content = config_path.read_text()
        for line in content.split("\n"):
            stripped = line.strip()
            if re.match(r"model:\s*", stripped) and not stripped.startswith("#"):
                model = extract_quoted(line) or extract_value(line)
                print(
                    f"\n  config.yaml agent.model: {color(model, 'cyan')}"
                )
                break
    else:
        print(color(f"\n  ⚠ instances/{instance}/config.yaml not found", "yellow"))

    # API keys
    print(f"\n  API Keys:")
    for p, env_var in API_KEY_ENVS.items():
        available = check_api_key(instance, p)
        status = (
            color("✓ available", "green")
            if available
            else color("✗ not found", "red")
        )
        print(f"    {env_var}: {status}")

    print()


# ============================================================
# Main
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Switch LLM provider between Claude and Qwen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --to claude                    Switch to Claude
  %(prog)s --to qwen --region singapore   Switch to Qwen (Singapore)
  %(prog)s --status                       Show current status
  %(prog)s --to claude --dry-run          Preview changes without writing
        """,
    )
    parser.add_argument("--to", choices=["claude", "qwen"], help="Target provider")
    parser.add_argument(
        "--instance", default="xiaodazi", help="Instance name (default: xiaodazi)"
    )
    parser.add_argument(
        "--region", default="singapore", help="Qwen region (default: singapore)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show current provider status"
    )

    args = parser.parse_args()

    if args.status:
        show_status(args.instance)
        return

    if not args.to:
        parser.error("--to is required (use --status to check current config)")

    target: str = args.to
    instance: str = args.instance
    region: str = args.region
    dry_run: bool = args.dry_run

    print(f"\n{color(f'=== Switching to {target.upper()} ===', 'bold')}")
    if dry_run:
        print(color("  (dry run — no files will be modified)\n", "yellow"))
    else:
        print()

    all_changes: Dict[str, List[str]] = {}

    # 1. profiles.yaml
    if PROFILES_YAML.exists():
        content = PROFILES_YAML.read_text()
        current = detect_provider(content)

        if current == target:
            print(
                f"  {color('profiles.yaml', 'cyan')}: already using {target}, skipping"
            )
        else:
            new_content, changes = process_profiles_yaml(content, target, region)
            if changes:
                all_changes["profiles.yaml"] = changes
                if not dry_run:
                    PROFILES_YAML.write_text(new_content)
    else:
        print(color(f"  ⚠ profiles.yaml not found", "yellow"))

    # 2. config.yaml
    config_path = PROJECT_ROOT / "instances" / instance / "config.yaml"
    if config_path.exists():
        content = config_path.read_text()
        new_content, changes = process_config_yaml(content, target)
        if changes:
            all_changes[f"instances/{instance}/config.yaml"] = changes
            if not dry_run:
                config_path.write_text(new_content)
        else:
            print(
                f"  {color(f'instances/{instance}/config.yaml', 'cyan')}: no changes needed"
            )
    else:
        print(color(f"  ⚠ instances/{instance}/config.yaml not found", "yellow"))

    # 3. Print change summary
    if all_changes:
        for file, changes in all_changes.items():
            # Count duplicate changes
            counts: Dict[str, int] = {}
            for c in changes:
                counts[c] = counts.get(c, 0) + 1

            total = len(changes)
            print(f"\n  {color(file, 'cyan')} ({total} changes):")
            for c, count in counts.items():
                suffix = f" (×{count})" if count > 1 else ""
                print(f"    {color('→', 'green')} {c}{suffix}")
    else:
        print(f"\n  No changes needed — already using {target}.")

    # 4. API key check
    print()
    has_key = check_api_key(instance, target)
    env_var = API_KEY_ENVS[target]
    if has_key:
        print(f"  {color('✓', 'green')} {env_var} found")
    else:
        print(f"  {color('⚠', 'red')} {env_var} not found!")
        print(f"    Set it in instances/{instance}/.env or system environment")

    # 5. Final summary
    if dry_run:
        print(f"\n{color('Dry run complete. No files were modified.', 'yellow')}")
        print(f"Remove --dry-run to apply changes.\n")
    elif all_changes:
        total = sum(len(c) for c in all_changes.values())
        print(f"\n{color(f'✓ Done! {total} changes applied.', 'green')}")
        print(f"Restart the server to take effect.\n")
    else:
        print()


if __name__ == "__main__":
    main()
