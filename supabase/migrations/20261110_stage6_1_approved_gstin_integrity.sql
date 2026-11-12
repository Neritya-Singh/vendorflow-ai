-- Applied to staging project hkxalnpnchzheorrogci on 2026-11-10.
-- DO NOT apply to production until the final controlled release.
DO $guard$
BEGIN
  IF (SELECT count(*) FROM public.applications) <> 0 THEN
    RAISE EXCEPTION 'Stage 6.1 staging-only migration expects empty applications table';
  END IF;
END
$guard$;
ALTER TABLE public.applications
  ALTER COLUMN gstin_normalized SET EXPRESSION AS
  (upper(regexp_replace(coalesce(payload_json->>'gstin',''), '[[:space:]]+', '', 'g')));
CREATE UNIQUE INDEX IF NOT EXISTS uq_vendorflow_approved_gstin
  ON public.applications (gstin_normalized) WHERE current_status='APPROVED';
ALTER TABLE public.applications ADD CONSTRAINT approved_gstin_valid_format
  CHECK (current_status <> 'APPROVED' OR gstin_normalized ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$');
ANALYZE public.applications;
