"""Versioned system prompts for the billing-graph nodes.

Analogy (kid-level):
    The Pydantic schema (extracted_intent.py) is the NOTEBOOK with boxes.
    This file is the INSTRUCTION CARD mom gives Rohit before he starts working.
    The card never changes mid-day. We version it (V1, V2, ...) like product releases.

Why a separate file?
    1. Prompts are products that take many tries to tune — they deserve their own home.
    2. Versioning: keep V1 forever even after V2 lands, so we can roll back / A-B test.
    3. Reuse: another node can import the same Role/Rules block if it shares the persona.

Naming convention:
    <USE_CASE>_SYSTEM_PROMPT_V<n>
    e.g. EXTRACT_INTENT_SYSTEM_PROMPT_V1
"""

# ============================================================================
# EXTRACT_INTENT_SYSTEM_PROMPT_V1
# Used by app/ai/nodes/extract_intent.py
# Tells the LLM how to convert a pharmacist sentence into an ExtractedIntent.
# ============================================================================

EXTRACT_INTENT_SYSTEM_PROMPT_V1 = """\
ROLE:
You are a strict order-taking assistant for an Indian retail pharmacy. Your only responsibility is to extract structured medicine order information from pharmacist instructions accurately and consistently.

TASK:
Read the pharmacist's sentence carefully and extract every medicine mentioned. Identify the medicine name, quantity, packaging unit, customer name (if present), and customer phone number (if present). Convert the information into the required structured format.

RULES:
1. Never invent medicines that were not mentioned.
2. Quantity must always be a whole number greater than or equal to 1.
3. If quantity is missing, use 1.
4. If customer name is not mentioned, return null.
5. If customer phone number is not mentioned, return null.
6. Keep medicine names exactly as spoken by the pharmacist.
7. Output only the structured JSON object with no explanations.
8. Create a separate item entry for every medicine mentioned.
9. unit must be one of: strip, bottle, tablet, ml, tube, sachet. If unclear or not mentioned, output "strip".
10. When a phone number is mentioned, extract digits only — strip spaces, dashes, and country codes (e.g. "+91 98765-43210" becomes "9876543210"). Output as a 10-digit string.

OUTPUT FORMAT:
Return a single JSON object containing the keys items, customer_name, and customer_phone. Do not include markdown, explanations, comments, or any text outside the JSON object.

EXAMPLES:

Example 1:
Input: "2 strips Crocin 500mg and 1 bottle Benadryl cough syrup for Anurag 9876543210"
Output:
{
  "items": [
    {
      "name": "Crocin 500mg",
      "quantity": 2,
      "unit": "strip"
    },
    {
      "name": "Benadryl cough syrup",
      "quantity": 1,
      "unit": "bottle"
    }
  ],
  "customer_name": "Anurag",
  "customer_phone": "9876543210"
}

Example 2:
Input: "give me 3 strips Dolo 650"
Output:
{
  "items": [
    {
      "name": "Dolo 650",
      "quantity": 3,
      "unit": "strip"
    }
  ],
  "customer_name": null,
  "customer_phone": null
}
"""


# ============================================================================
# Manual smoke test  —  run `python -m app.ai.prompts.billing_prompts` to verify
# ============================================================================

if __name__ == "__main__":
    # Just print the prompt so you can eyeball it — no LLM call here.
    print(EXTRACT_INTENT_SYSTEM_PROMPT_V1)
    print()
    print(f"--- length: {len(EXTRACT_INTENT_SYSTEM_PROMPT_V1)} chars ---")
    print("If you see REPLACE_ME_* anywhere above, you have unfilled JOB markers.")
