-- Stage 6.2 — isolated PostgreSQL regression probe.
-- ONLY run on project vendorflow-v11-staging. Synthetic metadata; NO real PDFs.
-- Every inserted row rolls back automatically via the inner exception block.
DO $vf62$
DECLARE
  report jsonb := '{}'::jsonb;
  app_revision integer;
  app_status text;
  stale_rejected boolean := false;
  wrong_manifest_rejected boolean := false;
  missing_manifest_rejected boolean := false;
  document_immutable boolean := false;
  duplicate_blocked boolean := false;
  replay_blocked boolean := false;
  b_manifest jsonb;
  error_text text;
  base_manifest jsonb;
  replaced_manifest jsonb;
BEGIN
  BEGIN
    INSERT INTO public.applications(id,payload_json,tracking_token_hash)
      VALUES ('VF-STAGE62-A', '{"gstin":"09ABCDE1234F1Z5"}',repeat('a',64));
    INSERT INTO public.documents(id,application_id,doc_type,storage_path,file_sha256,version,filename)
    VALUES
      ('62000000-0000-4000-8000-000000000001','VF-STAGE62-A','GST','VF-STAGE62-A/GST/v1-test.pdf',repeat('a',64),1,'gst-test.pdf'),
      ('62000000-0000-4000-8000-000000000002','VF-STAGE62-A','BANK','VF-STAGE62-A/BANK/v1-test.pdf',repeat('b',64),1,'bank-test.pdf'),
      ('62000000-0000-4000-8000-000000000003','VF-STAGE62-A','BANK','VF-STAGE62-A/BANK/v2-test.pdf',repeat('c',64),2,'bank-replacement.pdf');
    base_manifest := jsonb_build_array(
      jsonb_build_object('id','62000000-0000-4000-8000-000000000001','doc_type','GST','version',1,'file_sha256',repeat('a',64),'storage_path','VF-STAGE62-A/GST/v1-test.pdf'),
      jsonb_build_object('id','62000000-0000-4000-8000-000000000002','doc_type','BANK','version',1,'file_sha256',repeat('b',64),'storage_path','VF-STAGE62-A/BANK/v1-test.pdf')
    );
    replaced_manifest := jsonb_build_array(
      jsonb_build_object('id','62000000-0000-4000-8000-000000000001','doc_type','GST','version',1,'file_sha256',repeat('a',64),'storage_path','VF-STAGE62-A/GST/v1-test.pdf'),
      jsonb_build_object('id','62000000-0000-4000-8000-000000000003','doc_type','BANK','version',2,'file_sha256',repeat('c',64),'storage_path','VF-STAGE62-A/BANK/v2-test.pdf')
    );

    INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
      reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
    VALUES('RUN-STAGE62-A1','VF-STAGE62-A','submission','PENDING','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,0,base_manifest);
    SELECT revision INTO app_revision FROM public.applications WHERE id='VF-STAGE62-A';
    report := report || jsonb_build_object('S62_01_first_run_revision', CASE WHEN app_revision=1 THEN 'PASS' ELSE 'FAIL' END);

    BEGIN
      INSERT INTO public.review_actions(application_id,action,reason,reviewed_run_id,expected_revision)
      VALUES('VF-STAGE62-A','APPROVE','old stale reviewer','RUN-STAGE62-A1',0);
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      stale_rejected := position('stale_revision' in error_text) > 0;
    END;
    report := report || jsonb_build_object('S62_02_stale_review', CASE WHEN stale_rejected THEN 'PASS' ELSE 'FAIL' END);

    INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
      reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
    VALUES('RUN-STAGE62-A2','VF-STAGE62-A','resubmission','PENDING','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,1,replaced_manifest);
    report := report || jsonb_build_object('S62_03_new_bank_version_bound',
      CASE WHEN (SELECT revision=2 FROM public.applications WHERE id='VF-STAGE62-A') AND
        (SELECT document_manifest->1->>'id'='62000000-0000-4000-8000-000000000003' FROM public.runs WHERE id='RUN-STAGE62-A2')
      THEN 'PASS' ELSE 'FAIL' END);

    stale_rejected := false;
    BEGIN
      INSERT INTO public.review_actions(application_id,action,reason,reviewed_run_id,expected_revision)
      VALUES('VF-STAGE62-A','APPROVE','old document reviewed','RUN-STAGE62-A1',1);
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      stale_rejected := position('stale_revision' in error_text) > 0;
    END;
    report := report || jsonb_build_object('S62_04_old_run_review', CASE WHEN stale_rejected THEN 'PASS' ELSE 'FAIL' END);

    BEGIN
      UPDATE public.documents SET file_sha256=repeat('d',64)
      WHERE id='62000000-0000-4000-8000-000000000001';
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      document_immutable := position('cannot be modified' in error_text) > 0;
    END;
    report := report || jsonb_build_object('S62_05_immutable_documents', CASE WHEN document_immutable THEN 'PASS' ELSE 'FAIL' END);

    BEGIN
      INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
        reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
      VALUES('RUN-STAGE62-FAKE','VF-STAGE62-A','resubmission','PENDING','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,2,
        jsonb_set(replaced_manifest,'{1,file_sha256}',to_jsonb(repeat('0',64))));
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      wrong_manifest_rejected := position('manifest does not match' in error_text) > 0;
    END;
    report := report || jsonb_build_object('S62_06_forged_document', CASE WHEN wrong_manifest_rejected THEN 'PASS' ELSE 'FAIL' END);

    BEGIN
      INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
        reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
      VALUES('RUN-STAGE62-NODOC','VF-STAGE62-A','resubmission','APPROVED','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,2,'[]');
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      missing_manifest_rejected := position('requires both verified' in error_text) > 0;
    END;
    report := report || jsonb_build_object('S62_07_approval_requires_documents', CASE WHEN missing_manifest_rejected THEN 'PASS' ELSE 'FAIL' END);

    stale_rejected := false;
    BEGIN
      INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
        reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
      VALUES('RUN-STAGE62-STALE','VF-STAGE62-A','resubmission','PENDING','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,1,replaced_manifest);
    EXCEPTION WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      stale_rejected := position('stale_revision' in error_text) > 0;
    END;
    report := report || jsonb_build_object('S62_08_stale_vendor_cas', CASE WHEN stale_rejected THEN 'PASS' ELSE 'FAIL' END);

    report := report || jsonb_build_object('S62_11_failed_run_atomicity',
      CASE WHEN (SELECT count(*)=0 FROM public.runs WHERE id IN ('RUN-STAGE62-FAKE','RUN-STAGE62-NODOC','RUN-STAGE62-STALE'))
        AND (SELECT revision=2 AND current_status='PENDING' FROM public.applications WHERE id='VF-STAGE62-A')
      THEN 'PASS' ELSE 'FAIL' END);
    BEGIN
      INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
        reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
      VALUES('RUN-STAGE62-REPLAY','VF-STAGE62-A','submission','PENDING','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,2,base_manifest);
    EXCEPTION WHEN OTHERS THEN
      replay_blocked := true;
    END;
    report := report || jsonb_build_object('S62_12_initial_run_replay_blocked',
      CASE WHEN replay_blocked AND
        (SELECT count(*)=0 FROM public.runs WHERE id='RUN-STAGE62-REPLAY')
      THEN 'PASS' ELSE 'FAIL' END);

    INSERT INTO public.review_actions(application_id,action,reason,reviewed_run_id,expected_revision)
      VALUES('VF-STAGE62-A','APPROVE','current reviewer approval','RUN-STAGE62-A2',2);
    SELECT current_status, revision INTO app_status,app_revision FROM public.applications WHERE id='VF-STAGE62-A';
    report := report || jsonb_build_object('S62_09_current_review_atomic', CASE WHEN app_status='APPROVED' AND app_revision=3 THEN 'PASS' ELSE 'FAIL' END);

    INSERT INTO public.applications(id,payload_json,tracking_token_hash)
      VALUES ('VF-STAGE62-B','{"gstin":"09ABCDE1234F1Z5"}',repeat('b',64));
    INSERT INTO public.documents(id,application_id,doc_type,storage_path,file_sha256,version,filename)
    VALUES
      ('62000000-0000-4000-8000-000000000004','VF-STAGE62-B','GST','VF-STAGE62-B/GST/v1-test.pdf',repeat('e',64),1,'gst-b.pdf'),
      ('62000000-0000-4000-8000-000000000005','VF-STAGE62-B','BANK','VF-STAGE62-B/BANK/v1-test.pdf',repeat('f',64),1,'bank-b.pdf');
    b_manifest := jsonb_build_array(
      jsonb_build_object('id','62000000-0000-4000-8000-000000000004','doc_type','GST','version',1,'file_sha256',repeat('e',64),'storage_path','VF-STAGE62-B/GST/v1-test.pdf'),
      jsonb_build_object('id','62000000-0000-4000-8000-000000000005','doc_type','BANK','version',1,'file_sha256',repeat('f',64),'storage_path','VF-STAGE62-B/BANK/v1-test.pdf')
    );
    INSERT INTO public.runs(id,application_id,trigger,status,payload_json,stages_json,extracted_json,checks_json,
      reasons_json,all_reasons_json,next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
    VALUES('RUN-STAGE62-B1','VF-STAGE62-B','submission','PENDING','{"gstin":"09ABCDE1234F1Z5"}','[]','{}','[]','[]','[]','test',now(),now(),0,0,b_manifest);
    BEGIN
      INSERT INTO public.review_actions(application_id,action,reason,reviewed_run_id,expected_revision)
        VALUES('VF-STAGE62-B','APPROVE','duplicate synthetic identity','RUN-STAGE62-B1',1);
    EXCEPTION WHEN OTHERS THEN
      duplicate_blocked := true;
    END;
    report := report || jsonb_build_object('S62_10_approved_identity_unique',
      CASE WHEN duplicate_blocked AND
         (SELECT current_status='PENDING' FROM public.applications WHERE id='VF-STAGE62-B')
      THEN 'PASS' ELSE 'FAIL' END);

    report := report || jsonb_build_object('S62_13_failed_approval_kept_revision',
      CASE WHEN (SELECT revision=1 AND current_status='PENDING' FROM public.applications WHERE id='VF-STAGE62-B')
      THEN 'PASS' ELSE 'FAIL' END);

    -- Force SQL to undo ALL synthetic changes, regardless of test outcomes.
    RAISE EXCEPTION USING ERRCODE='Z6201',MESSAGE='stage6_2_rollback';
  EXCEPTION WHEN SQLSTATE 'Z6201' THEN NULL;
    WHEN OTHERS THEN
      GET STACKED DIAGNOSTICS error_text = MESSAGE_TEXT;
      report := report || jsonb_build_object('TEST_ERROR',left(error_text,220));
  END;
  PERFORM set_config('vendorflow.stage62_report',report::text,false);
END $vf62$;

SELECT result.key AS test, result.value AS result,
  ((SELECT count(*) FROM public.applications WHERE id LIKE 'VF-STAGE62-%')+
   (SELECT count(*) FROM public.documents WHERE application_id LIKE 'VF-STAGE62-%')+
   (SELECT count(*) FROM public.runs WHERE application_id LIKE 'VF-STAGE62-%')+
   (SELECT count(*) FROM public.review_actions WHERE application_id LIKE 'VF-STAGE62-%')) AS remaining_test_rows
FROM jsonb_each_text(current_setting('vendorflow.stage62_report',true)::jsonb) result
ORDER BY result.key;
