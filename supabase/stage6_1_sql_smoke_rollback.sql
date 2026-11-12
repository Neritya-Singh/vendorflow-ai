-- VendorFlow Stage 6.1: STAGING ONLY. All synthetic data is rolled back.
-- Requires the applied stage6_1_approved_gstin_integrity migration.
DO $stage61$
DECLARE
  report jsonb := '{}'::jsonb;
  got_key text;
  was_blocked boolean;
  got_sqlstate text;
BEGIN
  BEGIN
    -- Automatic approval of a spaced/lowercase GSTIN.
    INSERT INTO public.applications(id,payload_json,tracking_token_hash)
      VALUES ('VF-S61-A','{"gstin":" 09abcde 1234f1z5 "}',repeat('a',64));
    INSERT INTO public.runs(id,application_id,trigger,status,payload_json,
        stages_json,extracted_json,checks_json,reasons_json,all_reasons_json,
        next_action,started_at,finished_at,elapsed_ms)
      VALUES ('RUN-S61-A','VF-S61-A','submission','APPROVED',
        '{"gstin":" 09abcde 1234f1z5 "}',
        '[]','{}','[]','[]','[]','synthetic',now(),now(),0);
    SELECT gstin_normalized INTO got_key FROM public.applications WHERE id='VF-S61-A';
    report := report || jsonb_build_object('S61_01_canonical_key',
      CASE WHEN got_key='09ABCDE1234F1Z5' THEN 'PASS' ELSE 'FAIL' END);

    -- Another automatic run using the same identity must be rejected.
    INSERT INTO public.applications(id,payload_json,tracking_token_hash)
      VALUES ('VF-S61-B','{"gstin":"09ABCDE1234F1Z5"}',repeat('b',64));
    INSERT INTO public.runs(id,application_id,trigger,status,payload_json,
        stages_json,extracted_json,checks_json,reasons_json,all_reasons_json,
        next_action,started_at,finished_at,elapsed_ms)
      VALUES ('RUN-S61-B','VF-S61-B','submission','PENDING',
        '{"gstin":"09ABCDE1234F1Z5"}',
        '[]','{}','[]','[]','[]','synthetic',now(),now(),0);
    was_blocked := false;
    BEGIN
      INSERT INTO public.runs(id,application_id,trigger,status,payload_json,
          stages_json,extracted_json,checks_json,reasons_json,all_reasons_json,
          next_action,started_at,finished_at,elapsed_ms)
        VALUES ('RUN-S61-B2','VF-S61-B','resubmission','APPROVED',
          '{"gstin":"09ABCDE1234F1Z5"}',
          '[]','{}','[]','[]','[]','synthetic',now(),now(),0);
    EXCEPTION WHEN unique_violation THEN
      was_blocked := true;
    END;
    report := report || jsonb_build_object('S61_02_automatic_conflict',
      CASE WHEN was_blocked THEN 'PASS' ELSE 'FAIL' END);

    -- Admin approval uses the same database constraint.
    was_blocked := false;
    BEGIN
      INSERT INTO public.review_actions(application_id,action,reason,actor)
        VALUES('VF-S61-B','APPROVE','Synthetic staff approval','s61-probe');
    EXCEPTION WHEN unique_violation THEN
      was_blocked := true;
    END;
    report := report || jsonb_build_object('S61_03_manual_conflict',
      CASE WHEN was_blocked THEN 'PASS' ELSE 'FAIL' END);

    -- Invalid registration may be PENDING but not APPROVED.
    INSERT INTO public.applications(id,payload_json,tracking_token_hash)
      VALUES ('VF-S61-C','{"gstin":"invalid"}',repeat('c',64));
    INSERT INTO public.runs(id,application_id,trigger,status,payload_json,
        stages_json,extracted_json,checks_json,reasons_json,all_reasons_json,
        next_action,started_at,finished_at,elapsed_ms)
      VALUES ('RUN-S61-C','VF-S61-C','submission','PENDING',
        '{"gstin":"invalid"}',
        '[]','{}','[]','[]','[]','synthetic',now(),now(),0);
    was_blocked := false;
    BEGIN
      INSERT INTO public.review_actions(application_id,action,reason,actor)
        VALUES('VF-S61-C','APPROVE','Synthetic invalid ID approval','s61-probe');
    EXCEPTION WHEN check_violation THEN
      was_blocked := true;
    END;
    report := report || jsonb_build_object('S61_04_invalid_gstin',
      CASE WHEN was_blocked THEN 'PASS' ELSE 'FAIL' END);

    -- Roll back all writes in this inner subtransaction, even after a PASS.
    RAISE EXCEPTION USING ERRCODE='Z6101', MESSAGE='intentional_stage6_1_rollback';
  EXCEPTION
    WHEN SQLSTATE 'Z6101' THEN NULL;
    WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS got_sqlstate = RETURNED_SQLSTATE;
      report := report || jsonb_build_object('TEST_ERROR',got_sqlstate);
  END;
  PERFORM set_config('vendorflow.stage61_report',report::text,false);
END $stage61$;

SELECT key AS test_id, value AS result,
    (SELECT count(*) FROM public.applications WHERE id LIKE 'VF-S61-%')
     + (SELECT count(*) FROM public.runs WHERE id LIKE 'RUN-S61-%')
     + (SELECT count(*) FROM public.review_actions WHERE actor='s61-probe')
       AS remaining_test_rows
FROM jsonb_each_text(current_setting('vendorflow.stage61_report',true)::jsonb)
ORDER BY key;
