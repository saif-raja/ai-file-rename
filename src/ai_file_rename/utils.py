"""
Shared utility functions for ai-file-rename.

Small helpers used across multiple pipeline stages.
"""


def _extract_token_counts(response) -> dict:
    """Extract token usage from a Gemini response, falling back to 0."""
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            return {
                "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
            }
    except Exception:
        pass
    return {"input_tokens": 0, "output_tokens": 0}


def _add_token_counts(a: dict, b: dict) -> dict:
    """Sum two token count dicts."""
    return {
        "input_tokens": a.get("input_tokens", 0) + b.get("input_tokens", 0),
        "output_tokens": a.get("output_tokens", 0) + b.get("output_tokens", 0),
    }
