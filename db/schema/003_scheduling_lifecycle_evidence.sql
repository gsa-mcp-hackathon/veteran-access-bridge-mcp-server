-- VAB scheduling persistence extension; DEV-only additive migration.
-- Requires 001_initial.sql and existing synthetic schema; no booking side effects.
-- This is 003 because 002_kb.sql is already allocated.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS vab.scheduling_case_link (
    case_id text PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE REFERENCES vab.appointment_request(request_id),
    source_request_id text NOT NULL UNIQUE,
    source_system text NOT NULL DEFAULT 'SYNTHETIC_MCP',
    synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(case_id) <> ''),
    CHECK (btrim(source_request_id) <> '')
);

CREATE TABLE IF NOT EXISTS vab.scheduling_transition (
    transition_id uuid PRIMARY KEY,
    case_id text NOT NULL REFERENCES vab.scheduling_case_link(case_id),
    event_type text NOT NULL,
    from_state text,
    to_state text NOT NULL,
    actor_role text NOT NULL CHECK (
        actor_role IN ('VETERAN','SCHEDULER','SYSTEM')
    ),
    actor_id text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    correlation_id text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(event_type) <> ''),
    CHECK (btrim(to_state) <> ''),
    CHECK (btrim(actor_id) <> ''),
    CHECK (btrim(idempotency_key) <> ''),
    CHECK (btrim(correlation_id) <> '')
);

CREATE INDEX IF NOT EXISTS idx_scheduling_transition_case_time
    ON vab.scheduling_transition(case_id, occurred_at, transition_id);
CREATE INDEX IF NOT EXISTS idx_scheduling_transition_correlation
    ON vab.scheduling_transition(correlation_id, occurred_at);

CREATE TABLE IF NOT EXISTS vab.scheduling_decision (
    decision_id uuid PRIMARY KEY,
    case_id text NOT NULL REFERENCES vab.scheduling_case_link(case_id),
    option_id text NOT NULL,
    decision_kind text NOT NULL CHECK (
        decision_kind IN ('OPTION_SELECTED','VETERAN_CONFIRMED','SCHEDULER_APPROVED')
    ),
    decision_status text NOT NULL CHECK (
        decision_status IN ('ACCEPTED','REJECTED')
    ),
    actor_role text NOT NULL CHECK (
        actor_role IN ('VETERAN','SCHEDULER','SYSTEM')
    ),
    actor_id text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    correlation_id text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    decided_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(option_id) <> ''),
    CHECK (btrim(actor_id) <> ''),
    CHECK (btrim(idempotency_key) <> ''),
    CHECK (btrim(correlation_id) <> ''),
    CHECK (
        (decision_kind = 'VETERAN_CONFIRMED' AND actor_role = 'VETERAN')
        OR (decision_kind = 'SCHEDULER_APPROVED' AND actor_role = 'SCHEDULER')
        OR (decision_kind = 'OPTION_SELECTED'
            AND actor_role IN ('VETERAN','SCHEDULER'))
    )
);

CREATE INDEX IF NOT EXISTS idx_scheduling_decision_case_kind
    ON vab.scheduling_decision(case_id, decision_kind, decided_at);

-- Keep original appointment slot uniqueness until a separate reviewed
-- cancellation/rebooking policy is approved. No direct booking SQL is added.
COMMIT;
