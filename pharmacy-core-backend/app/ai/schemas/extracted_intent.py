"""Pydantic schemas for the `extract_intent` node.

This file defines the EXACT shape the LLM must produce when it parses a
pharmacist's free-text sentence.

Analogy (kid-level):
    A notebook with boxes drawn on each page.
    - One MedicineItem = one filled page (Name / Quantity / Unit boxes).
    - One ExtractedIntent = the whole stack of pages + the customer's name
      and phone written at the top.
    - Pydantic = the strict mom who checks every box was filled correctly.

The LLM (Maverick) is forced into this shape by `llm.with_structured_output(ExtractedIntent)`
in app/ai/nodes/extract_intent.py.

Why split into two classes?
    Because a single sentence can mention MANY medicines.
    "2 strips Crocin and 1 bottle Benadryl" → ONE ExtractedIntent containing TWO MedicineItem entries.
    The customer info appears ONCE at the top, not duplicated per medicine.
"""
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================================
# MedicineItem  —  one notebook page (one medicine the customer asked for)
# ============================================================================

class MedicineItem(BaseModel):
    """One line in a pharmacist's order: medicine name + how many + what unit."""

    # YOUR JOB 1:
    # Field 1 — `name`
    #
    # Type: str
    # Required: yes (use Field(...))
    # description: pass a short description like
    #     "Medicine name exactly as the customer said it, e.g. 'Crocin 500mg'"
    # The description is what the LLM SEES — it influences what the LLM writes.
    #
    # Hint: name: str = Field(..., description="...")
    name: str = Field(..., description="Medicine name exactly as the customer said it, e.g. 'Crocin 500mg'")

    # YOUR JOB 2:
    # Field 2 — `quantity`
    #
    # Type: int
    # Required: yes
    # Constraints: ge=1 (at least 1), le=1000 (sanity cap — no one buys 5000 strips at once)
    # Why the cap? Last test, Mistral-Nemotron returned 2 × 10^400. Cap prevents the
    # invoice math from exploding even if a future model hallucinates.
    # description: e.g. "Whole number — how many units the customer asked for"
    #
    # Hint: quantity: int = Field(..., ge=1, le=1000, description="...")
    quantity: int = Field(..., ge=1, le=1000, description="Whole number quantity requested by the customer")

    # YOUR JOB 3:
    # Field 3 — `unit`
    #
    # Type: str
    # Required: yes
    # description: explain to the LLM what kind of word goes here
    #     e.g. "Packaging unit — one of: strip, bottle, tablet, ml, tube, sachet"
    # We're NOT using an Enum yet (Pydantic Literal could lock it down) — keep it str
    # for now so we don't reject sentences the LLM phrases creatively.
    # We'll tighten this in a later phase if needed.
    unit: str = Field(..., description="Packaging unit such as strip, bottle, tablet, ml, tube, sachet")

# ============================================================================
# ExtractedIntent  —  the whole stack of pages + the customer info
# ============================================================================

class ExtractedIntent(BaseModel):
    """One pharmacist sentence parsed into structured data the graph can use."""

    # YOUR JOB 4:
    # Field 1 — `items`
    #
    # Type: list[MedicineItem]
    # Required: yes
    # min_length=1 — every order must have at least 1 medicine, else the sentence
    #                was probably gibberish and we should reject early.
    # description: e.g. "One entry per medicine the customer asked for"
    #
    # Hint: items: list[MedicineItem] = Field(..., min_length=1, description="...")
    items: list[MedicineItem] = Field(..., min_length=1, description="One entry per medicine requested by the customer")

    # YOUR JOB 5:
    # Field 2 — `customer_name`
    #
    # Type: Optional[str]   (or `str | None` — both work in Python 3.13)
    # Required: NO — pharmacist may not always say the customer's name
    # default: None
    # description: e.g. "Customer's first name if the pharmacist mentioned one, else None"
    #
    # Hint: customer_name: Optional[str] = Field(None, description="...")
    customer_name: Optional[str] = Field(None, description="Customer name if mentioned, otherwise None")

    # YOUR JOB 6:
    # Field 3 — `customer_phone`
    #
    # Type: Optional[str]
    # Required: NO
    # default: None
    # description: e.g. "10-digit Indian phone number if mentioned, else None — digits only, no spaces"
    # We keep it as `str` (not int) because phone numbers can have leading zeros
    # in some countries, and int would drop them.
    #
    # Hint: customer_phone: Optional[str] = Field(None, description="...")
    customer_phone: Optional[str] = Field(None, description="10-digit customer phone number if mentioned, otherwise None")


# ============================================================================
# Manual smoke test  —  run `python -m app.ai.schemas.extracted_intent` to verify
# ============================================================================

if __name__ == "__main__":
    # Sanity test — does our schema build a valid example?
    example = ExtractedIntent(
        items=[
            MedicineItem(name="Crocin 500mg", quantity=2, unit="strip"),
            MedicineItem(name="Benadryl cough syrup", quantity=1, unit="bottle"),
        ],
        customer_name="Anurag",
        customer_phone="9876543210",
    )
    print(example.model_dump_json(indent=2))
