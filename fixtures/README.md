# Synthetic demo fixtures

All PDFs and identifiers here are invented for demo use. They are not government/bank documents and do not establish real identity.

Test scenarios: happy; ec1_pan_gstin; ec2_bank_owner; ec3_duplicate_changed_bank (must have a prior APPROVED GSTIN); ec4_missing_bank_holder.

B7 photo/scan cases (`scripts/create_photo_fixtures.py`, all marked SAMPLE): `photo_cheque` (clear phone-style
photo of a cancelled cheque -> Approved), `photo_blurry` (out of focus -> waiting on vendor; `cheque_photo_clear.jpg`
is the retake -> Approved), `scanned_letter` (image-only PDF bank letter -> Approved). Each photo carries its true
values in a JPEG comment that ONLY the offline Gemini test double reads; OCR grounding uses the real pixels.
