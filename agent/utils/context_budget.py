"""
context_budget.py — Manages token budgets per LLM-calling node.

Each node has a defined input token budget. Before calling the LLM,
all context pieces are measured and truncated to fit. This prevents
exceeding model context windows and controls cost.

Budget allocations per node:
    Signal Extraction  — 800 input, 300 output
    Classification     — 1200 input, 300 output
    Code Inspection    — 3000 input, 600 output
    Root Cause Reason  — 4000 input, 1000 output
    Fix Generation     — 2000 input, 600 output
"""

from agent.utils.token_counter import count_tokens, truncate_to_tokens


# Per-node token budgets (input tokens)
NODE_BUDGETS = {
    "signal_extraction": 800,
    "classification": 1200,
    "code_inspection": 3000,
    "root_cause_reasoning": 4000,
    "fix_generation": 2000,
}

# Per-node output token limits (for max_tokens parameter)
OUTPUT_BUDGETS = {
    "signal_extraction": 300,
    "classification": 300,
    "code_inspection": 600,
    "root_cause_reasoning": 1000,
    "fix_generation": 600,
}


def prepare_context(node_name: str, context_pieces: dict[str, str]) -> dict[str, str]:
    """Prepare context for a node by fitting pieces within the token budget.

    Prioritizes pieces in the order they are provided. Earlier pieces
    get their full allocation; later pieces get truncated if the
    budget is running low.

    Args:
        node_name: Name of the LLM node (must be in NODE_BUDGETS).
        context_pieces: Ordered dict of {label: text} pieces.
            Example: {"logs": "...", "metadata": "...", "signals": "..."}

    Returns:
        Dict of {label: text} with each piece truncated to fit budget.
    """
    budget = NODE_BUDGETS.get(node_name, 2000)
    remaining = budget
    prepared = {}

    for label, text in context_pieces.items():
        if not text:
            prepared[label] = ""
            continue

        tokens = count_tokens(text)
        if tokens <= remaining:
            prepared[label] = text
            remaining -= tokens
        elif remaining > 50:
            # Truncate to fit remaining budget, leaving some room
            prepared[label] = truncate_to_tokens(text, remaining - 10)
            remaining = 10
        else:
            prepared[label] = ""

    return prepared


def get_output_budget(node_name: str) -> int:
    """Get the max_tokens value for a node's LLM call."""
    return OUTPUT_BUDGETS.get(node_name, 500)


def estimate_cost(node_name: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate the cost of an LLM call in USD.

    Pricing:
        GPT-4o-mini: $0.15/1M input, $0.60/1M output
        GPT-4o:      $2.50/1M input, $10.00/1M output

    Signal extraction and classification use GPT-4o-mini.
    All other nodes use GPT-4o.
    """
    mini_nodes = {"signal_extraction", "classification"}

    if node_name in mini_nodes:
        return (input_tokens * 0.15 / 1_000_000) + (output_tokens * 0.60 / 1_000_000)
    else:
        return (input_tokens * 2.50 / 1_000_000) + (output_tokens * 10.00 / 1_000_000)
