"""Fuzzy catalog matching helpers.

Voice transcription mangles medicine names ("crossing 200mg" for "Crocin 500mg").
Exact lookup fails on these. This module narrows the full catalog down to a few
plausible candidates per spoken name using fuzzy string similarity; the LLM then
confirms the best one (see app/ai/nodes/resolve_medicine.py).

Why fuzzy FIRST, then LLM:
    - Fuzzy is free + instant and scales: it trims thousands of catalog names to
      ~5 candidates without an LLM call.
    - The LLM then reasons over a tiny list (cheap) to pick the right one, using
      pharmacy + phonetic context fuzzy alone can't.
"""
from rapidfuzz import fuzz, process

# WRatio blends several strategies (ratio, partial, token-set) and handles word
# order + length differences well — a good general-purpose name matcher.
_SCORER = fuzz.WRatio

# Keep candidates scoring at least this (0-100). Low enough to catch sound-alikes
# like "crossing 200mg" vs "Crocin 500mg"; high enough to drop pure noise.
_SCORE_CUTOFF = 50

# Most candidates we hand to the LLM per item.
_LIMIT = 5


def shortlist(spoken_name: str, catalog_names: list[str]) -> list[str]:
    """Return up to _LIMIT catalog names most similar to `spoken_name`.

    Best match first. Empty list if nothing clears the cutoff (truly unknown).
    """
    results = process.extract(
        spoken_name,
        catalog_names,
        scorer=_SCORER,
        limit=_LIMIT,
        score_cutoff=_SCORE_CUTOFF,
    )
    # process.extract returns (name, score, index) tuples, already sorted desc.
    return [name for (name, _score, _idx) in results]
