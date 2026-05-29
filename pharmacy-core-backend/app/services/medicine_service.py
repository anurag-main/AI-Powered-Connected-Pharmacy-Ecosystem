"""Business-rule layer for the Medicine domain.

Responsibilities:
- Decide what data transformations are applied (e.g., name normalization).
- Enforce business rules (duplicate prevention, FEFO in Phase 2, pricing later).
- Orchestrate calls to one or more repositories.
- Raise domain exceptions (PharmacyError subclasses) when rules are violated.

The Service NEVER:
- Knows about HTTP, JSON, or status codes (those belong in the router).
- Knows about SQL or storage details (those belong in the repository).
"""
from app.exceptions import DuplicateMedicineError
from app.repositories.medicine_repository import InMemoryMedicineRepository
from app.schemas.medicine import MedicineCreate, MedicineOut


def normalize_medicine_name(name: str) -> str:
    """The canonical form used for duplicate detection.

    Currently: lowercase + strip surrounding whitespace.
    Single source of truth — every caller that needs to compare medicine names
    for equality should pass through this function first.
    """
    return name.lower().strip()


class MedicineService:
    """Business rules for Medicine — duplicate detection today, pricing/FEFO later."""

    def __init__(self, repository: InMemoryMedicineRepository) -> None:
        # Constructor takes the repo as a DEPENDENCY (dependency injection).
        # Phase 1.7 uses FastAPI's Depends() to inject the right repo here.
        # In tests, you'll inject a fake repo with the same interface — without touching this file.
        self._repo = repository

    def create_medicine(self, payload: MedicineCreate) -> MedicineOut:
        """Apply business rules, then add the medicine via the repository.

        Raises:
            DuplicateMedicineError: if a medicine with the same normalized
                name already exists. The router catches this → HTTP 409.
        """
        normalized = normalize_medicine_name(payload.name)
        existing = self._repo.find_by_normalized_name(normalized)
        if existing is not None:
            # Pass the ORIGINAL name (user's casing) so the error message
            # echoes back what they typed, not the internal normalized form.
            raise DuplicateMedicineError(payload.name)
        return self._repo.add(
            name=payload.name,
            mrp=payload.mrp,
            hsn_code=payload.hsn_code,
            manufacturer=payload.manufacturer,
        )

    def get_medicine(self, medicine_id: int) -> MedicineOut | None:
        """Fetch a medicine by id, or None if not found.

        Phase 1 has no business rule for "get" — service is a pass-through here.
        That's OK. Not every service method needs custom logic — the layer exists
        so we have a place to ADD rules later (auth filter, soft-delete check, cache)
        without refactoring routers.
        """
        return self._repo.get_by_id(medicine_id)

    def list_medicines(self) -> list[MedicineOut]:
        """List every medicine. Another Phase 1 pass-through to the repo."""
        return self._repo.list_all()
