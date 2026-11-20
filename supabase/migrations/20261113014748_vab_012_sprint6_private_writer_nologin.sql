-- Applied to approved Supabase project. Role cannot authenticate.
-- No grants to anon, authenticated, service_role, or Avery's KB login.
SET LOCAL lock_timeout='5s';
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vab_scheduling_writer') THEN
  RAISE EXCEPTION 'vab_scheduling_writer already exists; review grants rather than overwrite';
 END IF;
END $$;
CREATE ROLE vab_scheduling_writer NOLOGIN NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA vab TO vab_scheduling_writer;
GRANT SELECT ON
 vab.scheduling_case_link, vab.appointment_request, vab.slot,
 vab.data_source, vab.authorization, vab.referral, vab.scheduling_decision,
 vab.scheduling_transition, vab.appointment, vab.audit_event
TO vab_scheduling_writer;
GRANT INSERT ON
 vab.scheduling_decision, vab.scheduling_transition,
 vab.appointment, vab.audit_event
TO vab_scheduling_writer;
GRANT UPDATE (status) ON vab.slot TO vab_scheduling_writer;
GRANT USAGE ON SEQUENCE vab.scheduling_decision_decision_order_seq TO vab_scheduling_writer;
