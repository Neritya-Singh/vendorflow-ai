-- VendorFlow AI: one fictional Indian company's synthetic vendor applications.
-- Run ONCE in a NEW Supabase project via SQL Editor. No real personal/tax/banking data.
-- Uses only four application tables and one private Storage bucket.

create extension if not exists pgcrypto;

create table if not exists public.applications (
    id text primary key,
    payload_json jsonb not null default '{}'::jsonb,
    gstin_normalized text generated always as (upper(regexp_replace(coalesce(payload_json->>'gstin',''), '[[:space:]]+', '', 'g'))) stored,
    tracking_token_hash text not null,
    current_status text not null default 'PENDING'
        check (current_status in ('APPROVED','PENDING','REJECTED')),
    decision_source text not null default 'AUTOMATED'
        check (decision_source in ('AUTOMATED','MANUAL')),
    latest_run_id text,
    revision integer not null default 0 check (revision >= 0),
    constraint approved_gstin_valid_format check (current_status <> 'APPROVED' or gstin_normalized ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(),
    application_id text not null references public.applications(id) on delete restrict,
    doc_type text not null check (doc_type in ('GST','BANK')),
    storage_path text not null unique,
    file_sha256 text not null,
    version integer not null check (version >= 1),
    filename text not null,
    uploaded_at timestamptz not null default now(),
    unique (application_id,doc_type,version)
);

create table if not exists public.runs (
    id text primary key,
    application_id text not null references public.applications(id) on delete restrict,
    trigger text not null check (trigger in ('submission','resubmission')),
    status text not null check (status in ('APPROVED','PENDING')),
    decision text not null default 'AUTOMATED' check (decision = 'AUTOMATED'),
    payload_json jsonb not null,
    stages_json jsonb not null,
    extracted_json jsonb not null,
    checks_json jsonb not null,
    reasons_json jsonb not null,
    all_reasons_json jsonb not null,
    next_action text not null,
    extraction_error boolean not null default false,
    started_at timestamptz not null,
    finished_at timestamptz not null,
    elapsed_ms integer not null check (elapsed_ms >= 0),
    expected_revision integer not null default 0 check (expected_revision >= 0),
    document_manifest jsonb not null default '[]'::jsonb check (jsonb_typeof(document_manifest) = 'array'),
    created_at timestamptz not null default now()
);

create table if not exists public.review_actions (
    id uuid primary key default gen_random_uuid(),
    application_id text not null references public.applications(id) on delete restrict,
    action text not null check (action in ('APPROVE','REQUEST_CORRECTION','REJECT')),
    reason text not null check (char_length(btrim(reason)) >= 3),
    actor text not null default 'demo-admin',
    expected_revision integer not null default 0 check (expected_revision >= 0),
    reviewed_run_id text,
    created_at timestamptz not null default now()
);

create unique index if not exists uq_vendorflow_approved_gstin on public.applications (gstin_normalized) where current_status='APPROVED';
create index if not exists idx_apps_status_gstin on public.applications (current_status,gstin_normalized);
create index if not exists idx_docs_application on public.documents (application_id,doc_type,version desc);
create index if not exists idx_runs_application on public.runs (application_id,started_at desc);
create index if not exists idx_reviews_application on public.review_actions (application_id,created_at desc);

-- Stage 6.2: revision CAS, immutable PDF provenance and existing audit protections.
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

-- Completed runs are immutable audit records.
create or replace function public.vendorflow_prevent_run_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
    raise exception 'Historical workflow runs cannot be changed or deleted';
end;
$$;
drop trigger if exists trg_vendorflow_no_run_mutation on public.runs;
create trigger trg_vendorflow_no_run_mutation
    before update or delete on public.runs for each row
    execute function public.vendorflow_prevent_run_mutation();


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

DROP TRIGGER IF EXISTS trg_vendorflow_commit_run ON public.runs;
CREATE TRIGGER trg_vendorflow_commit_run AFTER INSERT ON public.runs
  FOR EACH ROW EXECUTE FUNCTION public.vendorflow_commit_run();
DROP TRIGGER IF EXISTS trg_vendorflow_apply_review_action ON public.review_actions;
CREATE TRIGGER trg_vendorflow_apply_review_action AFTER INSERT ON public.review_actions
  FOR EACH ROW EXECUTE FUNCTION public.vendorflow_apply_review_action();

-- Server-only backend. No anon/authenticated table grants or RLS policies.
alter table public.applications enable row level security;
alter table public.documents enable row level security;
alter table public.runs enable row level security;
alter table public.review_actions enable row level security;
revoke all on table public.applications, public.documents, public.runs, public.review_actions from anon, authenticated;
revoke execute on function public.vendorflow_commit_run() from public, anon, authenticated;
revoke execute on function public.vendorflow_prevent_run_mutation() from public, anon, authenticated;
revoke execute on function public.vendorflow_apply_review_action() from public, anon, authenticated;
revoke execute on function public.vendorflow_prevent_document_mutation() from public, anon, authenticated;

-- Private bucket. Its objects are never exposed through public URLs.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('vendor-documents', 'vendor-documents', false, 5242880, array['application/pdf']::text[])
on conflict (id) do update set public=false, file_size_limit=5242880, allowed_mime_types=array['application/pdf']::text[];
