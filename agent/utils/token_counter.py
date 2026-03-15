"""
token_counter.py — Token counting and text truncation utilities.

Uses tiktoken to count tokens accurately for OpenAI models.
Each LLM-calling node has a max input token budget. Before
calling the LLM, context is truncated to fit within the budget.

Blueprint reference: Section 15 (Cost and Token Management)
"""

import tiktoken


# Use cl100k_base encoding — works for GPT-4o and GPT-4o-mini
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count the number of tokens in a text string."""
    if not text:
        return 0
    return len(_ENCODING.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token budget.

    Truncates from the beginning, keeping the end of the text
    since the most recent/relevant content is usually at the end
    (e.g., error messages in logs).

    Args:
        text: The text to truncate.
        max_tokens: Maximum number of tokens allowed.

    Returns:
        Truncated text that fits within the budget.
    """
    if not text:
        return ""

    tokens = _ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return text

    # Keep the last max_tokens tokens
    truncated_tokens = tokens[-max_tokens:]
    truncated_text = _ENCODING.decode(truncated_tokens)

    return f"... [truncated, {len(tokens) - max_tokens} tokens removed] ...\n{truncated_text}"


def fits_budget(text: str, max_tokens: int) -> bool:
    """Check if text fits within a token budget."""
    return count_tokens(text) <= max_tokens
