"""SQLAlchemy ORM models package.

Importing this package imports every model module, so all tables register
with Base.metadata. Alembic relies on this in env.py to discover tables.
"""
from app.models.batch import Batch  # noqa: F401
from app.models.medicine import Medicine  # noqa: F401

__all__ = ["Medicine", "Batch"]
