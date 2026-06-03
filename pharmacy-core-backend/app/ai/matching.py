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
import re

from rapidfuzz import fuzz, process

# WRatio blends several strategies (ratio, partial, token-set) and handles word
# order + length differences well — a good general-purpose name matcher.
_SCORER = fuzz.WRatio

# Keep candidates scoring at least this (0-100). Low enough to catch sound-alikes
# like "mat cb" vs "mtac b"; high enough to drop pure noise.
_SCORE_CUTOFF = 50

# Most candidates we hand to the LLM per item.
_LIMIT = 5

# Dose tokens ("500mg", "10 mg", "5ml") and bare numbers add noise when comparing
# a spoken NAME ("mat cb") to a catalog entry ("Mtac B 500mg"). We strip them so
# the fuzzy score reflects the medicine NAME, not the dosage. The full catalog
# name is still what we return + display.
_DOSE = re.compile(r"\b\d+\s*(mg|ml|mcg|g|gm|iu)\b", re.IGNORECASE)
_NUM = re.compile(r"\b\d+\b")


def _name_key(s: str) -> str:
    """Lowercased name with dosage + bare numbers removed, for fuzzy comparison."""
    s = s.lower()
    s = _DOSE.sub(" ", s)
    s = _NUM.sub(" ", s)
    return " ".join(s.split())


def shortlist(spoken_name: str, catalog_names: list[str]) -> list[tuple[str, float]]:
    """Return up to _LIMIT (catalog_name, score) pairs most similar to `spoken_name`.

    Comparison is on dose-stripped name keys (so "mat cb" matches "Mtac B 500mg"),
    but the ORIGINAL catalog names are returned with their 0-100 score. Best match
    first; empty list if nothing clears the cutoff (truly unknown).
    """
    keys = [_name_key(n) for n in catalog_names]
    results = process.extract(
        _name_key(spoken_name),
        keys,
        scorer=_SCORER,
        limit=_LIMIT,
        score_cutoff=_SCORE_CUTOFF,
    )
    # process.extract returns (matched_key, score, index); map index → real name.
    return [(catalog_names[idx], score) for (_key, score, idx) in results]
