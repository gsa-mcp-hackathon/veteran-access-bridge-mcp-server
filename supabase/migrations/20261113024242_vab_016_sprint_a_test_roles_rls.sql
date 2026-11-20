-- Applied as vab_016_sprint_a_test_roles_rls.
-- Both roles deliberately stay NOLOGIN. No access to operational vab or KB.
SET LOCAL lock_timeout='5s';
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname IN (
    'vab_test_scheduling_writer','vab_test_scheduling_login'
  )) THEN
    RAISE EXCEPTION 'Sprint A test roles already exist; manual review required';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='vab_test') THEN
    RAISE EXCEPTION 'vab_test schema missing';
  END IF;
END $$;
CREATE ROLE vab_test_scheduling_writer NOLOGIN NOINHERIT NOBYPASSRLS;
CREATE ROLE vab_test_scheduling_login NOLOGIN NOINHERIT NOBYPASSRLS;
GRANT vab_test_scheduling_writer TO vab_test_scheduling_login
  WITH INHERIT FALSE, SET TRUE;
GRANT USAGE ON SCHEMA vab_test TO vab_test_scheduling_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA vab_test
  TO vab_test_scheduling_writer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA vab_test
  TO vab_test_scheduling_writer;
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_catalog.pg_tables
    WHERE schemaname='vab_test'
  LOOP
    EXECUTE format(
      'CREATE POLICY %I ON vab_test.%I FOR ALL TO vab_test_scheduling_writer USING (true) WITH CHECK (true)',
      'vab_test_writer_isolation', t.tablename
    );
  END LOOP;
END $$;
