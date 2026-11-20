-- Veteran Access Bridge: PostgreSQL synthetic-first data foundation.
-- Idempotent DDL; does not migrate or modify existing runtime stores.
BEGIN;
CREATE SCHEMA IF NOT EXISTS vab;
CREATE TABLE IF NOT EXISTS vab.data_source (
  source_id text PRIMARY KEY, source_kind text NOT NULL CHECK (source_kind IN ('sandbox','synthea','synthetic_fixture','public')),
  description text, collected_at timestamptz, provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.patient (
  patient_id uuid PRIMARY KEY, demo_patient_key text UNIQUE NOT NULL,
  display_name text, birth_date date, synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
  source_id text REFERENCES vab.data_source(source_id), source_patient_id text,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS vab.patient_identity (
  identity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  patient_id uuid NOT NULL REFERENCES vab.patient(patient_id),
  source_id text NOT NULL REFERENCES vab.data_source(source_id),
  identifier_system text NOT NULL, identifier_value text NOT NULL,
  verified boolean NOT NULL DEFAULT false, verification_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_id,identifier_system,identifier_value)
);
CREATE TABLE IF NOT EXISTS vab.fhir_resource (
  source_id text NOT NULL REFERENCES vab.data_source(source_id),
  resource_type text NOT NULL, resource_id text NOT NULL,
  patient_id uuid REFERENCES vab.patient(patient_id),
  last_updated timestamptz, retrieved_at timestamptz NOT NULL DEFAULT now(),
  sha256 text, resource jsonb NOT NULL, synthetic boolean NOT NULL DEFAULT true CHECK (synthetic),
  PRIMARY KEY (source_id, resource_type, resource_id)
);
CREATE TABLE IF NOT EXISTS vab.facility (
  facility_id text PRIMARY KEY, name text NOT NULL, facility_kind text NOT NULL,
  source_id text REFERENCES vab.data_source(source_id), city text, state text, attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.clinic (
  clinic_id text PRIMARY KEY, facility_id text NOT NULL REFERENCES vab.facility(facility_id),
  specialty text NOT NULL, name text NOT NULL, active boolean NOT NULL DEFAULT true,
  rules jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.appointment_request (
  request_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab.patient(patient_id),
  requested_service text NOT NULL, request_kind text NOT NULL CHECK (request_kind IN ('PRIMARY_CARE','SPECIALTY')),
  status text NOT NULL CHECK (status IN ('OPEN','TRIAGE','OPTIONS','CLOSED','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT now(), interaction_id text, provenance jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.consult (
  consult_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab.patient(patient_id),
  request_id uuid REFERENCES vab.appointment_request(request_id),
  specialty text NOT NULL, status text NOT NULL, ordered_at timestamptz NOT NULL,
  expires_at timestamptz, source_id text REFERENCES vab.data_source(source_id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.slot (
  slot_id uuid PRIMARY KEY, clinic_id text REFERENCES vab.clinic(clinic_id),
  provider_id text, channel text NOT NULL CHECK (channel IN ('VISTA','FEDERAL_EHR','EPS')),
  begins_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, 
  status text NOT NULL CHECK (status IN ('AVAILABLE','HELD','BOOKED','BLOCKED')),
  source_id text REFERENCES vab.data_source(source_id), verified_at timestamptz,
  CHECK (ends_at > begins_at)
);
CREATE INDEX IF NOT EXISTS idx_slot_search ON vab.slot(channel,status,begins_at);
CREATE TABLE IF NOT EXISTS vab.referral (
  referral_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab.patient(patient_id),
  consult_id uuid REFERENCES vab.consult(consult_id),
  status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.authorization (
  authorization_id uuid PRIMARY KEY, referral_id uuid NOT NULL REFERENCES vab.referral(referral_id),
  status text NOT NULL, valid_from timestamptz, valid_until timestamptz,
  service_scope text NOT NULL, source_id text REFERENCES vab.data_source(source_id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.appointment (
  appointment_id uuid PRIMARY KEY, patient_id uuid NOT NULL REFERENCES vab.patient(patient_id),
  request_id uuid NOT NULL REFERENCES vab.appointment_request(request_id),
  slot_id uuid NOT NULL UNIQUE REFERENCES vab.slot(slot_id),
  status text NOT NULL CHECK (status IN ('BOOKED_SIMULATED','CANCELLED_SIMULATED')),
  idempotency_key text NOT NULL UNIQUE,
  confirmed_at timestamptz NOT NULL DEFAULT now(), approved_by text,
  synthetic boolean NOT NULL DEFAULT true CHECK (synthetic)
);
CREATE TABLE IF NOT EXISTS vab.handoff (
  handoff_id uuid PRIMARY KEY, request_id uuid REFERENCES vab.appointment_request(request_id),
  status text NOT NULL, reason text NOT NULL, assigned_to text,
  decided_at timestamptz, decision jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.document_request (
  document_request_id uuid PRIMARY KEY, patient_id uuid REFERENCES vab.patient(patient_id),
  appointment_id uuid REFERENCES vab.appointment(appointment_id),
  document_type text NOT NULL CHECK (document_type IN ('SYNTHETIC_APPOINTMENT_CONFIRMATION','VA_SANDBOX_BENEFIT_LETTER')),
  status text NOT NULL, source_id text REFERENCES vab.data_source(source_id),
  created_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS vab.audit_event (
  event_id uuid PRIMARY KEY, correlation_id text NOT NULL,
  interaction_id text, actor text NOT NULL, tool_name text,
  event_type text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
  source_id text REFERENCES vab.data_source(source_id), details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_audit_timeline ON vab.audit_event(correlation_id,occurred_at);
COMMIT;
