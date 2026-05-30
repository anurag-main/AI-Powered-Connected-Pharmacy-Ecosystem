"""Repository contract protocols.

Each Protocol describes what every storage backend MUST support, so the service
layer can depend on the CONTRACT (the interface) rather than any specific
implementation. Swapping InMemoryMedicineRepository for SQLAlchemyMedicineRepository
needs zero changes in the service file — only the router rewires the provider.

Python's `Protocol` uses STRUCTURAL typing: any class with the right method
signatures satisfies the protocol automatically — no `implements` keyword
or inheritance needed.
"""
from typing import Protocol

from app.schemas.medicine import MedicineOut


class MedicineRepository(Protocol):
    """Storage contract for the Medicine domain — exactly 4 methods.

    Both InMemoryMedicineRepository (Phase 1) and SQLAlchemyMedicineRepository
    (Phase 2) satisfy this — neither inherits from it; Python checks
    structurally at type-check time.
    """

    def add(
        self,
        *,
        name: str,
        mrp: float,
        hsn_code: str,
        manufacturer: str | None,
    ) -> MedicineOut: ...

    def get_by_id(self, medicine_id: int) -> MedicineOut | None: ...

    def list_all(self) -> list[MedicineOut]: ...

    def find_by_normalized_name(self, normalized_name: str) -> MedicineOut | None: ...
