"""Guardrails for the additive PostgreSQL lifecycle evidence migration."""

from pathlib import Path

MIGRATION = Path("db/schema/003_scheduling_lifecycle_evidence.sql")


def test_migration_uses_existing_appointment_tables():
    sql = MIGRATION.read_text()
    assert "CREATE TABLE IF NOT EXISTS vab.scheduling_case_link" in sql
    assert "CREATE TABLE IF NOT EXISTS vab.scheduling_transition" in sql
    assert "CREATE TABLE IF NOT EXISTS vab.scheduling_decision" in sql
    assert "REFERENCES vab.appointment_request(request_id)" in sql
    assert "REFERENCES vab.scheduling_case_link(case_id)" in sql
    assert "CREATE TABLE IF NOT EXISTS vab.appointment " not in sql
    assert "DROP TABLE" not in sql
    assert "ALTER TABLE vab.appointment" not in sql


def test_explicit_consent_and_approval_are_distinct():
    sql = MIGRATION.read_text()
    for name in ("OPTION_SELECTED", "VETERAN_CONFIRMED", "SCHEDULER_APPROVED"):
        assert name in sql
    assert "actor_role = 'VETERAN'" in sql
    assert "actor_role = 'SCHEDULER'" in sql
    assert "idempotency_key text NOT NULL UNIQUE" in sql
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_decision_sequence_is_authoritative_not_transaction_start_time():
    sql = Path(
        "supabase/migrations/20261113014558_vab_011_sprint6_decision_order.sql"
    ).read_text()
    assert "ADD COLUMN decision_order bigint GENERATED ALWAYS AS IDENTITY" in sql
    assert "scheduling_decision_order_unique UNIQUE (decision_order)" in sql
    assert "case_id, decision_kind, decision_order DESC" in sql
    assert "decision_order" not in MIGRATION.read_text()


def test_local_decision_order_upgrade_is_safe_and_separate():
    sql = Path("db/schema/004_scheduling_decision_order.sql").read_text()
    assert "ALTER TABLE vab.scheduling_decision" in sql
    assert "ADD COLUMN decision_order bigint GENERATED ALWAYS AS IDENTITY" in sql
    assert "scheduling_decision_order_unique UNIQUE (decision_order)" in sql
    assert "Existing decisions require a reviewed ordered backfill" in sql
    assert "case_id, decision_kind, decision_order DESC" in sql
    assert "table_schema='vab'" in sql
    assert "BEGIN;" in sql and "COMMIT;" in sql
    assert "decision_order" not in MIGRATION.read_text()
