from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models as m
from . import schemas as s
from .config import get_settings
from .crud import make_crud_router
from .db import get_db
from .rosters import conflicts_router
from .rosters import router as rosters_router
from .scheduling.api import router as generate_router
from .scheduling.ops import router as ops_router

app = FastAPI(title="Smart Roster Management API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_list,  # comma-separated CORS_ORIGINS env var
    allow_methods=["*"],
    allow_headers=["*"],
)

# sqlstate -> (http status, label)
_PG_ERRORS = {
    "23505": (409, "duplicate value violates a unique rule"),
    "23503": (409, "referenced record missing, or still referenced by other records"),
    "23514": (422, "value violates a rule"),
    "23502": (422, "required value missing"),
}


@app.exception_handler(IntegrityError)
async def integrity_handler(_: Request, exc: IntegrityError):
    code = getattr(exc.orig, "sqlstate", None)
    status, label = _PG_ERRORS.get(code, (409, "database constraint failed"))
    detail = str(getattr(getattr(exc.orig, "diag", None), "message_detail", "") or "")
    return JSONResponse(status_code=status, content={"detail": label, "info": detail})


@app.get("/health", tags=["meta"])
def health(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    return {"status": "ok"}


CRUD = [
    dict(prefix="/pods", tag="pods", model=m.Pod, create=s.PodCreate, read=s.PodRead),
    dict(prefix="/employees", tag="employees", model=m.Employee, create=s.EmployeeCreate, read=s.EmployeeRead),
    dict(prefix="/brands", tag="brands", model=m.Brand, create=s.BrandCreate, read=s.BrandRead),
    dict(prefix="/processes", tag="processes", model=m.Process, create=s.ProcessCreate, read=s.ProcessRead),
    dict(prefix="/brand-processes", tag="brand-processes", model=m.BrandProcess,
         create=s.BrandProcessCreate, read=s.BrandProcessRead),
    dict(prefix="/coverage-rules", tag="coverage-rules", model=m.CoverageRule,
         create=s.CoverageRuleCreate, read=s.CoverageRuleRead),
    dict(prefix="/assignments", tag="assignments", model=m.Assignment,
         create=s.AssignmentCreate, read=s.AssignmentRead),
    dict(prefix="/holidays", tag="holidays", model=m.Holiday, create=s.HolidayCreate, read=s.HolidayRead),
    dict(prefix="/leaves", tag="leaves", model=m.Leave, create=s.LeaveCreate, read=s.LeaveRead),
    dict(prefix="/shifts", tag="shifts", model=m.Shift, create=s.ShiftCreate, read=s.ShiftRead),
]
for cfg in CRUD:
    app.include_router(make_crud_router(**cfg))

app.include_router(rosters_router)
app.include_router(conflicts_router)
app.include_router(generate_router)
app.include_router(ops_router)


@app.get("/assignment-details", tags=["assignments"])
def assignment_details(db: Session = Depends(get_db)):
    """Denormalised employee / pod / brand / process view for the dashboard."""
    rows = db.execute(text("select * from v_assignment_detail order by brand, process, full_name"))
    return [dict(r._mapping) for r in rows]
