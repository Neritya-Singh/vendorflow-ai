# VendorFlow AI v1.1 — Stage 6.2 handoff

**Scope:** staging-only database revision locking, immutable document provenance, recoverable receipt and retry. No production changes.

## Verified in development

- **82/82** offline tests passed on the Stage 6.1 baseline + 17 new Stage 6.2 tests. Original tests are included.
- All four previously RED H04/H06 tests now pass.
- Stage 6.2 additive migration applied to **vendorflow-v11-staging** (`hkxalnpnchzheorrogci`), and the revision, manifest, reviewer linkage and immutable-PDF trigger were found through read-only SQL.
- Four staging application tables remain empty.

## What changed

1. **Revision CAS:** `applications.revision` monotonically increments on saved runs and review actions. Both trigger functions lock the application row with `FOR UPDATE` and compare `expected_revision`, returning errors rather than overwriting changes.
2. **Reviewer grounding:** audit row binds `reviewed_run_id` + revision; Streamlit saves the version displayed. Stale reviewer actions are denied.
3. **Provenance:** each run records a `document_manifest` with document UUID, type, version, SHA-256 and storage path. Database trigger checks that each reference belongs to the application and matches the metadata. Historical versions remain immutable. Actual Storage downloads additionally check SHA-256.
4. **No uncommitted PDF reuse:** corrections read only the latest **committed run's manifest**, not the latest metadata upload. Failed upload metadata writes are compensated with best-effort object removal.
5. **Initial recovery:** Streamlit issues and displays recovery ID + private code **before writing to Supabase**; `PreparedIntake` enables idempotent retried first submissions. An interrupted application with zero runs has an authenticated resume form. Lost commit acknowledgement recovers the exact committed run.
6. **Correction retry:** on lost acknowledgement, service returns the exact committed result only if the run IDs agree, avoiding accidental reuse of a competitor's revision.

## Test instructions (manual staging gates)

1. Extract the downloadable ZIP. Open `supabase/stage6_2_sql_smoke_rollback.sql` and run it as a single query in Supabase **vendorflow-v11-staging** SQL Editor. **Expected:** `S62_01` through `S62_13` all `PASS`, and `remaining_test_rows = 0` for every row. If `TEST_ERROR`, stop and share sanitized error. The script inserts synthetic *metadata only* and rolls it all back.
2. Activate a Python venv and install `psycopg[binary]`. Run `python scripts/stage6_2_concurrency_gate.py`. Enter **only** staging Session Pooler URI *template* and staging database password **privately in terminal**. **Expected:** `Worker 1: APPROVED_HELD_UNCOMMITTED`, `Worker 2: BLOCKED_55P03`, `CLEAN` with zero records. Workers roll back both transactions.
3. Confirm SQL results and Python output before marking Stage 6.2 fully complete or pushing changes to the development GitHub branch. The SQL test covers 13 scenarios; the real concurrency script covers a competing manual-approval race, not a same-application revision race.

## Known boundaries and future release checks

- No production Supabase migrations or main branch commits before Stage 6.5.
- In the SQL integration test, synthetic document **metadata** is used; this does not test real Supabase Storage API upload or network interruption. The Python offline suite injects failures in upload, metadata save, commit and acknowledgments. **A separate staging end-to-end upload test remains necessary for full release confidence.**
- Historical production runs lack document manifests. When production is later migrated, never infer exact PDF provenance from upload dates. Require a verified backfill or explicitly require re-upload/review for legacy cases.
- Security remains a demo: server-secret Supabase access + password-protected admin; not a production IAM system.
- Never send database passwords, secret keys, live user documents or full connection URLs to ChatGPT or GitHub.
