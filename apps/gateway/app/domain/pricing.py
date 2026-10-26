"""Money and token accounting primitives.

All money is Decimal. Token estimation is an explicit, documented heuristic
(~4 chars/token) used ONLY when a provider reports no usage; the provenance
(usage_source / cost_basis) is always recorded alongside any figure.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

COST_QUANT = Decimal("0.00000001")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):  # OpenAI content parts
            content = " ".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        total += estimate_tokens(str(content)) + 4  # per-message overhead
    return total


def calculate_cost(
    input_tokens: int, output_tokens: int, input_price_per_token, output_price_per_token
) -> Decimal:
    in_price = Decimal(str(input_price_per_token))
    out_price = Decimal(str(output_price_per_token))
    cost = (Decimal(input_tokens) * in_price) + (Decimal(output_tokens) * out_price)
    return cost.quantize(COST_QUANT, rounding=ROUND_HALF_UP)


def reserve_estimate(
    input_tokens: int, max_output_tokens: int, input_price_per_token, output_price_per_token
) -> Decimal:
    """Conservative reservation: full requested output at the route's price."""
    return calculate_cost(input_tokens, max_output_tokens, input_price_per_token, output_price_per_token)
