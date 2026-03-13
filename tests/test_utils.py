"""Test token counter and context budget utilities."""

from agent.utils.token_counter import count_tokens, truncate_to_tokens, fits_budget
from agent.utils.context_budget import prepare_context, get_output_budget, estimate_cost


def test_token_counter():
    print("── Token Counter ──")

    # Basic counting
    text = "Hello, world!"
    tokens = count_tokens(text)
    print(f"'{text}' = {tokens} tokens")
    assert tokens > 0

    # Empty string
    assert count_tokens("") == 0
    print("Empty string = 0 tokens")

    # Budget check
    assert fits_budget("short text", 100)
    assert not fits_budget("short text", 1)
    print("fits_budget works correctly")

    # Truncation
    long_text = "word " * 500  # ~500 tokens
    truncated = truncate_to_tokens(long_text, 50)
    truncated_tokens = count_tokens(truncated)
    print(f"Truncated {count_tokens(long_text)} tokens → {truncated_tokens} tokens (budget: 50)")
    assert truncated_tokens <= 60  # some overhead from the truncation message
    assert "truncated" in truncated

    # No truncation needed
    short = "hello world"
    assert truncate_to_tokens(short, 100) == short
    print("Short text not truncated")
    print()


def test_context_budget():
    print("── Context Budget ──")

    # Prepare context for signal extraction (budget: 800)
    pieces = {
        "logs": "error log " * 100,       # ~200 tokens
        "metadata": "task info " * 50,     # ~100 tokens
        "signals": "signal data " * 30,    # ~60 tokens
    }
    result = prepare_context("signal_extraction", pieces)
    total = sum(count_tokens(v) for v in result.values() if v)
    print(f"signal_extraction: {total} tokens (budget: 800)")
    assert total <= 800

    # Prepare context with oversized input
    oversized = {
        "logs": "error log " * 1000,  # way over budget
        "metadata": "task info " * 100,
    }
    result = prepare_context("signal_extraction", oversized)
    total = sum(count_tokens(v) for v in result.values() if v)
    print(f"Oversized input trimmed to: {total} tokens (budget: 800)")
    assert total <= 800

    # Output budgets
    print(f"signal_extraction output: {get_output_budget('signal_extraction')}")
    print(f"root_cause_reasoning output: {get_output_budget('root_cause_reasoning')}")
    assert get_output_budget("signal_extraction") == 300
    assert get_output_budget("root_cause_reasoning") == 1000

    # Cost estimation
    mini_cost = estimate_cost("signal_extraction", 500, 200)
    gpt4_cost = estimate_cost("root_cause_reasoning", 3000, 800)
    print(f"signal_extraction cost (500 in, 200 out): ${mini_cost:.6f}")
    print(f"root_cause_reasoning cost (3000 in, 800 out): ${gpt4_cost:.6f}")
    assert mini_cost < gpt4_cost  # GPT-4o should cost more
    print()


if __name__ == "__main__":
    test_token_counter()
    test_context_budget()
    print("All utility tests passed.")
