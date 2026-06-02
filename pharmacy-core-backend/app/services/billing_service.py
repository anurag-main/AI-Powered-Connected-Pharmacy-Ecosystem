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
from app.ai.graphs.billing_graph import get_billing_graph
from app.ai.state.billing_state import BillingState
from app.schemas.billing import BillingLineItem, BillingResponse


class BillingService:
    """Orchestrates the billing graph and shapes its output into a response."""

    def create_sale(self, pharmacist_input: str) -> BillingResponse:
        """Run the full billing pipeline for one free-text order.

        Returns a BillingResponse. If sale_id is None, no sale was created and
        `errors` explains why (router turns that into HTTP 422).
        """
        graph = get_billing_graph()

        # The graph manages its own DB sessions inside each node — no session
        # is threaded in here. We hand it only the starting state.
        initial_state: BillingState = {"pharmacist_input": pharmacist_input}
        final_state = graph.invoke(initial_state)

        # ----- Map the graph's final state → the public response contract -----
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
