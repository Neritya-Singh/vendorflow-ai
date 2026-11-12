"""STAGING ONLY. Two independent transactions; synthetic-only, rollback-only.

Tests that a second manual approval cannot finish while a distinct application
with the same GSTIN is approved inside another open transaction.
"""
from __future__ import annotations

import sys
import threading
import uuid
from dataclasses import dataclass
from getpass import getpass
from urllib.parse import urlsplit, unquote

try:
    import psycopg
except ImportError:
    raise SystemExit("Install: python -m pip install 'psycopg[binary]'")

REF = 'hkxalnpnchzheorrogci'
GSTIN = '09ABCDE1234F1Z5'  # synthetic
TABLES = ('applications', 'documents', 'runs', 'review_actions')


def open_connection(credentials):
    return psycopg.connect(**credentials, connect_timeout=8,
                           sslmode='require', application_name='vendorflow-s62-staging-test')


def preflight(credentials):
    with open_connection(credentials) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT (SELECT count(*) FROM public.applications), (SELECT count(*) FROM public.documents), (SELECT count(*) FROM public.runs), (SELECT count(*) FROM public.review_actions)")
            counts = cur.fetchone()
            if counts != (0, 0, 0, 0):
                raise RuntimeError(f'Unsafe: staging contains records {counts}; no tests performed')
            cur.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname='uq_vendorflow_approved_gstin'")
            if cur.fetchone()[0] != 1:
                raise RuntimeError('Missing approved GSTIN uniqueness index')
            cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='runs' AND column_name='document_manifest'")
            if cur.fetchone()[0] != 1:
                raise RuntimeError('Stage 6.2 revision/provenance migration missing')
        conn.rollback()


def create_pending(cursor, name):
    cursor.execute("INSERT INTO public.applications(id,payload_json,tracking_token_hash) VALUES (%s,%s::jsonb,%s)",
                   (name, '{"gstin":"' + GSTIN + '"}', 'a'*64))
    manifest = []
    for doc_type, marker in (('GST','a'), ('BANK','b')):
        file_id = str(uuid.uuid4())
        path = f'{name}/{doc_type}/v1-synthetic.pdf'
        cursor.execute("""INSERT INTO public.documents
            (id, application_id, doc_type, storage_path, file_sha256, version, filename)
            VALUES (%s::uuid,%s,%s,%s,%s,1,%s)""",
            (file_id,name,doc_type,path,marker*64, f'{doc_type.lower()}.pdf'))
        manifest.append({'id':file_id, 'doc_type':doc_type, 'version':1,
                         'file_sha256':marker*64, 'storage_path':path})
    import json
    cursor.execute("""
        INSERT INTO public.runs
        (id,application_id,trigger,status,payload_json,stages_json,
         extracted_json,checks_json,reasons_json,all_reasons_json,
         next_action,started_at,finished_at,elapsed_ms,expected_revision,document_manifest)
        VALUES (%s,%s,'submission','PENDING',%s::jsonb,'[]','{}','[]','[]','[]',
                'Synthetic test',now(),now(),0,0,%s::jsonb)
        """, ('RUN-'+name,name,'{"gstin":"'+GSTIN+'"}',json.dumps(manifest)))


def approval(cursor, name):
    cursor.execute("""INSERT INTO public.review_actions
        (application_id,action,reason,actor,reviewed_run_id,expected_revision)
        VALUES(%s,'APPROVE','Synthetic concurrent approval test','s62-probe',%s,1)""",
        (name,'RUN-'+name))
    cursor.execute("SELECT current_status,revision FROM public.applications WHERE id=%s", (name,))
    return cursor.fetchone()


def main():
    print('VendorFlow v1.1 / Stage 6.2 — staging-only PostgreSQL concurrency gate')
    if input('Type vendorflow-v11-staging to confirm project: ').strip() != 'vendorflow-v11-staging':
        raise SystemExit('Cancelled. Project confirmation failed.')
    template = getpass('Paste staging Session pooler URI template, with [YOUR-PASSWORD] (hidden): ')
    parsed = urlsplit(template.replace('[YOUR-PASSWORD]', 'TEMPLATE'))
    if not (parsed.scheme in ('postgres', 'postgresql') and
            (parsed.hostname or '').endswith('.pooler.supabase.com') and
            unquote(parsed.username or '').endswith('.'+REF) and
            parsed.port == 5432 and parsed.path == '/postgres' and
            parsed.password in (None,'TEMPLATE','YOUR-PASSWORD')):
        raise SystemExit('Cancelled: the URI does not identify the staging Session pooler.')
    password = getpass('Enter STAGING database password (hidden): ')
    if not password:
        raise SystemExit('Cancelled: password missing.')
    credentials = dict(host=parsed.hostname, port=5432,
                       user=unquote(parsed.username), dbname='postgres',password=password)
    preflight(credentials)
    print('Preflight: staging empty; Stage 6.2 schema and uniqueness index present.')
    lock_open = threading.Event()
    second_finished = threading.Event()
    outcomes = ['NOT_RUN','NOT_RUN']
    run_tag = uuid.uuid4().hex[:10].upper()

    def first():
        conn = None
        try:
            conn = open_connection(credentials)
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='3s'")
                app = 'VF-S62-A-'+run_tag
                create_pending(cur,app)
                status, revision = approval(cur,app)
                outcomes[0] = 'APPROVED_HELD_UNCOMMITTED' if status=='APPROVED' and revision==2 else 'UNEXPECTED_'+status
                lock_open.set()  # Keep uncommitted unique-index entry visible to second transaction's conflict check.
                second_finished.wait(7)
        except Exception as error:
            outcomes[0] = 'ERROR_'+type(error).__name__
            lock_open.set()
        finally:
            if conn:
                conn.rollback()
                conn.close()

    def second():
        conn = None
        try:
            conn = open_connection(credentials)
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout='2s'")
                cur.execute("SET LOCAL statement_timeout='5s'")
                app = 'VF-S62-B-'+run_tag
                create_pending(cur,app)
                if not lock_open.wait(6):
                    outcomes[1] = 'SYNC_TIMEOUT'
                    return
                try:
                    status, revision = approval(cur,app)
                    outcomes[1] = 'UNSAFE_APPROVED' if status=='APPROVED' else 'UNEXPECTED_'+status
                except psycopg.Error as exc:
                    outcomes[1] = 'BLOCKED_'+str(exc.sqlstate or 'UNKNOWN')
        except Exception as error:
            outcomes[1] = 'ERROR_'+type(error).__name__
        finally:
            second_finished.set()
            if conn:
                conn.rollback()
                conn.close()

    worker1=threading.Thread(target=first)
    worker2=threading.Thread(target=second)
    worker1.start();worker2.start()
    worker1.join(14);worker2.join(14)
    print('Worker 1:',outcomes[0])
    print('Worker 2:',outcomes[1])
    if worker1.is_alive() or worker2.is_alive():
        raise SystemExit('INCONCLUSIVE: worker thread did not finish')
    preflight(credentials)
    print('CLEAN: all four staging tables have 0 records; worker transactions rolled back.')
    if outcomes[0]=='APPROVED_HELD_UNCOMMITTED' and outcomes[1]=='BLOCKED_55P03':
        print('PASS: approved-GSTIN unique index blocks concurrent competing manual approval.')
    else:
        raise SystemExit('INCONCLUSIVE/FAIL: do not close Stage 6.2 without reviewing outputs.')

if __name__=='__main__':
    main()
