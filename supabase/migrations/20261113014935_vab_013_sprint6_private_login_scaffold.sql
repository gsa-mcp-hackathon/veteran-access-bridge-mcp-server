-- Applied to approved Supabase project. NOLOGIN: not usable until
-- separate credential and activation review. Does not change KB access.
SET LOCAL lock_timeout='5s';
DO $$
BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vab_scheduling_login') THEN
  RAISE EXCEPTION 'vab_scheduling_login exists; do not overwrite authentication';
 END IF;
END $$;
CREATE ROLE vab_scheduling_login NOLOGIN NOINHERIT NOBYPASSRLS;
GRANT vab_scheduling_writer TO vab_scheduling_login WITH INHERIT FALSE, SET TRUE;
