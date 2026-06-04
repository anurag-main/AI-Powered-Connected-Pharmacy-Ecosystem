"""Deterministic TOOLS for the Smart Reorder Agent.

These are plain, testable functions — NO LLM, NO randomness. The agent (built
later in app/ai/nodes/ + app/ai/graphs/) will CALL these for the math, and use
the LLM only for fuzzy judgment. Senior rule: math = code, agent = decisions.

The "brain" in one line:
    how fast a medicine LEAVES (daily_velocity) vs how long resupply TAKES
    (lead_time). Reorder when days_of_cover < lead_time + safety_buffer.

Fill these in one at a time. Start with `days_of_cover` (smallest, teaches the
divide-by-zero trap), then run /review before moving to the next.
"""
import math

# A hard ceiling so a buggy/absurd suggestion can never propose a giant order.
# Used by is_qty_sane as the self-correction guardrail.
MAX_REORDER_QTY = 100_000


def days_of_cover(current_stock: float, daily_velocity: float) -> float:
    """How many days until stock hits zero, at the current sell-through speed.

    5 strips left, 1 sold/day  -> 5.0 days of cover.
    0 velocity (never sells)   -> treat as 'infinite' (never reorder).
    """
    # YOUR JOB:
    # 1. if daily_velocity <= 0: return float('inf')   (guard FIRST — no divide-by-zero)
    # 2. otherwise return current_stock / daily_velocity
    
    if daily_velocity <=0 :
        return float("inf")
    
    return current_stock / daily_velocity
    ...


def suggest_reorder_qty(daily_velocity: float, lead_time_days: int, safety_days: int) -> int:
    """How many units to order so we don't run dry while the supplier resupplies.

    Cover (lead_time + safety) days of demand. Round UP (you can't order half a
    strip) and return a whole number.
    """
    # YOUR JOB:
    # 1. days_to_cover = lead_time_days + safety_days
    # 2. qty = daily_velocity * days_to_cover
    # 3. round UP to a whole int (hint: math.ceil) and return it
    
    days_of_cover = lead_time_days + safety_days 
    qty = days_of_cover * daily_velocity
    
    return math.ceil(qty)
    
    ...


def is_qty_sane(qty: int) -> bool:
    """Self-correction guardrail: reject absurd or impossible quantities.

    The agent's math could go wrong (or an LLM could hallucinate a number);
    this is the net that stops a 9,000,000-unit order from ever being proposed.
    """
    # YOUR JOB:
    # return True only if qty is > 0 AND qty <= MAX_REORDER_QTY ; else False
    return qty > 0 and qty <= MAX_REORDER_QTY 
    ...


# ============================================================================
# Smoke test — run the pure functions with NO database:
#     python -m app.ai.tools.reorder_tools
# (get_reorder_candidates is tested later, once it's implemented.)
# ============================================================================

if __name__ == "__main__":
    print("========== reorder_tools (pure math) ==========")
    print("5 stock / 1 per day  ->", days_of_cover(5, 1))      # expect 5.0
    print("10 stock / 0 sales   ->", days_of_cover(10, 0))     # expect inf
    print("suggest (vel=2, lead=3, safety=2) ->", suggest_reorder_qty(2, 3, 2))  # expect 10
    print("is_qty_sane(10)      ->", is_qty_sane(10))          # expect True
    print("is_qty_sane(-3)      ->", is_qty_sane(-3))          # expect False
