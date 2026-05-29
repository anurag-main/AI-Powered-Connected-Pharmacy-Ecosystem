"""HTTP layer for the Medicine domain.

The router translates between HTTP and the service layer:
- FastAPI auto-parses incoming JSON into MedicineCreate (Pydantic validates).
- response_model=MedicineOut ensures only output-allowed fields ship to the client.
- Domain exceptions (DuplicateMedicineError) are caught and translated to HTTPException.

The router NEVER:
- Decides business rules (call the service for that).
- Talks to storage (call the service → repository).
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.exceptions import DuplicateMedicineError
from app.repositories.medicine_repository import InMemoryMedicineRepository
from app.schemas.medicine import MedicineCreate, MedicineOut
from app.services.medicine_service import MedicineService

# Phase 1 ONLY: module-level singleton repo so every request shares the same dict.
# Phase 2 replaces this with a per-request DB session — same Depends() pattern, different provider.
_repository = InMemoryMedicineRepository()


def get_repository() -> InMemoryMedicineRepository:
    """Dependency provider returning the shared in-memory repo (Phase 1)."""
    return _repository


def get_service(
    repo: InMemoryMedicineRepository = Depends(get_repository),
) -> MedicineService:
    """Dependency provider building a MedicineService with the right repo."""
    return MedicineService(repository=repo)


router = APIRouter(prefix="/api/v1/medicines", tags=["medicines"])


@router.post(
    "",
    response_model=MedicineOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new medicine",
)
def create_medicine(
    payload: MedicineCreate,
    service: MedicineService = Depends(get_service),
) -> MedicineOut:
    """Create a new medicine. Returns 409 if same normalized name already exists."""
    try:
        return service.create_medicine(payload)
    except DuplicateMedicineError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get(
    "",
    response_model=list[MedicineOut],
    summary="List all medicines",
)
def list_medicines(
    service: MedicineService = Depends(get_service),
) -> list[MedicineOut]:
    """Return every stored medicine."""
    return service.list_medicines()


@router.get(
    "/{medicine_id}",
    response_model=MedicineOut,
    summary="Get a medicine by id",
)
def get_medicine(
    medicine_id: int,
    service: MedicineService = Depends(get_service),
) -> MedicineOut:
    """Return the medicine with this id, or 404 if not found."""
    result = service.get_medicine(medicine_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Medicine {medicine_id} not found",
        )
    return result
