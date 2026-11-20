-- Applied to Supabase project wntbjxjeaxngjrffmnis (2026-11-13).
-- Row-lock authorization without mutation privileges for clinical facts.
SET LOCAL lock_timeout='5s';
ALTER TABLE vab.authorization
  ADD COLUMN scheduling_lock_guard boolean NOT NULL DEFAULT true
  CHECK (scheduling_lock_guard);
ALTER TABLE vab.referral
  ADD COLUMN scheduling_lock_guard boolean NOT NULL DEFAULT true
  CHECK (scheduling_lock_guard);
ALTER TABLE vab.scheduling_decision
  ADD COLUMN scheduling_lock_guard boolean NOT NULL DEFAULT true
  CHECK (scheduling_lock_guard);
GRANT UPDATE (scheduling_lock_guard) ON
  vab.authorization, vab.referral, vab.scheduling_decision
TO vab_scheduling_writer;
GRANT UPDATE (synthetic) ON
  vab.scheduling_case_link, vab.appointment
TO vab_scheduling_writer;
