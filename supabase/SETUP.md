# Stage 3.3 — Supabase manual checkpoints

Do **one checkpoint at a time** with the user; they should not paste credentials into ChatGPT.

1. **Create the Supabase project:** Dashboard → New project → organisation,
   `vendorflow-ai-demo`, choose a region near India, set a strong database password and
   securely save it, create project. Confirm project dashboard opens. No credentials needed in chat.
2. **Install schema:** SQL Editor → New query → paste and run all `supabase/schema.sql`.
   Then Table Editor shows `applications`, `documents`, `runs`, `review_actions`;
   Storage shows private `vendor-documents` bucket. Never make bucket public.
3. **Configure local secret:** Project Settings / Connect → project URL, API Keys →
   new server-only secret key (`sb_secret_...`, or legacy `service_role` key) into local `.env`.
   Do **not** paste the key into chat or GitHub. If downloaded, the ZIP will not contain `.env`.
4. **Install new dependencies and live smoke test:** `pip install -r requirements.txt`,
   `pytest -q`, `python run_persisted.py --scenario happy`. Never paste tracking code in chat.
5. **Verify correction & manual review** using later UI; don't mark the stage complete
   until history survives a fresh session and server-side duplicate checks are live.

## Security limitations

All database access uses a server-only secret, behind the Streamlit process. The
Supabase tables have RLS enabled and grant no read/write permissions to `anon` or
`authenticated`. The service key bypasses RLS, so **never** call this adapter from
untrusted clients. This is demo security only; it is not production vendor identity
management. Only synthetic vendor documents/data are permitted.

## Persistence contract

- Four Postgres tables; only `runs` stores full immutable workflow snapshots.
- SQL triggers atomically update current application status when runs or admin
  decisions are inserted. The separate Storage upload is not transactional with SQL;
  upload failure prevents any successful decision claim and may leave an unreferenced
  private object if a metadata insert fails.
- Vendor tracking secret is randomly generated; only its SHA-256 digest is stored.
- `APPROVED` is a sample document-consistency result, **not official verification**.
