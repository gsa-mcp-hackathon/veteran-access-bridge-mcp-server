-- Aggregate only. Keys are SHA-256 of lower(full fixture name) | ISO birth date.
-- This mirrors the dynamic resolver's exact persisted-patient match.
WITH roster(k) AS (
    VALUES
        ('ed996be5debe7de8f821188ddae3ec6f20cd486b08bd1f8a6cea404f6573771f'),
        ('3be7524198752c69fee86884bc753242ab685ac772393bed3ef6e1afeec2090d'),
        ('ddc6272ecbe887c7305e3845f8c46a70e92250fa746b69b9abe7ee26ee352ffa')
), candidates AS (
    SELECT k, count(p.patient_id) AS matches,
           bool_or(EXISTS (
               SELECT 1 FROM vab_test.appointment a WHERE a.patient_id = p.patient_id
           )) AS booked,
           bool_or(EXISTS (
               SELECT 1 FROM vab_test.appointment_request r
               WHERE r.patient_id = p.patient_id
                 AND r.provenance->>'voice_session_id' IS NOT NULL
                 AND (r.provenance->>'call_expires_at')::timestamptz > now()
                 AND r.status IN ('OPEN','OPTIONS')
           )) AS active
    FROM roster LEFT JOIN vab_test.patient p ON p.synthetic
      AND encode(sha256(convert_to(lower(p.display_name) || '|' ||
          to_char(p.birth_date,'YYYY-MM-DD'),'UTF8')),'hex') = k
    GROUP BY k
)
SELECT count(*) AS roster,
       count(*) FILTER (WHERE matches = 0) AS would_need_patient_creation,
       count(*) FILTER (WHERE matches > 1) AS ambiguous,
       count(*) FILTER (WHERE matches = 1 AND booked) AS already_booked,
       count(*) FILTER (WHERE matches = 1 AND active) AS active,
       count(*) FILTER (WHERE matches = 1 AND NOT booked AND NOT active)
           AS existing_unused_inactive
FROM candidates;
