"""Generic CRUD router factory so every entity is configured, not hand-coded."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, get_db
from .schemas import optional


def make_crud_router(
    *, prefix: str, tag: str, model: type[Base], create, read, update=None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])
    update = update or optional(create, f"{create.__name__}Patch")
    cols = {c.key for c in model.__table__.columns}

    def get_or_404(db: Session, id_: UUID):
        obj = db.get(model, id_)
        if obj is None:
            raise HTTPException(404, f"{tag} not found")
        return obj

    @router.get("", response_model=list[read])
    def list_items(request: Request, db: Session = Depends(get_db), limit: int = 1000, offset: int = 0):
        """Filter by any column with ?column=value (e.g. /assignments?employee_id=...)."""
        stmt = select(model)
        for key, value in request.query_params.items():
            if key in ("limit", "offset"):
                continue
            if key not in cols:
                raise HTTPException(422, f"unknown filter '{key}'")
            stmt = stmt.where(getattr(model, key) == value)
        return db.scalars(stmt.limit(limit).offset(offset)).all()

    @router.post("", response_model=read, status_code=201)
    def create_item(body: create, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        obj = model(**body.model_dump())
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @router.get("/{item_id}", response_model=read)
    def get_item(item_id: UUID, db: Session = Depends(get_db)):
        return get_or_404(db, item_id)

    @router.patch("/{item_id}", response_model=read)
    def patch_item(item_id: UUID, body: update, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        obj = get_or_404(db, item_id)
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        db.commit()
        db.refresh(obj)
        return obj

    @router.delete("/{item_id}", status_code=204)
    def delete_item(item_id: UUID, db: Session = Depends(get_db)):
        db.delete(get_or_404(db, item_id))
        db.commit()
        return Response(status_code=204)

    return router
