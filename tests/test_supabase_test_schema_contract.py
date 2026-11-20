"""Reviewable, zero-network invariants for the isolated Supabase test schema."""

from pathlib import Path

MIGRATION = Path(
    "supabase/migrations/"
    "20261113022113_vab_015_sprint6_isolated_test_schema.sql"
)


def test_test_schema_ddl_has_no_cross_schema_foreign_keys():
    sql = MIGRATION.read_text()
    active_lines = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    assert "CREATE SCHEMA vab_test;" in active_lines
    assert "CREATE TABLE IF NOT EXISTS vab_test.appointment " in active_lines
    assert "CREATE TABLE IF NOT EXISTS vab_test.scheduling_decision " in active_lines
    assert "REFERENCES vab_test.appointment_request(request_id)" in active_lines
    assert "REFERENCES vab_test.scheduling_case_link(case_id)" in active_lines
    assert "REFERENCES vab." not in active_lines
    assert "ALTER TABLE vab." not in active_lines
    assert "CREATE TABLE IF NOT EXISTS vab." not in active_lines
    assert "table_schema='vab'" not in active_lines


def test_test_schema_is_private_and_fails_closed_on_replay():
    sql = MIGRATION.read_text()
    assert "vab_test already exists, fail closed" in sql
    assert (
        "REVOKE ALL ON SCHEMA vab_test "
        "FROM PUBLIC, anon, authenticated, service_role;"
    ) in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "ADD COLUMN decision_order bigint GENERATED ALWAYS AS IDENTITY" in sql
    assert "scheduling_decision_order_unique UNIQUE (decision_order)" in sql
    assert "ADD COLUMN scheduling_lock_guard boolean" in sql
    assert "GRANT INSERT" not in sql
