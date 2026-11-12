# VendorFlow AI v1.1 — Stage 6.4 Gemini reliability / PDF handling

**Status:** implementation + offline verification complete; developer staging API smoke and branch commit pending. **No merge, migration or production deployment.**

## Scope and decisions

1. **Single bounded retry owner.** `GeminiExtractor` retries a total of **at most three** `generate_content` calls, with exponential waits of roughly 1 and 2 seconds plus small jitter. Its own newly created Google GenAI client has `HttpRetryOptions(attempts=1)` to prevent multiplying these retries. The HTTP request timeout is 18 seconds; the nominal budget is 60 seconds. Python cannot forcibly interrupt an injected client that ignores a timeout.
2. **Only transient failure retries.** HTTP `408`, `429`, and `5xx`, plus typed `httpx` network and timeout failures, are retried; 400/401/403/404, malformed/empty JSON, schema-invalid responses, unexpected exceptions, and missing SDK/credentials are not. A numeric `Retry-After` larger than 4 seconds ends the attempt immediately rather than retrying too early. No fallback model is configured because that may amplify shared quota/credential problems and needs separate fixture evaluation.
3. **Sanitized diagnostics.** Persisted `S3` stage events include category, safe model label, attempts, and elapsed milliseconds on success/failure. Provider raw messages, document strings, secret keys, account numbers and tracking codes are **never placed in diagnostic notes**. Failed extraction still produces `PENDING` through rule `R14`, not approval or automatic rejection.
4. **Document limits.** Enforce PDF file size before parsing; keep 5 MB / 10-page limits and add a 24,000-character extracted-text limit per PDF (oversized text becomes unreadable and Pending Review; never fed to Gemini). Password-protected, image-only, malformed or absent PDFs remain review-bound.
5. **Reversed uploads.** A conservative cross-heading **and** field-label check only flags PDF swaps when a bank-confirmation heading + account number appear in the GST upload **and** a GST-registration heading + GSTIN appear in the bank upload. Flagging makes document check `R02` fail with a clear vendor action, skips unnecessary Gemini calls, and cannot approve. Ambiguous/mixed documents receive normal deterministic rule checks; there is no authenticity claim.
6. **Prompt boundary.** Both extracted PDF texts are serialized as JSON strings separately from extraction instructions; unchanged deterministic source grounding independently guards against hallucinated values.

## Offline evidence

- Full suite on the Stage 6.3 + hotfix baseline: `PYTHONPATH=. python -m pytest -q` → **128 passed** (101 prior + 27 new Stage 6.4 cases).
- New fault injection covers 429/503/408/500 transient retries; permanent 400/401/403/404 stop; invalid/empty outputs; typed transport failures; unknown exception privacy; bounded retry count and `Retry-After`; SDK retry configuration; absent-doc hallucination; safe diagnostics; overlong-text PDF; swapped/normal/scanned PDFs.
- `python -m compileall -q app.py vendorflow tests scripts` → no syntax errors.
- All tests are offline mocks, **not live Gemini requests**.

## Acceptance gate on Ubuntu (staging-only)

1. In `~/Downloads/vendorflow-stage61-branch`, check `git status --short` and branch (`stage6-v1.1-remediation`). Keep `.env` private and confirm it points to `https://hkxalnpnchzheorrogci.supabase.co`, not production. No database migration.
2. Apply the Stage 6.4 patch only. Run `PYTHONPATH=. python -m pytest -q` → **128 passed**. Optionally inspect `git diff --check` and changed files.
3. With the existing staging-only `.env` and synthetic fixture files, run `python scripts/stage6_4_live_gemini_smoke.py`. This invokes the actual Gemini model once (unless a transient error causes up to 2 retries) to extract the synthetic sample documents. It validates grounding of six critical document fields but prints no private fields. **Expected:** `LIVE GEMINI EXTRACTION: PASS` and a sanitized summary. `CLEAN` means there were **no Supabase DB/Storage operations**; it doesn't claim to test application save or outage recovery.
4. Confirm the Streamlit vendor flow remains usable using fake data and that an unreadable PDF routes `PENDING`. Test the exact staged production keys only locally; never share them. Live reproduction of 429/503 is intentionally **not induced**; mocks cover bounded retry classification.
5. Commit changed files to `stage6-v1.1-remediation` only. Verify GitHub `main` unchanged. **Do not merge/redeploy until Stage 6.5.**

## Known limitations / future

- Real Gemini API quotas/model availability and occasional schema compliance can vary. A single smoke success does not establish statistical uptime or rate-limit recovery in production.
- The synchronous HTTP timeout is per attempt; the 60-second budget is checked **between attempts**. Actual hung third-party clients that violate SDK timeout are not forcibly killed.
- PDF text extraction is not OCR or document forgery detection. If documents are scanned, vendor must provide readable evidence or request manual review.
- No admin-initiated retry, API model fallback, user-triggered retry rate limit, or production-level IAM added here. Those require a separate product/security design, not a cosmetic hotfix.
- Preserve legacy immutable document manifests and database revision locks from Stages 6.1/6.2; Stage 6.4 makes no schema changes.

## Expected changed/new files

- `vendorflow/gemini_extractor.py`
- `vendorflow/pdf_reader.py`
- `vendorflow/pipeline.py`
- `vendorflow/rules.py`
- `tests/test_stage6_4_gemini_resilience.py` (new)
- `scripts/stage6_4_live_gemini_smoke.py` (new)
- `README.md`, `PROGRESS.md`, `STAGE6_4_HANDOFF.md` (new)

**After this stage passes:** return to Product Management chat for Claude's comprehensive SaaS design refinement before Stage 6.5. No changes to UI colours/design or model fallback are in this stage.
