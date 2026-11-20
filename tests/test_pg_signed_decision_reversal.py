"""Latest signed Veteran rejection must prevent subsequent scheduler approval.

The cursor models only the private PostgreSQL decision contract, not live SQL.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from veteran_access_bridge.services.pg_signed_decisions import (
    AUDIENCE,
    ISSUER,
    persist_signed_scheduling_decision,
)

SECRET = "local-synthetic-test-verifier-secret-at-least-32-characters"
CASE = "DEMO-PC-5000999-001"


def scheduler_jwt():
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "trusted-scheduler",
            "role": "SCHEDULER",
            "case_id": CASE,
            "synthetic": True,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": ISSUER,
            "aud": AUDIENCE,
        },
        SECRET,
        algorithm="HS256",
    )


class DecisionCursor:
    def __init__(self, latest_veteran):
        self.latest_veteran = latest_veteran
        self.queries = []
        self.answer = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.queries.append(sql)
        if "SELECT current_database()" in sql:
            self.answer = ("veteran_access_bridge_dev",)
        elif "SELECT l.request_id FROM vab.scheduling_case_link" in sql:
            self.answer = (uuid4(),)
        elif "SELECT EXISTS (" in sql:
            self.answer = (True,)
        elif "SELECT d.decision_status FROM vab.scheduling_decision" in sql:
            self.answer = self.latest_veteran
        else:
            self.answer = None

    def fetchone(self):
        return self.answer


class DecisionConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1


@pytest.mark.parametrize("latest", [("REJECTED",), None])
def test_scheduler_cannot_approve_after_latest_veteran_rejection(latest):
    cur = DecisionCursor(latest)
    conn = DecisionConnection(cur)
    with pytest.raises(ValueError, match="Current Veteran confirmation required"):
        persist_signed_scheduling_decision(
            lambda: conn,
            assertion=scheduler_jwt(),
            verifier_secret=SECRET,
            case_id=CASE,
            option_id="OPT-PC-001",
            idempotency_key=uuid4().hex,
            correlation_id="demo-correlation",
            service_evidence_reference="verified-service-record",
        )
    assert conn.commits == 0
    assert not any("INSERT INTO" in query for query in cur.queries)
