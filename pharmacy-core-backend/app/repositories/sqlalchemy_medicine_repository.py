"""SQL-backed repository for the Medicine domain.

Same 4-method interface as InMemoryMedicineRepository (Phase 1) but persists
to MySQL through a SQLAlchemy Session. The service layer treats both as
interchangeable — that's the whole point of the repository pattern.

Phase 2 simplification: this repo commits inside each write method.
When we add multi-table writes in Phase 3 (sale = sale + sale_items + batch update),
we'll refactor so the service owns the commit boundary (Unit of Work pattern).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.medicine import Medicine
from app.schemas.medicine import MedicineOut
from app.services.medicine_service import normalize_medicine_name


class SQLAlchemyMedicineRepository:
    """MySQL-backed repository — identical interface to InMemoryMedicineRepository."""

    def __init__(self, db: Session) -> None:
        # Session is injected via Depends(get_db) in the router layer.
        # Lifetime = one HTTP request. The session closes itself after the request.
        self._db = db

    def add(
        self,
        *,
        name: str,
        mrp: float,
        hsn_code: str,
        manufacturer: str | None,
    ) -> MedicineOut:
        """Insert one row. MySQL generates id, created_at, updated_at."""
        medicine = Medicine(
            name=name,
            normalized_name=normalize_medicine_name(name),
            mrp=mrp,
            hsn_code=hsn_code,
            manufacturer=manufacturer,
        )
        self._db.add(medicine)
        self._db.commit()
        # After commit, MySQL has filled id + timestamps. refresh() reloads the
        # row so our Python `medicine` object reflects them before we serialize.
        self._db.refresh(medicine)
        return MedicineOut.model_validate(medicine)

    def get_by_id(self, medicine_id: int) -> MedicineOut | None:
        """O(1) primary-key lookup. None if no row with that id."""
        # session.get(Model, pk) is the SQLAlchemy 2.0 idiom for "find by PK"
        # — avoids writing a full SELECT statement.
        orm = self._db.get(Medicine, medicine_id)
        return MedicineOut.model_validate(orm) if orm is not None else None

    def list_all(self) -> list[MedicineOut]:
        """Every row, ordered by id (insertion order)."""
        stmt = select(Medicine).order_by(Medicine.id)
        rows = self._db.scalars(stmt).all()
        return [MedicineOut.model_validate(row) for row in rows]

    def find_by_normalized_name(self, normalized_name: str) -> MedicineOut | None:
        """O(log n) lookup via the UNIQUE INDEX on normalized_name.

        The caller must pre-normalize the query string — same contract as the
        in-memory repo. This method NEVER re-normalizes the input.
        """
        stmt = select(Medicine).where(Medicine.normalized_name == normalized_name)
        orm = self._db.scalars(stmt).first()
        return MedicineOut.model_validate(orm) if orm is not None else None
