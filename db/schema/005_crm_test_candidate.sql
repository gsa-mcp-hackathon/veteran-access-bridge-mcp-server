-- CRM candidate DDL for review. Not an applied Supabase migration.
-- Run only on the existing synthetic vab_test schema as its migration owner.
BEGIN;
SET LOCAL lock_timeout='5s';
CREATE TABLE vab_test.crm_interaction (
 record_id uuid PRIMARY KEY,
 case_id text NOT NULL REFERENCES vab_test.scheduling_case_link(case_id),
 interaction_id text NOT NULL CHECK(length(interaction_id) BETWEEN 1 AND 200),
 summary text NOT NULL CHECK(length(btrim(summary)) BETWEEN 1 AND 2000),
 disposition text NOT NULL CHECK(disposition IN ('INFORMATION_PROVIDED','FOLLOW_UP_NEEDED','HUMAN_REVIEW_REQUESTED','CALLER_DECLINED')),
 synthetic boolean NOT NULL DEFAULT true CHECK(synthetic),
 actor text NOT NULL DEFAULT 'AVERY' CHECK(actor='AVERY'),
 content_trust text NOT NULL DEFAULT 'UNTRUSTED_AGENT_NOTE' CHECK(content_trust='UNTRUSTED_AGENT_NOTE'),
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX crm_interaction_history ON vab_test.crm_interaction(case_id,created_at DESC,record_id);
CREATE TABLE vab_test.crm_follow_up (
 task_id uuid PRIMARY KEY,
 case_id text NOT NULL REFERENCES vab_test.scheduling_case_link(case_id),
 interaction_id text NOT NULL CHECK(length(interaction_id) BETWEEN 1 AND 200),
 description text NOT NULL CHECK(length(btrim(description)) BETWEEN 1 AND 1000),
 owner_queue text NOT NULL CHECK(owner_queue IN ('MSA','SCHEDULING_SUPPORT')),
 due_at timestamptz NOT NULL,
 status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','IN_PROGRESS','CANCELLED')),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 synthetic boolean NOT NULL DEFAULT true CHECK(synthetic),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX crm_follow_up_history ON vab_test.crm_follow_up(case_id,due_at,task_id);
CREATE TABLE vab_test.crm_event (
 event_id uuid PRIMARY KEY,
 case_id text NOT NULL REFERENCES vab_test.scheduling_case_link(case_id),
 interaction_id text NOT NULL,
 operation text NOT NULL CHECK(operation IN ('record_crm_interaction','create_crm_follow_up','update_crm_follow_up')),
 idempotency_key text NOT NULL CHECK(length(btrim(idempotency_key)) BETWEEN 1 AND 100),
 payload_hash text NOT NULL CHECK(length(payload_hash)=64),
 payload jsonb NOT NULL, receipt jsonb NOT NULL,
 synthetic boolean NOT NULL DEFAULT true CHECK(synthetic),
 actor text NOT NULL DEFAULT 'AVERY' CHECK(actor='AVERY'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(case_id,interaction_id,idempotency_key)
);
ALTER TABLE vab_test.crm_interaction ENABLE ROW LEVEL SECURITY;
ALTER TABLE vab_test.crm_interaction FORCE ROW LEVEL SECURITY;
ALTER TABLE vab_test.crm_follow_up ENABLE ROW LEVEL SECURITY;
ALTER TABLE vab_test.crm_follow_up FORCE ROW LEVEL SECURITY;
ALTER TABLE vab_test.crm_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE vab_test.crm_event FORCE ROW LEVEL SECURITY;
REVOKE ALL ON vab_test.crm_interaction,vab_test.crm_follow_up,vab_test.crm_event FROM PUBLIC,anon,authenticated,vab_test_scheduling_writer;
GRANT SELECT,INSERT ON vab_test.crm_interaction,vab_test.crm_event TO vab_test_scheduling_writer;
GRANT SELECT,INSERT ON vab_test.crm_follow_up TO vab_test_scheduling_writer;
GRANT UPDATE(status,version,updated_at) ON vab_test.crm_follow_up TO vab_test_scheduling_writer;
CREATE POLICY crm_read ON vab_test.crm_interaction FOR SELECT TO vab_test_scheduling_writer
 USING(case_id=current_setting('vab.crm_case_id',true));
CREATE POLICY crm_append ON vab_test.crm_interaction FOR INSERT TO vab_test_scheduling_writer
 WITH CHECK(case_id=current_setting('vab.crm_case_id',true) AND interaction_id=current_setting('vab.crm_interaction_id',true));
CREATE POLICY crm_task_read ON vab_test.crm_follow_up FOR SELECT TO vab_test_scheduling_writer
 USING(case_id=current_setting('vab.crm_case_id',true));
CREATE POLICY crm_task_create ON vab_test.crm_follow_up FOR INSERT TO vab_test_scheduling_writer
 WITH CHECK(case_id=current_setting('vab.crm_case_id',true) AND interaction_id=current_setting('vab.crm_interaction_id',true));
CREATE POLICY crm_task_update ON vab_test.crm_follow_up FOR UPDATE TO vab_test_scheduling_writer
 USING(case_id=current_setting('vab.crm_case_id',true))
 WITH CHECK(case_id=current_setting('vab.crm_case_id',true));
CREATE POLICY crm_event_read ON vab_test.crm_event FOR SELECT TO vab_test_scheduling_writer
 USING(case_id=current_setting('vab.crm_case_id',true) AND interaction_id=current_setting('vab.crm_interaction_id',true));
CREATE POLICY crm_event_append ON vab_test.crm_event FOR INSERT TO vab_test_scheduling_writer
 WITH CHECK(case_id=current_setting('vab.crm_case_id',true) AND interaction_id=current_setting('vab.crm_interaction_id',true));
COMMIT;
