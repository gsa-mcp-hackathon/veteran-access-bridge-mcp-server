-- Applied to Supabase project wntbjxjeaxngjrffmnis (2026-11-13).
-- Additive update to existing 003 lifecycle table; no KB changes.
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
  IF (SELECT COUNT(*) FROM vab.scheduling_decision) <> 0 THEN
    RAISE EXCEPTION 'Decision-order migration requires empty scheduling decision table; review existing rows separately';
  END IF;
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='vab' AND table_name='scheduling_decision' AND column_name='decision_order'
  ) THEN
    RAISE EXCEPTION 'decision_order already exists; stop rather than applying unknown schema state';
  END IF;
END $$;

ALTER TABLE vab.scheduling_decision
  ADD COLUMN decision_order bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE vab.scheduling_decision
  ADD CONSTRAINT scheduling_decision_order_unique UNIQUE (decision_order);
DROP INDEX IF EXISTS vab.idx_scheduling_decision_case_kind;
CREATE INDEX idx_scheduling_decision_case_kind
  ON vab.scheduling_decision(case_id, decision_kind, decision_order DESC);
