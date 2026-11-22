"""Roster versions and entries. Generation/validation arrive in Stages 3-4."""
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db import get_db
from .models import Conflict, Roster, RosterEntry
from .schemas import (ConflictRead, EntryRead, EntryUpsert, RosterCreate, RosterRead,
                      RosterUpdate)

router = APIRouter(prefix="/rosters", tags=["rosters"])


def _roster_or_404(db: Session, roster_id: UUID) -> Roster:
    roster = db.get(Roster, roster_id)
    if roster is None:
        raise HTTPException(404, "roster not found")
    return roster


@router.get("", response_model=list[RosterRead])
def list_rosters(month_start: date | None = None, db: Session = Depends(get_db)):
    stmt = select(Roster).order_by(Roster.month_start.desc(), Roster.created_at.desc())
    if month_start:
        stmt = stmt.where(Roster.month_start == month_start)
    return db.scalars(stmt).all()


@router.post("", response_model=RosterRead, status_code=201)
def create_roster(body: RosterCreate, db: Session = Depends(get_db)):
    roster = Roster(**body.model_dump())
    db.add(roster)
    db.commit()
    db.refresh(roster)
    return roster


@router.get("/{roster_id}", response_model=RosterRead)
def get_roster(roster_id: UUID, db: Session = Depends(get_db)):
    return _roster_or_404(db, roster_id)


@router.patch("/{roster_id}", response_model=RosterRead)
def update_roster(roster_id: UUID, body: RosterUpdate, db: Session = Depends(get_db)):
    roster = _roster_or_404(db, roster_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("status") == "published":
        # Stage 4 adds the validator gate here: roster with error-level conflicts cannot publish.
        roster.published_at = datetime.now(timezone.utc)
    for k, v in data.items():
        setattr(roster, k, v)
    db.commit()
    db.refresh(roster)
    return roster


@router.delete("/{roster_id}", status_code=204)
def delete_roster(roster_id: UUID, db: Session = Depends(get_db)):
    db.delete(_roster_or_404(db, roster_id))
    db.commit()
    return Response(status_code=204)


@router.get("/{roster_id}/entries", response_model=list[EntryRead])
def list_entries(
    roster_id: UUID,
    employee_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
    _roster_or_404(db, roster_id)
    stmt = select(RosterEntry).where(RosterEntry.roster_id == roster_id)
    if employee_id:
        stmt = stmt.where(RosterEntry.employee_id == employee_id)
    if date_from:
        stmt = stmt.where(RosterEntry.on_date >= date_from)
    if date_to:
        stmt = stmt.where(RosterEntry.on_date <= date_to)
    return db.scalars(stmt.order_by(RosterEntry.on_date, RosterEntry.employee_id)).all()


@router.put("/{roster_id}/entries", response_model=list[EntryRead])
def upsert_entries(roster_id: UUID, body: list[EntryUpsert], db: Session = Depends(get_db)):
    """Manual edit: upsert one or more cells. Marked is_manual so regeneration respects them."""
    _roster_or_404(db, roster_id)
    if not body:
        return []
    rows = [{**e.model_dump(), "roster_id": roster_id, "is_manual": True} for e in body]
    stmt = insert(RosterEntry).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["roster_id", "employee_id", "on_date"],
        set_={c: stmt.excluded[c] for c in ("status", "shift_id", "is_manual", "is_locked")},
    ).returning(RosterEntry)
    result = db.execute(stmt).scalars().all()
    db.commit()
    return result


conflicts_router = APIRouter(prefix="/conflicts", tags=["conflicts"])


@conflicts_router.get("", response_model=list[ConflictRead])
def list_conflicts(roster_id: UUID | None = None, resolved: bool | None = None,
                   db: Session = Depends(get_db)):
    stmt = select(Conflict).order_by(Conflict.on_date, Conflict.created_at)
    if roster_id:
        stmt = stmt.where(Conflict.roster_id == roster_id)
    if resolved is not None:
        stmt = stmt.where(Conflict.resolved == resolved)
    return db.scalars(stmt).all()


@conflicts_router.patch("/{conflict_id}", response_model=ConflictRead)
def set_resolved(conflict_id: UUID, resolved: bool, db: Session = Depends(get_db)):
    c = db.get(Conflict, conflict_id)
    if c is None:
        raise HTTPException(404, "conflict not found")
    c.resolved = resolved
    db.commit()
    db.refresh(c)
    return c
