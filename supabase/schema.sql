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
    created_at timestamptz not null default now()
);

create table if not exists public.review_actions (
    id uuid primary key default gen_random_uuid(),
    application_id text not null references public.applications(id) on delete restrict,
    action text not null check (action in ('APPROVE','REQUEST_CORRECTION','REJECT')),
    reason text not null check (char_length(btrim(reason)) >= 3),
    actor text not null default 'demo-admin',
    created_at timestamptz not null default now()
);

create unique index if not exists uq_vendorflow_approved_gstin on public.applications (gstin_normalized) where current_status='APPROVED';
create index if not exists idx_apps_status_gstin on public.applications (current_status,gstin_normalized);
create index if not exists idx_docs_application on public.documents (application_id,doc_type,version desc);
create index if not exists idx_runs_application on public.runs (application_id,started_at desc);
create index if not exists idx_reviews_application on public.review_actions (application_id,created_at desc);

-- This guard commits the run and current app status in ONE database transaction.
-- If this trigger raises, the run insert is rolled back automatically.
create or replace function public.vendorflow_commit_run()
returns trigger language plpgsql security invoker set search_path = '' as $$
declare app_status text;
begin
    select current_status into app_status
    from public.applications where id = new.application_id for update;
    if app_status is null then
        raise exception 'Application does not exist';
    end if;
    if app_status in ('APPROVED','REJECTED') then
        raise exception 'A terminal application cannot be resubmitted';
    end if;
    if new.trigger = 'submission' and exists (
        select 1 from public.runs where application_id = new.application_id and id <> new.id
    ) then
        raise exception 'Initial submission already has a run';
    end if;
    if new.trigger = 'resubmission' and not exists (
        select 1 from public.runs where application_id = new.application_id and id <> new.id
    ) then
        raise exception 'Cannot resubmit an application with no previous run';
    end if;
    update public.applications set
        payload_json = new.payload_json,
        current_status = new.status,
        decision_source = 'AUTOMATED',
        latest_run_id = new.id,
        updated_at = now()
    where id = new.application_id;
    return new;
end;
$$;

drop trigger if exists trg_vendorflow_commit_run on public.runs;
create trigger trg_vendorflow_commit_run
    after insert on public.runs for each row
    execute function public.vendorflow_commit_run();

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

-- Admin decisions and latest visible status also commit in one transaction.
create or replace function public.vendorflow_apply_review_action()
returns trigger language plpgsql security invoker set search_path = '' as $$
declare app_status text;
begin
    select current_status into app_status from public.applications
      where id = new.application_id for update;
    if app_status is distinct from 'PENDING' then
        raise exception 'Only pending applications can receive review actions';
    end if;
    update public.applications set
        current_status = case
            when new.action = 'APPROVE' then 'APPROVED'
            when new.action = 'REJECT' then 'REJECTED'
            else 'PENDING' end,
        decision_source = 'MANUAL',
        updated_at = now()
    where id = new.application_id;
    return new;
end;
$$;
drop trigger if exists trg_vendorflow_apply_review_action on public.review_actions;
create trigger trg_vendorflow_apply_review_action
    after insert on public.review_actions for each row
    execute function public.vendorflow_apply_review_action();

-- Server-only backend. No anon/authenticated table grants or RLS policies.
alter table public.applications enable row level security;
alter table public.documents enable row level security;
alter table public.runs enable row level security;
alter table public.review_actions enable row level security;
revoke all on table public.applications, public.documents, public.runs, public.review_actions from anon, authenticated;
revoke execute on function public.vendorflow_commit_run() from public, anon, authenticated;
revoke execute on function public.vendorflow_prevent_run_mutation() from public, anon, authenticated;
revoke execute on function public.vendorflow_apply_review_action() from public, anon, authenticated;

-- Private bucket. Its objects are never exposed through public URLs.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('vendor-documents', 'vendor-documents', false, 5242880, array['application/pdf']::text[])
on conflict (id) do update set public=false, file_size_limit=5242880, allowed_mime_types=array['application/pdf']::text[];
