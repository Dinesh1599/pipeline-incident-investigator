"""
llm_caller.py — Centralized LLM call utility with retry and JSON parsing.

Wraps every LLM call with:
    - JSON response parsing with markdown fence handling
    - Retry on malformed JSON (2 retries max, with reformatting prompt)
    - Fallback to regex extraction of key fields on final failure
    - Logging of token usage and cost
"""

import json
import logging
import re

from langchain_openai import ChatOpenAI

from agent.utils.config import LLM_TEMPERATURE, LLM_MAX_RETRIES

logger = logging.getLogger(__name__)


def call_llm_json(
    model: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 500,
    node_name: str = "unknown",
) -> dict:
    """Call an LLM and parse the JSON response with retry logic.

    Args:
        model: OpenAI model name (e.g., 'gpt-4o', 'gpt-4o-mini')
        system_prompt: System prompt text
        user_message: User message text
        max_tokens: Max output tokens
        node_name: Name of the calling node (for logging)

    Returns:
        Parsed JSON dict. Returns empty dict on complete failure.
    """
    llm = ChatOpenAI(
        model=model,
        temperature=LLM_TEMPERATURE,
        max_tokens=max_tokens,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # First attempt
    try:
        response = llm.invoke(messages)
        result = parse_json_response(response.content)
        return result
    except json.JSONDecodeError:
        logger.warning("[%s] Malformed JSON on first attempt, retrying...", node_name)
    except Exception as e:
        logger.error("[%s] LLM call failed: %s", node_name, e)
        return {}

    # Retry with reformatting instruction
    for attempt in range(LLM_MAX_RETRIES):
        try:
            retry_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    "Your previous response was not valid JSON. "
                    "Respond with ONLY valid JSON matching the schema. "
                    "No explanation, no markdown fences, just the JSON object.\n\n"
                    + user_message
                )},
            ]
            response = llm.invoke(retry_messages)
            result = parse_json_response(response.content)
            logger.info("[%s] Retry %d succeeded", node_name, attempt + 1)
            return result
        except json.JSONDecodeError:
            logger.warning(
                "[%s] Retry %d failed — still malformed JSON",
                node_name, attempt + 1,
            )
        except Exception as e:
            logger.error("[%s] Retry %d failed: %s", node_name, attempt + 1, e)
            return {}

    # Final fallback: try to extract any JSON from the response
    logger.error("[%s] All retries failed, attempting regex extraction", node_name)
    try:
        return extract_json_fallback(response.content)
    except Exception:
        logger.error("[%s] Regex extraction also failed, returning empty", node_name)
        return {}


def parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return json.loads(cleaned.strip())


def extract_json_fallback(text: str) -> dict:
    """Last-resort extraction: find any JSON object in the text."""
    # Try to find a JSON object
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise json.JSONDecodeError("No JSON found", text, 0)
