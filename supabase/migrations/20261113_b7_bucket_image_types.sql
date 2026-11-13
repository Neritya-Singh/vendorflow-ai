-- v2 B7: allow phone photos (JPG/PNG) in the private document bucket.
-- STAGING ONLY. Written for the NEW staging project, NOT YET APPLIED anywhere.
-- Never apply to the live v1.1 project (hkxalnpnchzheorrogci) or production.
--
-- Scanned PDFs need no change (still application/pdf). The bucket stays private
-- and keeps its 5 MB limit; only the allowed MIME types grow. The app re-checks
-- type by file extension AND magic bytes before storing (vendorflow/v2_scan.py).
BEGIN;

UPDATE storage.buckets
   SET allowed_mime_types = ARRAY['application/pdf', 'image/jpeg', 'image/png']::text[],
       public = false,
       file_size_limit = 5242880
 WHERE id = 'vendor-documents';

DO $check$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM storage.buckets
     WHERE id = 'vendor-documents' AND public = false AND file_size_limit = 5242880
       AND allowed_mime_types @> ARRAY['application/pdf', 'image/jpeg', 'image/png']::text[]
  ) THEN
    RAISE EXCEPTION 'vendor-documents bucket missing or not updated';
  END IF;
END
$check$;

COMMIT;

-- Rollback (PDF only again; run only if no image documents were stored):
-- UPDATE storage.buckets SET allowed_mime_types = ARRAY['application/pdf']::text[]
--  WHERE id = 'vendor-documents';
