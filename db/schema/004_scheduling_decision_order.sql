-- Local-only additive upgrade after 003_scheduling_lifecycle_evidence.sql.
-- Hosted Supabase has already applied the equivalent migration 011.
-- Historical 003 must remain unchanged to preserve migration replay.
BEGIN;
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE existing_identity text;
BEGIN
  IF to_regclass('vab.scheduling_decision') IS NULL THEN
    RAISE EXCEPTION 'Apply 003_scheduling_lifecycle_evidence.sql first';
  END IF;
  SELECT c.is_identity INTO existing_identity
    FROM information_schema.columns c
   WHERE c.table_schema='vab'
     AND c.table_name='scheduling_decision'
     AND c.column_name='decision_order';
  IF existing_identity IS NULL THEN
    IF EXISTS (SELECT 1 FROM vab.scheduling_decision) THEN
      RAISE EXCEPTION 'Existing decisions require a reviewed ordered backfill';
    END IF;
    ALTER TABLE vab.scheduling_decision
      ADD COLUMN decision_order bigint GENERATED ALWAYS AS IDENTITY;
  ELSIF existing_identity <> 'YES' THEN
    RAISE EXCEPTION 'decision_order exists but is not an identity column';
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c
    WHERE c.conrelid='vab.scheduling_decision'::regclass
      AND c.contype='u'
      AND c.conname='scheduling_decision_order_unique'
  ) THEN
    ALTER TABLE vab.scheduling_decision
      ADD CONSTRAINT scheduling_decision_order_unique UNIQUE (decision_order);
  END IF;
END $$;

DROP INDEX IF EXISTS vab.idx_scheduling_decision_case_kind;
CREATE INDEX idx_scheduling_decision_case_kind
  ON vab.scheduling_decision(case_id, decision_kind, decision_order DESC);
COMMIT;
