# VendorFlow AI v2 — Stage 2: Product Thinking and Workflow

**Status:** Approved by product owner, 13 Nov 2026
**Builds on:** `v2/V2_01_Problem_and_Scope.md` (approved)
**Not covered here:** visual design (Stage 3) and code changes (Stage 4). Effort estimates are unverified until Claude Code reports what already exists.

---

## 1. Who uses it

| Role | Real-life person | Job to be done | Success for them |
|---|---|---|---|
| **Vendor** | Owner or accountant of a small Indian business, invited by a buyer; often on a phone | "Get set up as a supplier once, quickly, so I can get paid." | Finished in one sitting; knows the status; never asked the same thing twice |
| **Reviewer** | AP or procurement analyst at the buyer company | "Only look at cases that need me, decide confidently, and have proof later." | Clean cases never reach them; each exception decided in one screen |

The reviewer also sends vendor invites. A separate "requester" role is out of scope.

---

## 2. Vendor psychology → design response

| What the vendor feels | Design response |
|---|---|
| "Is this genuine? Should I share bank details?" | The invite page names the buyer and who invited them, says why bank details are needed, and says documents are stored privately. No account creation. |
| "How long will this take? What do I need?" | Checklist up front (GST certificate, cancelled cheque or bank letter, Udyam certificate if MSME) and a time estimate, about 5 minutes (a design target, not a measurement) |
| "I don't want to type all this." | Upload first; we fill in the details |
| "Did it read my documents correctly?" | A confirm screen showing every value with its source ("from your GST certificate") |
| "Am I being judged?" | Neutral wording. Never say "fraud", "duplicate" or "suspicious" to the vendor. Pending is presented as a normal step. |
| "What happens now?" | Every result says the status, **who acts next**, and exactly what is needed |
| "Do I have to start again to fix one thing?" | Everything is kept. Only the flagged items are shown, then re-checked immediately. |
| "I'm on my phone." | Camera or photo upload works; one column; large buttons |

---

## 3. Reviewer psychology → design response

| What the reviewer feels | Design response |
|---|---|
| "Don't waste my time." | The default queue shows only cases **with our team**, sorted by risk then age, with a one-line reason per row |
| "I'm accountable if fraud gets through." | Evidence side by side, a document viewer, links to matching records, and a full audit trail. Approving an unresolved duplicate or bank-reuse case needs a structured confirmation. |
| "Can I trust the automation?" | Every automated decision, including approvals, shows each check and its evidence |
| "I don't want to chase vendors." | Requesting a correction sends the vendor message automatically. The case moves to "waiting on vendor" and leaves the reviewer's queue. |
| "I need to show this works." | A dashboard of real run data, labelled synthetic |

---

## 4. Prioritisation

Each item is scored on fit with the brief, demo value and effort (effort unverified).

| Rank | Item | PS-2 names it? | Demo value | Effort |
|---|---|---|---|---|
| 1 | "Waiting on you / with our team" split plus correct vendor reasons | Yes ("communicate back what's needed") | High | Low |
| 2 | Upload first → auto-fill → confirm | Indirectly (removes manual work) | Very high | High |
| 3 | Wrong or swapped document detection | Yes ("attach the wrong documents") | High | Low–Med |
| 4 | Reviewer evidence (document viewer, linked matching record) | Yes (review is manual today) | High | Med |
| 5 | Vendor message plus message log | Yes ("track down the vendor… and wait") | High | Low–Med |
| 6 | Duplicates across all statuses; bank reuse across GSTINs | Yes (fraud) | High | Low |
| 7 | Scans and photos via Gemini image input | Indirectly (messy real documents) | Med–High | Med |
| 8 | MSME (Udyam) capture | No (India credibility) | Med | Med |
| 9 | Invite link instead of tracking code | Indirectly | Med | Med |
| 10 | "Pvt Ltd" = "Private Limited" normalisation | Yes (name ≠ bank-name false alarms) | Low–Med | Low |

**If time runs short, drop in this order:** 10 → 9 → 8 (explain it in the demo instead of building it). Never drop 1–6.

---

## 5. End-to-end workflow

```
REVIEWER                               VENDOR
Invite vendor ──── link (copied) ────▶ Welcome + checklist
                                        │
                                       1 Documents: upload GST cert, bank proof,
                                         MSME yes/no (+ Udyam cert)
                                         └▶ live "Reading" stages
                                        │
                                       2 Details: confirm pre-filled values,
                                         fix gaps, add contact, declaration
                                        │
                                       3 Submit ─▶ live "Checking" stages
                                        │
                                       Result: Approved / Pending (owner) / Rejected
                                        │
            ┌───────── Pending, with our team ─────────┤
            ▼                                          │ Pending, waiting on vendor
Queue → Case → Decide                                  ▼
  ├ Approve (reason) ─────────────▶ Approved       Application page: to-do list
  ├ Reject (reason) ──────────────▶ Rejected        → fix items → re-check
  └ Request correction ─ message ─▶ waiting on vendor ─┘
Every step is written to the audit timeline and the message log.
```

**Live run view in two parts:**
- **Reading** (happens on upload): Received → Identified document types → Read details
- **Checking** (happens on submit): Checked formats → Compared documents → Checked our records → Decided → Saved and vendor notified

The admin case timeline shows both parts as one run history. How extraction results are stored between upload and submit is decided in Stage 4.

---

## 6. Status and ownership model

| Internal state | Vendor sees | In reviewer queue? |
|---|---|---|
| Invited | "Start your application" | No (invites list) |
| Draft | "Continue your application" | No |
| Checking | Live stages | No |
| Approved | "Approved" + MSME tag if any | No |
| Pending — waiting on vendor | "Action needed from you" + to-do list | "Waiting on vendor" tab only |
| Pending — with our team | "With our team. No action needed." | **Yes, default tab** |
| Rejected | "Not approved" + reviewer's reason | No |

**Ownership rule**
1. Any vendor-fixable failure (missing, unreadable, wrong or swapped document; format; MSME mismatch) → **waiting on vendor**. Only the vendor's items are shown.
2. Otherwise, any reviewer-owned flag (name ≠ bank holder, edited value, duplicate, bank reuse, extraction outage) → **with our team**.
3. Otherwise → **Approved**.

When a case has both kinds, the vendor fixes their part first, and the re-check then routes it to the team.

**Final states:** Approved and Rejected. Reviewer decisions always need a written reason.

---

## 7. Vendor screens

| # | Screen | Purpose | Key content | Primary action |
|---|---|---|---|---|
| V1 | Welcome (from invite link) | Build trust, set expectations | Buyer name, inviter, checklist, ~5 min, privacy line | **Start** |
| V2 | Step 1 — Documents | Collect evidence | Three upload slots (GST, bank proof, Udyam shown only if MSME = Yes); camera allowed; inline "Reading…" stages per file; wrong-type warning on the slot | **Continue** |
| V3 | Step 2 — Details | Confirm, not type | Pre-filled values with source labels; edited values marked "you changed this, our team will compare it with your document"; empty fields marked "not found on your document"; contact name, email and phone (email pre-filled from invite); account number masked | **Continue** |
| V4 | Step 3 — Review and submit | Last check | Compact summary; declaration "These details are correct and belong to my business" | **Submit for checking** |
| V5 | Live check | Show real processing | Checking stages as they happen | (none, automatic) |
| V6 | Result | Clear outcome | Status, who acts next, up to 3 items, what happens next | Depends: **Fix items** / **Done** |
| V7 | Application page (return via link) | Single home | Status, to-do list, messages from the team, history | **Fix items** if waiting on vendor |
| V8 | Fix items | Minimal correction | Only the flagged fields and documents | **Re-check** |

**Rules**
- One primary button per screen.
- No rule IDs, PASS/FAIL tokens or technical captions on vendor screens.
- Times shown in IST.

---

## 8. Reviewer screens

| # | Screen | Key content | Main actions |
|---|---|---|---|
| R1 | Overview (dashboard) | Needs review; waiting on vendors; straight-through rate; median check time; top reasons; oldest case age; recent runs | Open queue |
| R2 | Applications (queue) | Tabs: **Needs review** (default), Waiting on vendor, Approved, Rejected, All. Columns: vendor, main reason, risk tag, age, MSME tag | Open case (one click) |
| R3 | Case | Header (status, owner, age, MSME tag); checks with evidence; values compared side by side; document viewer; linked records (matching GSTIN or bank account); timeline (runs, messages, actions) | Approve / Request correction / Reject |
| R4 | Decision dialog | Reason box; vendor message preview. Duplicate or bank-reuse approval needs a structured confirmation: "Bank change confirmed by call-back to the contact on the existing record." | Confirm |
| R5 | Invite vendor | Company name, contact name, email → link with copy button | Create invite |
| R6 | Activity | Every run across all vendors: time, vendor, trigger, result, duration | Open run |

---

## 9. Message templates

| Situation | Vendor message (core text) |
|---|---|
| Waiting on vendor | "We need a few things before we can continue: [items]. Open your application to fix them: [link]" |
| With our team | "Thanks, your application is with our team for a final check. No action is needed from you. We'll message you here." |
| Correction requested | "Our team needs one change: [reviewer note]. Open your application: [link]" |
| Approved | "Your business is approved as a supplier to [Buyer]." (+ "Registered MSME: payment terms within 45 days apply" if Micro/Small) |
| Rejected | "We couldn't approve your application: [reviewer reason]. Questions: [contact]" |

All messages are stored in the message log. Real email is optional and goes to the owner's address only.

---

## 10. Demo cases (final pick)

| Case | Input (all SAMPLE) | Expected result | What it proves |
|---|---|---|---|
| **Happy path** | GST certificate PDF + **photo** of a cancelled cheque + Udyam (Micro, Services) | Approved straight through; "MSME — pay within 45 days" tag | AI reads messy documents; nothing typed; India-specific output |
| **EC1: Swapped documents** | Bank proof in the GST slot and vice versa | Waiting on vendor: "The files look swapped." Vendor fixes → re-check → Approved | Wrong-document handling plus the full correction loop |
| **EC2: Name ≠ bank holder** | GST legal name "SAMPLE Traders Pvt Ltd"; bank account in the proprietor's personal name | With our team; reviewer opens both documents → Request correction | Judgment instead of blind matching; reviewer evidence |
| **EC3: Payment diversion** | GSTIN of an approved vendor with a **new** bank account | With our team; vendor sees neutral text; reviewer sees linked record; approve blocked without confirmation → **Reject** | Fraud control; shows a Rejected outcome |
| **EC4: MSME mismatch** | Udyam certificate state or name doesn't match the GST certificate | Waiting on vendor with exact item | Subtle cross-document inconsistency |

**Backup EC4:** the vendor edits the extracted account number → With our team, both values shown.

---

## 11. Dashboard metrics (all from real run data, labelled synthetic)

- Straight-through rate: first submissions auto-approved ÷ first submissions
- Pending split by owner (vendor / team)
- Top 5 reasons
- Median automated check time (runs with documents only)
- Oldest case waiting on the team
- MSME vendors (Micro/Small) count

---

## 12. Deliberately not important

- Vendor accounts, passwords or profiles
- Real GST, penny-drop or Udyam API calls (named as "what production adds")
- Multiple reviewers, roles or assignment
- Editing approved vendors or re-verifying them later
- Charts beyond the metrics above; animations; dark mode; AI chat
- Address matching between documents (address formats vary too much; low value)

---

## 13. Product-owner decisions (approved 13 Nov 2026)

1. **Invite-based entry: yes.**
   - The reviewer creates an invite (company, contact, email).
   - The system generates a unique link with a random token; only its hash is stored. The link expires and can be resent or revoked.
   - The same link is the vendor's way back, replacing the tracking code.
   - Demo delivery is a "Copy link" button plus a message-log entry marked as not delivered. Real email to the owner's own address is optional.
   - In production, the link is emailed automatically.
2. **Declaration checkbox on V4: yes.**
3. **EC4: MSME mismatch.** The edited account number remains the backup case.
