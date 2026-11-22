import os

import pytest

# Tests need a Postgres with supabase/schema.sql applied. NEVER point this at your real project:
# the fixture truncates every table.
TEST_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_URL:
    pytest.exit("Set TEST_DATABASE_URL to a throwaway Postgres (schema.sql applied)", returncode=2)
os.environ["DATABASE_URL"] = TEST_URL

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import get_engine  # noqa: E402
from app.main import app  # noqa: E402

TABLES = ("audit_log, conflicts, roster_entries, rosters, shifts, leaves, holidays, assignments, "
          "coverage_rules, brand_processes, processes, brands, employees, pods")


@pytest.fixture()
def client():
    with get_engine().begin() as conn:
        conn.execute(text(f"truncate {TABLES} restart identity cascade"))
    with TestClient(app) as c:
        yield c
