"""
Default model IDs for all LLM providers.

This is the SINGLE SOURCE OF TRUTH for default model names in code.
All factory functions, registry registrations, and fallback values
should import from here instead of hardcoding model IDs.

To upgrade a model, change the value here + the corresponding
provider_templates in llm_profiles.yaml.

Long-term goal: code reads defaults from llm_profiles.yaml at runtime,
making this file unnecessary. Until then, this file prevents scattered
hardcoded model IDs across the codebase.
"""

DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "gemini": "gemini-pro",
    "qwen": "qwen3-max",
    "deepseek": "deepseek-reasoner",
    "glm": "glm-5",
    "minimax": "MiniMax-M2.5",
    "kimi": "kimi-k2.5",
}


def get_default_model(provider: str) -> str:
    """Return the default model ID for a given provider name."""
    return DEFAULT_MODELS[provider]
