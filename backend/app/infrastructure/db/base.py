from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models.

    Deliberately lives in infrastructure/, not domain/ — domain entities
    (app/domain/entities/) are plain dataclasses with zero SQLAlchemy
    dependency; these ORM models exist only to map domain entities to
    Postgres rows and back, inside repository implementations.
    """
