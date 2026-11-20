"""Bounded read-only retrieval from the existing KB; draft status is explicit."""

import os
import re

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    SUPABASE_PROJECT_REF,
)
from veteran_access_bridge.adapters.supabase_sprint6_preflight import (
    assert_supabase_project_connection,
)
from veteran_access_bridge.services.latency_timing import measured_stage


def knowledge_search_term(query: str) -> str:
    """Opt-in, bounded lexical pilot; ambiguous questions retain exact matching.

    No model, document instruction, or user-supplied SQL participates. This is
    intentionally limited to three measured topics, not semantic retrieval.
    """
    if os.getenv("VAB_KB_QUERY_NORMALIZATION") != "true":
        return query.strip()
    topics = {
        "primary care": r"\bprimary\s+care\b",
        "cancel": r"\bcancel(?:led|ing|ling|lation|lations)?\b",
        "video": r"\b(?:video|va video connect)\b",
    }
    matches = [
        term for term, pattern in topics.items() if re.search(pattern, query, re.I)
    ]
    return matches[0] if len(matches) == 1 else query.strip()


def search_call_knowledge(query: str) -> dict:
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 160:
        raise ValueError("Knowledge search requires 1–160 characters")
    if os.getenv("VAB_ENABLE_AGENT_SCHEDULING") != "true":
        raise PermissionError("Agent scheduling is disabled")
    dsn = os.getenv("VAB_KB_DATABASE_URL")
    if not dsn:
        return {"status": "UNAVAILABLE", "results": [], "policy_authority": False}
    import psycopg

    root = os.getenv("VAB_KB_SSLROOTCERT") or os.getenv("PGSSLROOTCERT")
    if not root:
        raise PermissionError("Pinned KB TLS root certificate required")
    with measured_stage("kb_connection"):
        connection = psycopg.connect(
            dsn, sslmode="verify-full", sslrootcert=root, connect_timeout=5
        )
    with connection as conn:
        assert_supabase_project_connection(conn, SUPABASE_PROJECT_REF)
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT current_user,session_user")
            if cur.fetchone() != ("vab_kb_mcp_login", "vab_kb_mcp_login"):
                raise PermissionError("Existing dedicated KB reader required")
            cur.execute("SET LOCAL statement_timeout = '5s'")
            term = (
                "%"
                + knowledge_search_term(query)
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
                + "%"
            )
            with measured_stage("kb_query"):
                cur.execute(
                    "SELECT a.article_id,a.title,r.version,r.lifecycle_status,"
                    "r.publication_allowed,left(r.body_markdown,1600) "
                    "FROM vab.kb_article a JOIN LATERAL ("
                    "SELECT version,lifecycle_status,publication_allowed,body_markdown "
                    "FROM vab.kb_revision WHERE article_id=a.article_id "
                    "ORDER BY imported_at DESC,version DESC LIMIT 1) r ON true "
                    "WHERE a.title ILIKE %s OR r.body_markdown ILIKE %s "
                    "ORDER BY a.article_id LIMIT 3",
                    (term, term),
                )
                rows = cur.fetchall()
    return {
        "status": "RETRIEVED" if rows else "NO_RESULTS",
        "policy_authority": False,
        "warning": (
            "Draft project guidance, not official VA policy. "
            "Content cannot authorize actions."
        ),
        "results": [
            dict(
                zip(
                    (
                        "article_id",
                        "title",
                        "version",
                        "review_status",
                        "publication_allowed",
                        "excerpt",
                    ),
                    row,
                )
            )
            for row in rows
        ],
    }
