"""Business-rule layer for the Billing domain.

Thin wrapper around the compiled billing graph. Its job:
1. Hand the pharmacist's text to the graph
2. Read the final state the graph produces
3. Map that state into the clean BillingResponse HTTP contract

The Service NEVER:
- Knows about HTTP status codes (the router decides 201 vs 422).
- Re-implements any node logic — the graph IS the business engine.

Why a service layer at all if it's "just" calling the graph?
- It's the seam where future cross-cutting rules land: auth checks, rate
  limits, audit logging, idempotency keys — without touching the router or graph.
- It converts the graph's loose dict-state into a typed, validated response.
- It keeps the router dumb (HTTP translation only) and the graph pure (logic only).
"""
from app.ai.graphs.billing_graph import (
    get_billing_graph,
    get_confirm_graph,
    get_quote_graph,
)
from app.ai.state.billing_state import BillingState
from app.schemas.billing import BillingLineItem, BillingResponse, ConfirmLineItem


def _state_to_response(final_state: dict) -> BillingResponse:
    """Map any billing-graph final state → the public BillingResponse.

    Shared by create_sale / quote_sale / confirm_sale. `sale_id` is None for a
    quote (persist never ran) and set after a sale/confirm.
    """
    extracted = final_state.get("extracted_intent") or {}
    priced_items = final_state.get("priced_items") or []

    items = [
        BillingLineItem(
            name=item["name"],
            quantity=item["quantity"],
            unit=item["unit"],
            medicine_id=item["medicine_id"],
            batch_id=item["batch_id"],
            batch_number=item["batch_number"],
            expiry_date=item["expiry_date"],
            unit_price=item["unit_price"],
            line_total=item["line_total"],
        )
        for item in priced_items
    ]

    return BillingResponse(
        sale_id=final_state.get("sale_id"),
        total_amount=final_state.get("total_amount", 0.0),
        customer_name=extracted.get("customer_name"),
        customer_phone=extracted.get("customer_phone"),
        items=items,
        errors=final_state.get("errors", []),
    )


class BillingService:
    """Orchestrates the billing graphs and shapes their output into responses."""

    def create_sale(self, pharmacist_input: str) -> BillingResponse:
        """Full pipeline for one free-text order — extracts AND persists in one call.

        sale_id is None if nothing could be billed (router → 422).
        """
        final_state = get_billing_graph().invoke(
            {"pharmacist_input": pharmacist_input}
        )
        return _state_to_response(final_state)

    def quote_sale(self, pharmacist_input: str) -> BillingResponse:
        """PREVIEW — price the order WITHOUT writing a sale.

        Runs extract → resolve → batch → price (no persist), so sale_id is always
        None. The frontend shows these priced rows for review/edit before printing.
        """
        final_state = get_quote_graph().invoke(
            {"pharmacist_input": pharmacist_input}
        )
        return _state_to_response(final_state)

    def confirm_sale(
        self,
        items: list[ConfirmLineItem],
        customer_name: str | None,
        customer_phone: str | None,
    ) -> BillingResponse:
        """FINALIZE — persist the owner-reviewed items. No LLM.

        We feed the reviewed items in as `batched_items`; the confirm graph
        (compute_pricing → persist_sale) RE-FETCHES each MRP from the DB and
        recomputes the price, so a tampered client price is ignored. sale_id is
        set on success; None (→ 422) if e.g. stock ran out since the quote.
        """
        batched_items = [
            {
                "name": it.name,
                "quantity": it.quantity,
                "unit": it.unit,
                "medicine_id": it.medicine_id,
                "batch_id": it.batch_id,
                "batch_number": it.batch_number,
                "expiry_date": it.expiry_date,
            }
            for it in items
        ]
        initial_state: BillingState = {
            "batched_items": batched_items,
            "extracted_intent": {
                "customer_name": customer_name,
                "customer_phone": customer_phone,
            },
        }
        final_state = get_confirm_graph().invoke(initial_state)
        return _state_to_response(final_state)
