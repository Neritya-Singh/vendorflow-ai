# VendorFlow AI v2 — Stage 3: UI/UX Direction

**Status:** Draft for product-owner approval, 13 Nov 2026
**Builds on:** `V2_01_Problem_and_Scope.md`, `V2_02_Product_and_Workflow.md` (both approved)
**Not covered here:** which UI library Claude Code already uses. That is checked in Stage 4; this document sets the direction, not the code.

---

## 1. What kind of product this is

VendorFlow is a **B2B SaaS product with two surfaces**. Each surface needs a different design.

| | Vendor portal | Reviewer console |
|---|---|---|
| Who | External small-business owner, first and only visit | Internal analyst, uses it every day |
| Device | Phone or laptop; mobile-first | Desktop (≥1280px); usable at 1024px |
| Feel | Simple guided flow, consumer-grade | Fast operations tool, like an inbox |
| Density | Comfortable, large tap targets | Compact tables, more information per screen |
| Branding | **Co-branded:** the buyer's name first, "Powered by VendorFlow" small | VendorFlow product brand |
| Speed lever | Fewer things to type and fewer decisions | Fewer clicks and less hunting for evidence |

**Reference model:**
- **Vendor portal:** Stripe-hosted onboarding (co-branded form; pre-filled data that the user confirms).
- **Reviewer console:** document-review tools (queue + document viewer + decision panel side by side, keyboard navigation).

**Anti-model:** a generic "AI dashboard" (gradients, sparkle icons, chat bubbles, "AI-powered" badges, decorative charts).

---

## 2. Design principles

1. **Speed is the yardstick.** PS-2's pain is manual review, manual follow-up and waiting. Every screen should cut typing, clicks or waiting.
2. **One job per screen, one primary button.**
3. **Show, don't ask.** Pre-fill from documents and from the invite.
4. **Say who acts next,** everywhere.
5. **Evidence next to the decision.** The reviewer never leaves the case to find proof.
6. **Honest UI.** Progress shows real stages only, with no fake percentages. The words "verified" or "KYC" are never used. AI is mentioned only where it does something ("Read from your GST certificate").
7. **Accessible by default.** WCAG 2.2 AA, text with every colour, visible focus, full keyboard use.

---

## 3. Speed targets (design targets; measured in Stage 5)

| User | Target |
|---|---|
| Vendor | 3 steps · ≤4 typed inputs (contact name, phone, MSME yes/no, declaration) · under 5 minutes with documents ready |
| Reviewer | Case opens in 1 click · decision in ≤3 interactions (choose action → pick or edit reason → confirm) · auto-advance to the next case |
| Reviewer | Can tell why every queued case is there without opening it |

---

## 4. Vendor portal

### 4.1 Layout
- **Laptop:**
  - Fit-to-screen, with no page scroll.
  - A header card (workspace name, step pills, "Powered by VendorFlow").
  - Content as rounded cards: the form card plus helper cards.
  - Fields inside each card stay in one column.
- **Phone:**
  - One column of cards with a step bar and a large bottom button.
  - Step 1 fits one screen. Step 2 (details) scrolls, with the Continue button kept visible, because forcing ~10 fields onto a phone screen would mean tiny text.
- Footer: one privacy line ("Your documents are stored privately and seen only by [Buyer]'s finance team").
- No sidebar, no navigation menu, no login.

### 4.2 Form rules
- Single column; labels above fields; never use placeholder text as a label.
- Validate a field when the user leaves it, not only on submit.
- Mark optional fields "(optional)". Everything else is required.
- Autosave the draft; the same invite link resumes it.
- Each step is one "thing": documents, then details, then submit.

### 4.3 Key screens

**V2 — Documents**
```
Zamp AI · Demo workspace                            Step 1 of 3
Upload your documents
We'll read the details for you, so there's no typing.

┌ GST registration certificate ───────────────────────┐
│ ✓ gst-cert.pdf · Read: GSTIN, legal name, state      │
└─────────────────────────────────────────────────────┘
┌ Cancelled cheque or bank letter ────────────────────┐
│ ⟳ Reading cheque.jpg…                                │
└─────────────────────────────────────────────────────┘
Is your business registered under Udyam (MSME)?  ( ) Yes  ( ) No
┌ Udyam certificate  (appears if Yes) ────────────────┐
│ Drop file or [Take photo]   PDF, JPG, PNG · max 5 MB │
└─────────────────────────────────────────────────────┘
                                          [Continue →]
```
- Reading starts as soon as each file is dropped, so the vendor uploads the next file while the first is read.
- Wrong-type warning appears on the slot itself: "This looks like a bank document. Did you mean to put it in the bank slot? [Move it]".

**V3 — Details (confirm, don't type)**
```
Check your details
From your GST certificate                         [Edit]
  Legal name     SAMPLE Traders Private Limited
  GSTIN          09ABCDE1234F1Z5   PAN ABCDE1234F (from GSTIN)
  State          Uttar Pradesh
From your bank document                           [Edit]
  Account holder SAMPLE Traders Private Limited
  Account no.    •••• •••• 4821   IFSC  SBIN0001234
⚠ Not found on your document: IFSC — enter it or upload a clearer copy
Your contact
  Name [________]   Phone [________]   Email  owner@sample.in (from invite)
                                          [Continue →]
```
- Edited values get a small tag: "Changed by you — our team will compare it with your document."

**V5/V6 — Live check, then result.** One vertical list of real stages with ticks and times; the result card replaces it in place.
```
✓ Approved
You're set up as a supplier to Zamp AI.
MSME (Micro): payment terms within 45 days apply.
                                   [Done]
```
```
⚠ Action needed from you  (2 items)
1. Your files look swapped. Put the GST certificate in the GST slot.   [Fix]
2. …
```
```
● With our team — no action needed
We'll message you here when there's an update.
```

**V7 — Application page:** status card at the top, then the to-do list (if any), messages, and history (collapsed).

### 4.4 Vendor copy rules
- Plain English, sentence case, verbs on buttons ("Upload", "Fix", "Submit for checking").
- Never say "fraud", "duplicate", "suspicious", "failed" or "rejected by AI".
- Dates as "13 Nov 2026, 3:04 pm IST". Account numbers masked to the last 4 digits.

---

## 5. Reviewer console

### 5.1 Layout
- **No sidebar.** The top bar holds the brand, tab navigation (**Overview · Applications · Invites · Activity**), search and an "Invite vendor" button.
- **Fit-to-screen app shell (approved 13 Nov):**
  - On laptop, every screen fits one viewport (about 1440×900, down to 1280×760) and the page itself never scrolls.
  - Long content (the table, the document viewer, the history list) scrolls only inside its own card.

### 5.2 Applications (queue)
```
Applications   [Needs review 4] [Waiting on vendor 3] [Approved] [Rejected] [All]
Vendor                 Main reason                     Risk     Age   MSME
SAMPLE Steelworks      Same GSTIN, new bank account    ● High   2d    —
SAMPLE Traders         Bank holder ≠ legal name        ● Med    1d    Micro
SAMPLE Logistics       Value edited by vendor          ● Med    3h    —
```
- Sorted by risk, then age. The whole row is clickable.
- Keyboard: **J/K** move, **Enter** opens.

### 5.3 Case page: a split view built for one decision
```
← Back   SAMPLE Steelworks · With our team · 2 days        [◀ Prev] [Next ▶]
┌ WHY IT'S HERE ───────────────────────┐┌ DOCUMENT VIEWER ─────────────────┐
│ Same GSTIN as approved vendor         ││ [GST cert] [Bank letter] [Udyam] │
│ VF-1042, with a different bank account││                                  │
│ → Open VF-1042                        ││     (PDF or image, zoom)         │
│ Compared values                       ││                                  │
│ Field     This app     VF-1042        ││                                  │
│ Account   ••••7730     ••••4821  ⚠    ││                                  │
│ IFSC      HDFC0…       SBIN0…    ⚠    ││                                  │
│ ✓ 11 other checks passed  [show]      ││                                  │
│ Timeline: runs · messages · actions ▸ ││                                  │
└───────────────────────────────────────┘└──────────────────────────────────┘
[ Approve (A) ]  [ Request correction (C) ]  [ Reject (R) ]     ? shortcuts
```
- **"Why it's here"** is written by the rules, not AI, in one or two sentences.
- Failed or flagged checks are open; passed checks are collapsed into one line.
- The action bar is always visible.

### 5.4 Decision dialogs
- **Request correction:** the vendor message is drafted automatically from the flagged items; the reviewer edits it and sends.
- **Reject / Approve:** quick-reason chips (for example "Bank account not owned by the business") plus a free-text box; reason required.
- **Approve on a duplicate or bank-reuse case:** an extra confirmation is required ("Bank change confirmed by call-back to the contact on the existing record").
- After any decision → toast "Decision saved · Vendor notified", then the **next case opens automatically**.

### 5.5 Overview (dashboard)
- One row of metric cards: Needs review · Waiting on vendors · Straight-through rate · Median check time · Oldest case.
- Below: "Top reasons" (a simple bar list) and "Recent runs" (table).
- Small label: "Synthetic test data."
- No other charts.

### 5.6 Activity
A table of every run (time, vendor, trigger, result, duration). Clicking a row opens the same live-stage timeline component used by the vendor, in admin wording.

---

## 6. Visual system

| Element | Decision |
|---|---|
| Theme | Light. White cards on a very light grey background. No dark mode. |
| Accent | One calm, finance-trustworthy accent (deep indigo/blue) for primary buttons and links only |
| Status colours (always with icon and text) | Approved = green ✓ · Action needed / Waiting on vendor = amber ⚠ · With our team = blue ● · Rejected = red ✕ · Invited / Draft = grey ○ |
| Risk tags (reviewer only) | High = red dot · Medium = amber dot |
| Type | Inter or the system UI font. Tabular figures for IDs, GSTINs and amounts. Vendor body 16px; reviewer tables 14px. |
| Style | Card-based ("bento") layout: rounded rectangles (16–20px radius), 1px light borders, no heavy shadows, 12–16px gaps |
| Spacing | 8px grid; vendor inputs ≥44px tall; reviewer table rows about 40px |
| Icons | One simple line-icon set; icons support text, never replace it |
| Motion | Only for the stage tick and the toast. Nothing decorative. |
| Empty states | One line + one action ("No cases need review. [Invite a vendor]") |

**Workspace branding (multi-tenant).** Each customer company is a workspace with its own display name and optional logo. The vendor portal shows the workspace name ("Zamp AI invited you…") with "Powered by VendorFlow" in small text.

- **Demo workspace:** **Zamp AI** (zamp.ai), shown as text only, with a "Demo workspace" label.
- No Zamp logo or brand colours, so the page cannot be mistaken for an official Zamp page.
- Not to be confused with the US sales-tax company "Zamp" (zamp.com).

---

## 7. Shared components (build once, use on both sides)
- Status badge (the six states)
- Stage timeline (live and historical)
- Document card (upload slot / viewer tab)
- Field row (label, value, source tag, edited tag, masked option)
- Message item

---

## 8. What we will not add
- Animations, illustrations, hero images, gradients
- Charts beyond §5.5
- Dark mode, themes, settings pages
- Tooltips as the only place important information lives
- Any "AI" branding beyond the "Read from your document" labels

---

## 9. Product-owner decisions (13 Nov 2026)
1. **Buyer name:** a per-workspace setting. The demo workspace is **Zamp AI**.
2. **Visual mockups** of the 4 key screens before Stage 4: **yes**. Made as the canvas "VendorFlow v2 — Key Screen Mockups" (6 artboards: vendor laptop ×2, vendor phone ×2, reviewer ×2).
3. **Layout:** no sidebar; fit-to-screen with no page scroll on laptop; card ("bento") style; phone details step may scroll.
