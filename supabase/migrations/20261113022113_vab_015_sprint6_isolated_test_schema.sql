-- Recorded applied migration: 20261113022113.
-- Test-only clone of base synthetic scheduling tables, no KB, no cross-schema FK.
-- Source: db/schema/001_initial.sql + db/schema/003_scheduling_lifecycle_evidence.sql
-- + applied decision_order (011) + lock-guard columns (014).
-- NOT for reapplication to a project where vab_test already exists.
SET LOCAL lock_timeout = '5s';
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='vab_test') THEN
    RAISE EXCEPTION 'vab_test already exists, fail closed';
  END IF;
END $$;
-- Veteran Access Bridge: PostgreSQL synthetic-first data foundation.
-- Idempotent DDL; does not migrate or modify existing runtime stores.

CREATE SCHEMA vab_test;
CREATE TABLE IF NOT EXISTS vab_test.data_source (
  source_id text PRIMARY KEY, source_kind text NOT NULL CHECK (source_kind IN ('sandbox','synthea','synthetic_fixture','public')),
  description text, collected_at timestamptz, provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.patient (
  patient_id uuid PRIMARY KEY, demo_patient_key text UNIQUE NOT NULL,
  display_name text, birth_date date, synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
  source_id text REFERENCES vab_test.data_source(source_id), source_patient_id text,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vab_test.patient_identity (
  identity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  patient_id uuid NOT NULL REFERENCES vab_test.patient(patient_id),
  source_id text NOT NULL REFERENCES vab_test.data_source(source_id),
  identifier_system text NOT NULL, identifier_value text NOT NULL,
  verified boolean NOT NULL DEFAULT false, verification_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_id,identifier_system,identifier_value)
);
CREATE TABLE IF NOT EXISTS vab_test.fhir_resource (
  source_id text NOT NULL REFERENCES vab_test.data_source(source_id),
  resource_type text NOT NULL, resource_id text NOT NULL,
  patient_id uuid REFERENCES vab_test.patient(patient_id),
  last_updated timestamptz, retrieved_at timestamptz NOT NULL DEFAULT now(),
  sha256 text, resource jsonb NOT NULL, synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
  PRIMARY KEY (source_id, resource_type, resource_id)
);
CREATE TABLE IF NOT EXISTS vab_test.facility (
  facility_id text PRIMARY KEY, name text NOT NULL, facility_kind text NOT NULL,
  source_id text REFERENCES vab_test.data_source(source_id), city text, state text, attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.clinic (
  clinic_id text PRIMARY KEY, facility_id text NOT NULL REFERENCES vab_test.facility(facility_id),
  specialty text NOT NULL, name text NOT NULL, active boolean NOT NULL DEFAULT true,
  rules jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.appointment_request (
  request_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab_test.patient(patient_id),
  requested_service text NOT NULL, request_kind text NOT NULL CHECK (request_kind IN ('PRIMARY_CARE','SPECIALTY')),
  status text NOT NULL CHECK (status IN ('OPEN','TRIAGE','OPTIONS','CLOSED','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT now(), interaction_id text, provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.consult (
  consult_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab_test.patient(patient_id),
  request_id uuid REFERENCES vab_test.appointment_request(request_id),
  specialty text NOT NULL, status text NOT NULL, ordered_at timestamptz NOT NULL,
  expires_at timestamptz, source_id text REFERENCES vab_test.data_source(source_id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.slot (
  slot_id uuid PRIMARY KEY, clinic_id text REFERENCES vab_test.clinic(clinic_id),
  provider_id text, channel text NOT NULL CHECK (channel IN ('VISTA','FEDERAL_EHR','EPS')),
  begins_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, 
  status text NOT NULL CHECK (status IN ('AVAILABLE','HELD','BOOKED','BLOCKED')),
  source_id text REFERENCES vab_test.data_source(source_id), verified_at timestamptz,
  CHECK (ends_at > begins_at)
);
CREATE INDEX IF NOT EXISTS idx_slot_search ON vab_test.slot(channel,status,begins_at);
CREATE TABLE IF NOT EXISTS vab_test.referral (
  referral_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab_test.patient(patient_id),
  consult_id uuid REFERENCES vab_test.consult(consult_id),
  status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.authorization (
  authorization_id uuid PRIMARY KEY, referral_id uuid NOT NULL REFERENCES vab_test.referral(referral_id),
  status text NOT NULL, valid_from timestamptz, valid_until timestamptz,
  service_scope text NOT NULL, source_id text REFERENCES vab_test.data_source(source_id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.appointment (
  appointment_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab_test.patient(patient_id),
  request_id uuid NOT NULL REFERENCES vab_test.appointment_request(request_id),
  slot_id uuid NOT NULL UNIQUE REFERENCES vab_test.slot(slot_id),
  status text NOT NULL CHECK (status IN ('BOOKED_SIMULATED','CANCELLED_SIMULATED')),
  idempotency_key text NOT NULL UNIQUE,
  confirmed_at timestamptz NOT NULL DEFAULT now(), approved_by text,
  synthetic boolean NOT NULL DEFAULT true CHECK (synthetic)
);
CREATE TABLE IF NOT EXISTS vab_test.handoff (
  handoff_id uuid PRIMARY KEY, request_id uuid REFERENCES vab_test.appointment_request(request_id),
  status text NOT NULL, reason text NOT NULL, assigned_to text,
  decided_at timestamptz, decision jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.document_request (
  document_request_id uuid PRIMARY KEY, patient_id uuid REFERENCES vab_test.patient(patient_id),
  appointment_id uuid REFERENCES vab_test.appointment(appointment_id),
  document_type text NOT NULL CHECK (document_type IN ('SYNTHETIC_APPOINTMENT_CONFIRMATION','VA_SANDBOX_BENEFIT_LETTER')),
  status text NOT NULL, source_id text REFERENCES vab_test.data_source(source_id),
  created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab_test.audit_event (
  event_id uuid PRIMARY KEY, correlation_id text NOT NULL,
  interaction_id text, actor text NOT NULL, tool_name text,
  event_type text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
  source_id text REFERENCES vab_test.data_source(source_id), details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_audit_timeline ON vab_test.audit_event(correlation_id,occurred_at);


-- VAB scheduling persistence extension; DEV-only additive migration.
-- Requires 001_initial.sql and existing synthetic schema; no booking side effects.
-- This is 003 because 002_kb.sql is already allocated.

SET LOCAL lock_timeout = '5s';

CREATE TABLE IF NOT EXISTS vab_test.scheduling_case_link (
    case_id text PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE REFERENCES vab_test.appointment_request(request_id),
    source_request_id text NOT NULL UNIQUE,
    source_system text NOT NULL DEFAULT 'SYNTHETIC_MCP',
    synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(case_id) <> ''),
    CHECK (btrim(source_request_id) <> '')
);

CREATE TABLE IF NOT EXISTS vab_test.scheduling_transition (
    transition_id uuid PRIMARY KEY,
    case_id text NOT NULL REFERENCES vab_test.scheduling_case_link(case_id),
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
    ON vab_test.scheduling_transition(case_id, occurred_at, transition_id);
CREATE INDEX IF NOT EXISTS idx_scheduling_transition_correlation
    ON vab_test.scheduling_transition(correlation_id, occurred_at);

CREATE TABLE IF NOT EXISTS vab_test.scheduling_decision (
    decision_id uuid PRIMARY KEY,
    case_id text NOT NULL REFERENCES vab_test.scheduling_case_link(case_id),
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
    ON vab_test.scheduling_decision(case_id, decision_kind, decided_at);

-- Keep original appointment slot uniqueness until a separate reviewed
-- cancellation/rebooking policy is approved. No direct booking SQL is added.


-- Applied to Supabase project wntbjxjeaxngjrffmnis (2026-11-13).
-- Additive update to existing 003 lifecycle table; no KB changes.
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
  IF (SELECT COUNT(*) FROM vab_test.scheduling_decision) <> 0 THEN
    RAISE EXCEPTION 'Decision-order migration requires empty scheduling decision table; review existing rows separately';
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='vab_test' AND table_name='scheduling_decision' AND column_name='decision_order'
  ) THEN
    RAISE EXCEPTION 'decision_order already exists; stop rather than applying unknown schema state';
  END IF;
END $$;

ALTER TABLE vab_test.scheduling_decision
  ADD COLUMN decision_order bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE vab_test.scheduling_decision
  ADD CONSTRAINT scheduling_decision_order_unique UNIQUE (decision_order);
DROP INDEX IF EXISTS vab_test.idx_scheduling_decision_case_kind;
CREATE INDEX idx_scheduling_decision_case_kind
  ON vab_test.scheduling_decision(case_id, decision_kind, decision_order DESC);


-- Applied to Supabase project wntbjxjeaxngjrffmnis (2026-11-13).
-- Row-lock authorization without mutation privileges for clinical facts.
SET LOCAL lock_timeout='5s';
ALTER TABLE vab_test.authorization
  ADD COLUMN scheduling_lock_guard boolean NOT NULL DEFAULT true
  CHECK (scheduling_lock_guard);
ALTER TABLE vab_test.referral
  ADD COLUMN scheduling_lock_guard boolean NOT NULL DEFAULT true
  CHECK (scheduling_lock_guard);
ALTER TABLE vab_test.scheduling_decision
  ADD COLUMN scheduling_lock_guard boolean NOT NULL DEFAULT true
  CHECK (scheduling_lock_guard);

REVOKE ALL ON SCHEMA vab_test FROM PUBLIC, anon, authenticated, service_role;
DO $$ DECLARE item record;
BEGIN
  FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='vab_test' LOOP
    EXECUTE format('ALTER TABLE vab_test.%I ENABLE ROW LEVEL SECURITY',item.tablename);
  END LOOP;
END $$;
