"""SQLAlchemy ORM model for the reorder_requests table.

One row per reorder suggestion the owner APPROVED. This is how the agent
REMEMBERS its decisions — without it, "Approve" only changes a colour on screen
and is forgotten on the next refresh.

status lifecycle:
    'pending'   — approved, not yet turned into a real purchase order
    'ordered'   — a PO has been placed (future step)
    'cancelled' — owner changed their mind
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.medicine import Medicine


class ReorderRequest(Base):
    """An approved reorder, awaiting a purchase order."""

    __tablename__ = "reorder_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # FK -> medicines.id. RESTRICT: can't delete a medicine that has reorder
    # history (same audit reasoning as sale_items.medicine_id).
    medicine_id: Mapped[int] = mapped_column(
        ForeignKey("medicines.id", ondelete="RESTRICT"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(nullable=False)

    # 'rule' (deterministic math) or 'llm' (judgment node) — where the suggestion
    # came from. Kept so the owner can later see what the AI vs the math proposed.
    source: Mapped[str] = mapped_column(String(10), nullable=False)

    # The LLM's plain-English reason (null for rule-based approvals).
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 'pending' | 'ordered' | 'cancelled'. New approvals start 'pending'.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Powers the idempotency check: "is there already a pending request for this
    # medicine?" — a single indexed lookup instead of a full scan.
    __table_args__ = (
        Index("ix_reorder_requests_medicine_status", "medicine_id", "status"),
    )

    # One-directional link (no back_populates needed on Medicine for this).
    medicine: Mapped["Medicine"] = relationship("Medicine")

    def __repr__(self) -> str:
        return (
            f"<ReorderRequest id={self.id} medicine_id={self.medicine_id} "
            f"qty={self.quantity} status={self.status!r}>"
        )
