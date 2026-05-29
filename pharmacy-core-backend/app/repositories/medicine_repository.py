"""In-memory repository for the Medicine domain.

Phase 1 implementation: stores records in a process-local Python dict.
Phase 2 will replace this with a SQLAlchemy + MySQL-backed repository.
The Service layer should not change between the two — that's the point.

Contract enforced by this class:
- The repo NEVER decides whether something should be added (no duplicate check here).
- The repo NEVER calculates prices, GST, discounts.
- The repo NEVER reads HTTP request schemas (it takes plain primitives).
- The caller of find_by_normalized_name() MUST pass an already-normalized string;
  the repo compares using lowercase + strip and trusts the caller's normalization rule.
"""
from datetime import datetime

from app.schemas.medicine import MedicineOut


class InMemoryMedicineRepository:
    """Stores Medicine records in process memory.

    Limitations of this Phase 1 implementation (acceptable for now):
    - NOT thread-safe. Multiple uvicorn workers (--workers > 1) will each have their own copy.
    - State is lost on process restart.
    - O(n) scan for find_by_normalized_name (no index).
    Phase 2 (MySQL) and Phase 6 (Redis cache) eliminate all of these.
    """

    def __init__(self) -> None:
        # Internal storage. Do NOT expose this dict directly — only return copies or new lists.
        self._store: dict[int, MedicineOut] = {}
        # Auto-increment counter that mirrors what a real DB primary key sequence does.
        self._next_id: int = 1

    # The `*,` after `self` makes every following argument KEYWORD-ONLY.
    # Callers must say `repo.add(name=..., mrp=...)`, never `repo.add("Crocin", 25.5)`.
    # Reason: prevents swapping argument order by accident in future refactors.
    def add(
        self,
        *,
        name: str,
        mrp: float,
        hsn_code: str,
        manufacturer: str | None,
    ) -> MedicineOut:
        """Insert a new medicine. Generates id and created_at server-side."""
        # Capture the current counter BEFORE incrementing — this is the id we'll hand out.
        new_id = self._next_id

        medicine = MedicineOut(
            id=new_id,
            name=name,
            mrp=mrp,
            hsn_code=hsn_code,
            manufacturer=manufacturer,
            created_at=datetime.now(),
        )

        self._store[new_id] = medicine
        self._next_id += 1  # next add() gets the next number
        return medicine

    def get_by_id(self, medicine_id: int) -> MedicineOut | None:
        """Return the medicine with this id, or None if no such id exists."""
        # dict.get returns None when the key is missing — no KeyError raised.
        return self._store.get(medicine_id)

    def list_all(self) -> list[MedicineOut]:
        """Return every stored medicine in insertion order.

        We wrap in list(...) to return a NEW list. If we returned self._store.values()
        directly, a caller mutating it would corrupt our internal storage.
        """
        return list(self._store.values())

    def find_by_normalized_name(self, normalized_name: str) -> MedicineOut | None:
        """Find the first medicine whose name (lowercased + stripped) matches.

        Caller (the service) MUST pre-normalize the query string. The repo only
        normalizes the STORED names for comparison — it does NOT re-normalize the input.
        """
        for medicine in self._store.values():
            if medicine.name.lower().strip() == normalized_name:
                return medicine
        return None
