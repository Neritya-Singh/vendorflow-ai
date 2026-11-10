-- Stage 6.2 — Staging-first: atomic revision CAS, immutable run provenance.
-- Apply to ONLY vendorflow-v11-staging; do NOT apply to the production project.
-- Migration is additive to Stage 6.1 schema. Existing records remain intact.

ALTER TABLE public.applications
  ADD COLUMN IF NOT EXISTS revision integer NOT NULL DEFAULT 0;
ALTER TABLE public.applications
  ADD CONSTRAINT vf_revision_nonnegative CHECK (revision >= 0);

ALTER TABLE public.runs
  ADD COLUMN IF NOT EXISTS expected_revision integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS document_manifest jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE public.runs
  ADD CONSTRAINT vf_run_manifest_array CHECK (jsonb_typeof(document_manifest) = 'array'),
  ADD CONSTRAINT vf_run_expected_revision_nonnegative CHECK (expected_revision >= 0);

ALTER TABLE public.review_actions
  ADD COLUMN IF NOT EXISTS expected_revision integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS reviewed_run_id text;
ALTER TABLE public.review_actions
  ADD CONSTRAINT vf_review_expected_revision_nonnegative CHECK (expected_revision >= 0);

-- Completed document metadata must never silently change underneath historical runs.
CREATE OR REPLACE FUNCTION public.vendorflow_prevent_document_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'Saved document versions cannot be modified or deleted';
END;
$$;
DROP TRIGGER IF EXISTS trg_vendorflow_immutable_document ON public.documents;
CREATE TRIGGER trg_vendorflow_immutable_document
  BEFORE UPDATE OR DELETE ON public.documents FOR EACH ROW
  EXECUTE FUNCTION public.vendorflow_prevent_document_mutation();

CREATE OR REPLACE FUNCTION public.vendorflow_commit_run()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  app_record record;
  entry jsonb;
  matched_count integer;
  seen_types text[] := ARRAY[]::text[];
  entry_type text;
BEGIN
  -- FOR UPDATE serializes vendor resubmissions and admin decisions on the app.
  SELECT revision, current_status, latest_run_id
    INTO app_record FROM public.applications
    WHERE id = NEW.application_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Application does not exist';
  END IF;
  IF app_record.current_status IN ('APPROVED','REJECTED') THEN
    RAISE EXCEPTION 'A terminal application cannot be resubmitted';
  END IF;
  IF NEW.expected_revision <> app_record.revision THEN
    RAISE EXCEPTION 'stale_revision: application changed before this run was saved';
  END IF;
  IF NEW.trigger = 'submission' AND app_record.latest_run_id IS NOT NULL THEN
    RAISE EXCEPTION 'Initial submission already has a run';
  END IF;
  IF NEW.trigger = 'resubmission' AND app_record.latest_run_id IS NULL THEN
    RAISE EXCEPTION 'Cannot resubmit an application with no previous run';
  END IF;
  IF jsonb_typeof(NEW.document_manifest) IS DISTINCT FROM 'array'
    OR jsonb_array_length(NEW.document_manifest) > 2 THEN
    RAISE EXCEPTION 'Invalid source-document manifest';
  END IF;
  FOR entry IN SELECT value FROM jsonb_array_elements(NEW.document_manifest) LOOP
    entry_type := entry->>'doc_type';
    IF entry_type NOT IN ('GST','BANK') OR entry_type = ANY(seen_types) THEN
      RAISE EXCEPTION 'Duplicate or invalid source-document type';
    END IF;
    seen_types := array_append(seen_types, entry_type);
    SELECT count(*) INTO matched_count FROM public.documents d
      WHERE d.id = (entry->>'id')::uuid
        AND d.application_id = NEW.application_id
        AND d.doc_type = entry_type
        AND d.version = (entry->>'version')::integer
        AND d.file_sha256 = entry->>'file_sha256'
        AND d.storage_path = entry->>'storage_path';
    IF matched_count <> 1 THEN
      RAISE EXCEPTION 'Source-document manifest does not match saved version';
    END IF;
  END LOOP;
  IF NEW.status = 'APPROVED' AND NOT ('GST' = ANY(seen_types) AND 'BANK' = ANY(seen_types)) THEN
    RAISE EXCEPTION 'Automatic approval requires both verified source-document versions';
  END IF;
  UPDATE public.applications SET
    payload_json = NEW.payload_json,
    current_status = NEW.status,
    decision_source = 'AUTOMATED',
    latest_run_id = NEW.id,
    revision = revision + 1,
    updated_at = now()
  WHERE id = NEW.application_id;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.vendorflow_apply_review_action()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  app_record record;
BEGIN
  SELECT current_status, latest_run_id, revision INTO app_record
    FROM public.applications WHERE id = NEW.application_id FOR UPDATE;
  IF NOT FOUND OR app_record.current_status IS DISTINCT FROM 'PENDING'
    OR app_record.latest_run_id IS NULL THEN
    RAISE EXCEPTION 'Only completed pending applications can receive review actions';
  END IF;
  IF NEW.expected_revision <> app_record.revision
     OR NEW.reviewed_run_id IS DISTINCT FROM app_record.latest_run_id THEN
    RAISE EXCEPTION 'stale_revision: reviewed evidence is no longer current';
  END IF;
  UPDATE public.applications SET
    current_status = CASE
      WHEN NEW.action = 'APPROVE' THEN 'APPROVED'
      WHEN NEW.action = 'REJECT' THEN 'REJECTED'
      ELSE 'PENDING' END,
    decision_source = 'MANUAL',
    revision = revision + 1,
    updated_at = now()
  WHERE id = NEW.application_id;
  RETURN NEW;
END;
$$;

-- Existing triggers stay attached to the updated functions.
REVOKE EXECUTE ON FUNCTION public.vendorflow_prevent_document_mutation()
  FROM public, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.vendorflow_commit_run()
  FROM public, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.vendorflow_apply_review_action()
  FROM public, anon, authenticated;
