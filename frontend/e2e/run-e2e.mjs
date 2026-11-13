// Browser end-to-end checks for VendorFlow v2, driven through the real UI in Chrome.
//
// Requires running servers (see README_V2.md):
//   BASE_URL      offline or staging server (default http://127.0.0.1:8000)
//   OUTAGE_URL    server whose Gemini provider fails (offline mode + VENDORFLOW_OFFLINE_EXTRACTOR=gemini, no key)
//   ADMIN_PASSWORD_FILE  file containing the admin password (never printed)
//   UNREADABLE_PDF       path to a PDF with no text layer
// Prints PASS/FAIL per check and saves screenshots to e2e/artifacts/.
import { chromium } from "playwright-core";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const FIX = resolve(here, "../../fixtures");
const ART = resolve(here, "artifacts");
mkdirSync(ART, { recursive: true });
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8000";
const OUTAGE = process.env.OUTAGE_URL ?? "http://127.0.0.1:8001";
const PASSWORD = readFileSync(process.env.ADMIN_PASSWORD_FILE, "utf8").trim();
const UNREADABLE = process.env.UNREADABLE_PDF;
const CHROME = process.env.CHROME_PATH ?? "/usr/bin/google-chrome";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
  if (!ok) failures += 1;
};
const fixture = (name) => JSON.parse(readFileSync(`${FIX}/${name}/submission.json`, "utf8"));
const pdf = (name, kind) => `${FIX}/${name}/${kind === "gst" ? "gst_certificate" : "bank_confirmation"}.pdf`;
const shot = (page, name, fullPage = true) => page.screenshot({ path: `${ART}/${name}.png`, fullPage });

async function noHorizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
}

const FIELD_LABELS = { legal_name: "Legal name", gstin: "GSTIN", bank_holder: "Account holder", account_number: "Account number", ifsc: "IFSC" };

/** Wait until no upload slot is still reading; returns the slot states, e.g. ["read", "read"]. */
async function slotStates(page, files = 0) {
  await page.waitForFunction((n) => {
    const states = [...document.querySelectorAll("[data-slot-state]")].map((e) => e.getAttribute("data-slot-state"));
    return states.length === 2 && !states.includes("reading") && states.filter((x) => x !== "empty").length >= n;
  }, files, { timeout: 60_000 });
  return page.$$eval("[data-slot-state]", (els) => els.map((e) => e.getAttribute("data-slot-state")));
}

/** Upload-first flow (B5/B6): documents → details → submit → live check → result. */
async function startDocs(page, base, gstPath, bankPath) {
  await page.goto(`${base}/apply`);
  await page.locator('input[data-slot="GST"]').waitFor({ state: "attached" });
  const id = (await page.locator("code").nth(0).textContent()).trim();
  const code = (await page.locator("code").nth(1).textContent()).trim();
  // Both files go up at once; each slot reads independently.
  if (gstPath) await page.locator('input[data-slot="GST"]').setInputFiles(gstPath);
  if (bankPath) await page.locator('input[data-slot="BANK"]').setInputFiles(bankPath);
  return { id, code, states: await slotStates(page, [gstPath, bankPath].filter(Boolean).length) };
}

async function fillDetails(page, data, { typeAll = false, edit = {} } = {}) {
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("heading", { name: "Check your details" }).waitFor();
  if (typeAll) {
    for (const [key, label] of Object.entries(FIELD_LABELS)) {
      await page.getByLabel(label, { exact: true }).fill(data[key]);
      await page.getByLabel(label, { exact: true }).press("Tab");
    }
    await page.getByLabel("State", { exact: true }).selectOption({ label: data.business_state });
  }
  for (const [key, value] of Object.entries(edit)) {
    const card = key === "account_number" || key === "ifsc" || key === "bank_holder" ? "bank account" : "business";
    const field = page.getByLabel(FIELD_LABELS[key], { exact: true });
    if (!(await field.count())) await page.getByRole("button", { name: `Edit ${card}` }).click();
    await field.fill(value);
    await field.press("Tab");
  }
  await page.getByLabel("Contact name").fill(data.contact_name);
  await page.getByLabel("Phone").fill("+91 98765 43210");
  await page.getByLabel("Email").fill(data.contact_email);
  await page.getByLabel("Email").press("Tab");
}

async function submitDetails(page, label) {
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.getByRole("heading", { name: "Review and submit" }).waitFor();
  const submit = page.getByRole("button", { name: "Submit for checking" });
  check(`${label}: submit disabled until the declaration is ticked`, await submit.isDisabled());
  await page.getByRole("checkbox").check();
  await submit.click();
  await page.getByRole("heading", { name: "Your result" }).waitFor({ timeout: 90_000 });
  return outcome(page);
}

async function apply(page, base, data, gstPath, bankPath, label, opts = {}) {
  const started = await startDocs(page, base, gstPath, bankPath);
  if (label === "happy") await shot(page, "02-apply-documents");
  await fillDetails(page, data, opts);
  if (label === "happy") await shot(page, "03-apply-details");
  const decision = await submitDetails(page, label);
  return { ...started, decision };
}

/** "STATUS/OWNER" from the vendor decision card, e.g. "PENDING/TEAM". */
async function outcome(page) {
  const card = page.locator("[data-status]").first();
  await card.waitFor();
  return `${await card.getAttribute("data-status")}/${await card.getAttribute("data-owner")}`;
}

async function track(page, base, id, code) {
  await page.goto(`${base}/track`);
  await page.getByLabel("Application ID").fill(id);
  await page.getByLabel("Private tracking code").fill(code);
  await page.getByRole("button", { name: "Find application" }).click();
}

const browser = await chromium.launch({ executablePath: CHROME, headless: true });
try {
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  // Negative tests deliberately trigger 401/409 responses; only count script errors.
  page.on("console", (m) => m.type() === "error" && !m.text().startsWith("Failed to load resource") && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  // ------------------------------------------------------------ A. happy path
  await page.goto(BASE);
  await shot(page, "01-home");
  const happy = fixture("frontend_happy");
  const A = await apply(page, BASE, happy, pdf("frontend_happy", "gst"), pdf("frontend_happy", "bank"), "happy");
  check("A happy path → Approved", A.decision === "APPROVED/COMPLETE", A.decision);
  const stagesDone = await page.locator('ol[aria-label="Workflow stages"] > li').filter({ hasText: "Done ·" }).count();
  check("A receipt shows 9 completed server-timed stages", stagesDone === 9, `${stagesDone}`);
  await shot(page, "05-receipt-approved");
  const storage = await page.evaluate(() => JSON.stringify(localStorage) + JSON.stringify(sessionStorage));
  check("A tracking code never written to browser storage", !storage.includes(A.code));

  // ------------------------------------------------------------ B. bank-holder mismatch loop
  const ec2 = fixture("ec2_bank_owner");
  const B = await apply(page, BASE, ec2, pdf("ec2_bank_owner", "gst"), pdf("ec2_bank_owner", "bank"), "ec2");
  check("B bank-holder mismatch → Pending, with our team", B.decision === "PENDING/TEAM", B.decision);
  const bText = await page.locator("main").textContent();
  check("B no raw rule codes shown to vendor", !bText.match(/\bR1[0-4]\b|EXTRACTION_INCOMPLETE/));
  check("B vendor told no action is needed", bText.includes("No action is needed from you"));
  check("B vendor copy avoids fraud/duplicate/failed wording", !/fraud|duplicate|suspicious|failed/i.test(bText));
  await shot(page, "06-receipt-pending");
  await track(page, BASE, B.id, B.code);
  await page.getByText("With our team — no action needed").waitFor();
  check("B with-our-team case shows no edit form", (await page.getByRole("button", { name: "Re-check" }).count()) === 0);

  const admin = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const ap = await admin.newPage();
  await ap.goto(`${BASE}/admin`);
  await ap.getByLabel("Admin password").fill(PASSWORD);
  await ap.getByRole("button", { name: "Sign in" }).click();
  await ap.getByRole("heading", { name: "Applications" }).waitFor();
  await shot(ap, "07-admin-queue");
  const firstRow = await ap.locator("tbody tr").first().textContent();
  check("B 'Needs review' tab lists the team case with reason and risk", firstRow.includes(B.id)
    && firstRow.includes("Bank account holder differs from legal name") && firstRow.includes("Medium"), firstRow);
  await ap.getByRole("link", { name: ec2.legal_name }).first().click();
  await ap.getByRole("heading", { name: "Compared values" }).waitFor();
  const masked = await ap.locator("section", { hasText: "Compared values" }).locator("table").textContent();
  check("B admin comparison masks account number by default", !masked.includes(ec2.account_number) && masked.includes("•"));
  await shot(ap, "08-admin-case");
  // Keyboard: C opens the correction dialog with a message pre-drafted from the flagged items.
  await ap.keyboard.press("c");
  const dialog = ap.getByRole("dialog");
  await dialog.waitFor();
  const draft = await dialog.getByLabel("Message to the vendor").inputValue();
  check("B 'C' opens a pre-drafted correction request", draft.includes("as the account holder"), draft);
  await dialog.getByLabel("Message to the vendor").fill("Upload a bank letter showing the company's legal name as account holder.");
  check("B dialog previews the exact vendor message", (await dialog.textContent()).includes("Our team needs one change: Upload a bank letter"));
  await shot(ap, "09-admin-correction-dialog", false);
  await dialog.getByRole("button", { name: "Send request" }).click();
  await ap.getByText("Decision saved · Message added for vendor").waitFor();
  check("B correction saved with honest toast", true);
  await ap.waitForURL(/\/admin(\?.*)?$/);
  check("B auto-advances (no more cases needing review → back to the queue)", true);
  await ap.getByRole("tab", { name: /Waiting on vendor/ }).click();
  await ap.locator("tbody tr", { hasText: B.id }).waitFor({ timeout: 5_000 }).catch(() => {});
  const waiting = await ap.locator("tbody").textContent();
  check("'Waiting on vendor' tab lists the correction-requested case", waiting.includes(B.id) && waiting.includes("Correction requested"), waiting.slice(0, 200));

  await track(page, BASE, B.id, B.code);
  await page.getByText("Upload a bank letter showing the company's legal name").first().waitFor();
  check("B vendor sees reviewer message", true);
  check("B 'Action needed from you' is said once", (await page.getByText("Action needed from you", { exact: true }).count()) === 1);
  const log = await page.locator("section", { hasText: "Messages from our team" }).first().textContent();
  check("B vendor message log lists the correction and the earlier outcome", log.includes("Our team needs one change")
    && log.includes("with our team for a final check") && !/email sent/i.test(log));
  await shot(page, "10-track-correction-requested");
  await page.getByLabel("Account holder name").fill(ec2.legal_name);
  await page.locator('input[type="file"]').nth(1).setInputFiles(pdf("happy", "bank"));
  await page.getByRole("button", { name: "Re-check" }).click();
  await page.getByText("Your update was checked and saved").waitFor({ timeout: 90_000 });
  const afterB = await page.locator("main").textContent();
  check("B corrected application re-run → Approved", (await outcome(page)) === "APPROVED/COMPLETE");
  check("B history shows BANK v2 with original GST v1 kept", afterB.includes("Bank proof v2") && afterB.includes("GST certificate v1"));
  await shot(page, "11-track-after-correction");

  // ------------------------------------------------------------ terminal immutability
  check("H terminal application shows no correction form", (await page.getByRole("button", { name: "Re-check" }).count()) === 0);
  const resubmitStatus = await page.evaluate(async ([id, code]) => {
    const f = new FormData();
    Object.entries({ application_id: id, tracking_code: code, expected_revision: "3", expected_latest_run_id: "RUN-000000000000", legal_name: "X", contact_email: "a@b.co" })
      .forEach(([k, v]) => f.set(k, v));
    return (await fetch("/api/vendor/resubmit", { method: "POST", body: f })).status;
  }, [B.id, B.code]);
  check("H server refuses resubmission of a final application", resubmitStatus === 409, `${resubmitStatus}`);

  // ------------------------------------------------------------ I. payment diversion (EC3)
  // B is now approved; the same GSTIN arrives with a different bank account.
  const ec3 = fixture("ec3_duplicate_changed_bank");
  const I = await apply(page, BASE, ec3, pdf("ec3_duplicate_changed_bank", "gst"), pdf("ec3_duplicate_changed_bank", "bank"), "ec3");
  const iText = await page.locator("main").textContent();
  check("I same GSTIN + new bank → Pending, with our team", I.decision === "PENDING/TEAM", I.decision);
  check("I vendor sees only the neutral 'additional check' line", iText.includes("Our team is completing an additional check")
    && !iText.includes(B.id) && !/fraud|duplicate|suspicious/i.test(iText));
  await ap.goto(`${BASE}/admin`);
  await ap.locator("tbody tr").first().waitFor();
  const iRow = await ap.locator("tbody tr").first().textContent();
  check("I queue puts the high-risk case first with its reason", iRow.includes(I.id)
    && iRow.includes("Same GSTIN as an approved vendor, different bank account") && iRow.includes("High"), iRow);
  await ap.keyboard.press("/");
  check("'/' focuses queue search", await ap.evaluate(() => document.activeElement?.id === "admin-search"));
  await ap.keyboard.press("Escape");
  await ap.keyboard.press("k");
  await ap.keyboard.press("Enter");
  await ap.getByText("Linked record").waitFor();
  const linked = await ap.locator("section", { hasText: "Linked record" }).first().textContent();
  check("I case links the approved record and flags the differing account", linked.includes(`Open ${B.id}`)
    && /Account no\.[^A-Za-z]*Differs/.test(linked), linked.slice(0, 160));
  check("I linked comparison keeps account numbers masked", !linked.includes(ec3.account_number) && !linked.includes(ec2.account_number));
  const viewerImg = ap.locator("section[aria-labelledby=doc-h] img").first();
  await viewerImg.waitFor();
  await ap.waitForFunction(() => document.querySelector("section[aria-labelledby=doc-h] img")?.complete);
  check("I document viewer shows the committed document page", (await viewerImg.evaluate((i) => i.naturalWidth)) > 0);
  await ap.getByRole("tab", { name: /bank proof/ }).last().click();
  check("I viewer offers the linked record's bank proof", (await ap.getByRole("tab", { name: `${B.id} bank proof` }).count()) === 1);
  await ap.waitForFunction(() => [...document.querySelectorAll("section[aria-labelledby=doc-h] img")].every((i) => i.complete && i.naturalWidth > 0));
  await shot(ap, "09b-admin-linked-record");
  const noPageScroll = () => ap.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1);
  await ap.setViewportSize({ width: 1440, height: 900 });
  check("Fit-to-screen: case page does not scroll at 1440×900", await noPageScroll());
  await ap.setViewportSize({ width: 1280, height: 760 });
  check("Fit-to-screen: case page does not scroll at 1280×760", await noPageScroll());
  await ap.setViewportSize({ width: 1100, height: 700 });
  check("Below 1280×760 the page scrolls normally instead", !(await noPageScroll()));
  await ap.setViewportSize({ width: 1440, height: 950 });
  await ap.keyboard.press("?");
  await ap.getByRole("dialog", { name: "Keyboard shortcuts" }).waitFor();
  check("'?' shows the shortcut list", true);
  await ap.keyboard.press("Escape");
  await ap.keyboard.press("a");
  const approve = ap.getByRole("dialog", { name: "Approve application" });
  await approve.waitFor();
  await approve.getByRole("button", { name: "Documents consistent after manual check" }).click();
  check("I approval of a matched case blocked until call-back confirmed", await approve.getByRole("button", { name: "Approve" }).isDisabled());
  await shot(ap, "09c-admin-approve-confirmation", false);
  const serverGuard = await ap.evaluate(async (id) => {
    const c = await (await fetch(`/api/admin/applications/${id}`)).json();
    const s = await (await fetch("/api/admin/session")).json();
    const r = await fetch(`/api/admin/applications/${id}/review`, { method: "POST", headers: { "content-type": "application/json", "x-csrf-token": s.csrf_token },
      body: JSON.stringify({ action: "APPROVE", reason: "Bypassing the UI", expected_revision: c.revision, expected_latest_run_id: c.latest_run_id }) });
    return r.status;
  }, I.id);
  check("I server refuses approval without the confirmation", serverGuard === 400, `${serverGuard}`);
  await ap.keyboard.press("Escape");
  await ap.keyboard.press("r");
  const reject = ap.getByRole("dialog", { name: "Reject application" });
  await reject.waitFor();
  await reject.getByRole("button", { name: "Bank account not owned by the business" }).click();
  await shot(ap, "09d-admin-reject-dialog", false);
  await reject.getByRole("button", { name: "Reject" }).click();
  await ap.getByText("Decision saved · Message added for vendor").waitFor();
  check("I rejected via keyboard with a quick reason", true);

  // ------------------------------------------------------------ C. swapped files: warned on the slot, fixed with "Move it"
  const acme = fixture("happy");
  const C = await startDocs(page, BASE, pdf("happy", "bank"), pdf("happy", "gst"));
  check("C swapped files → both slots warn before submitting", C.states.join() === "wrong_slot,wrong_slot", C.states.join());
  check("C slot says which slot the file belongs in", (await page.locator("main").textContent())
    .includes("This looks like a bank document. Did you mean to put it in the bank slot?"));
  await shot(page, "12-apply-wrong-slot");
  check("C Continue blocked while a file is in the wrong slot", await page.getByRole("button", { name: /Continue/ }).isDisabled());
  await page.getByRole("button", { name: "Move it" }).first().click();
  const moved = await page.waitForFunction(() => [...document.querySelectorAll("[data-slot-state]")]
    .map((e) => e.getAttribute("data-slot-state")).join() === "read,read", null, { timeout: 60_000 }).then(() => true, () => false);
  check("C one 'Move it' swaps both files and reads them", moved);
  await fillDetails(page, acme);
  C.decision = await submitDetails(page, "swapped");
  check("C after the move the case is never sent back for swapped files", C.decision !== "PENDING/VENDOR", C.decision);

  // ------------------------------------------------------------ D. unreadable bank PDF: blocked at upload
  const D = await startDocs(page, BASE, pdf("frontend_ec2_review", "gst"), UNREADABLE);
  check("D unreadable bank PDF flagged on its slot", D.states.join() === "read,unreadable", D.states.join());
  check("D vendor asked for a clearer copy before submitting", (await page.locator("main").textContent()).includes("We couldn't read this file")
    && await page.getByRole("button", { name: /Continue/ }).isDisabled());

  // ------------------------------------------------------------ J. edited value + value not on the document
  const ec4 = fixture("ec4_missing_bank_holder");
  const J = await startDocs(page, BASE, pdf("ec4_missing_bank_holder", "gst"), pdf("ec4_missing_bank_holder", "bank"));
  await fillDetails(page, ec4, { edit: { ifsc: "DEMO0999999" } });
  check("J field missing from the document is marked 'Not found'", (await page.locator("main").textContent()).includes("Not found on your bank document"));
  await page.getByLabel("Account holder", { exact: true }).fill(ec4.bank_holder);
  await page.getByLabel("Account holder", { exact: true }).press("Tab");
  await page.locator('[data-tag="entered"]').waitFor();
  await page.locator('[data-tag="changed"]').waitFor();
  check("J typed value tagged 'Entered by you' and edited value 'Changed by you'", true);
  await shot(page, "12b-details-edited-and-not-found");
  const vendorNoScroll = () => page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1);
  await page.setViewportSize({ width: 1440, height: 900 });
  check("Fit-to-screen: vendor details step does not scroll at 1440×900", await vendorNoScroll());
  await page.setViewportSize({ width: 1280, height: 760 });
  check("Fit-to-screen: vendor details step does not scroll at 1280×760", await vendorNoScroll());
  await page.setViewportSize({ width: 1360, height: 900 });
  J.decision = await submitDetails(page, "edited");
  check("J changed/typed values → Pending, with our team (no action asked)", J.decision === "PENDING/TEAM", J.decision);

  // ------------------------------------------------------------ E. Gemini provider failure (real client, no key)
  const outagePage = await ctx.newPage();
  const E = await startDocs(outagePage, OUTAGE, pdf("frontend_ec2_review", "gst"), pdf("frontend_ec2_review", "bank"));
  check("E reading outage shown on the slots without blaming the files", E.states.join() === "unavailable,unavailable"
    && (await outagePage.locator("main").textContent()).includes("temporary problem on our side"), E.states.join());
  await fillDetails(outagePage, fixture("frontend_ec2_review"), { typeAll: true });
  E.decision = await submitDetails(outagePage, "outage");
  const eText = await outagePage.locator("main").textContent();
  check("E Gemini failure → Pending, with our team (never approved)", E.decision === "PENDING/TEAM", E.decision);
  check("E truthful 'temporary problem on our side' message", eText.includes("temporary problem on our side"));
  check("E does not blame the documents", !/unreadable|clearer copy/i.test(eText));
  check("E reading stage shown as couldn't finish", (await outagePage.getByText(/Couldn't finish/).count()) >= 1);
  await shot(outagePage, "13-receipt-gemini-unavailable");
  await track(outagePage, OUTAGE, E.id, E.code);
  await outagePage.getByRole("button", { name: "Retry check now" }).waitFor();
  check("E tracking offers a one-click retry", true);
  await outagePage.close();

  // ------------------------------------------------------------ F. wrong tracking code
  await track(page, BASE, A.id, "wrong-code-wrong-code-wrong");
  await page.getByText("Application ID or tracking code is incorrect.").waitFor();
  check("F wrong tracking code rejected", true);

  // ------------------------------------------------------------ G. unauthenticated admin
  const anon = await browser.newContext();
  const anonPage = await anon.newPage();
  await anonPage.goto(`${BASE}/admin`);
  await anonPage.getByRole("heading", { name: "Reviewer sign-in" }).waitFor();
  const overviewStatus = await anonPage.evaluate(async () => (await fetch("/api/admin/overview")).status);
  const caseStatus = await anonPage.evaluate(async (id) => (await fetch(`/api/admin/applications/${id}`)).status, B.id);
  check("G unauthenticated admin sees sign-in, API returns 401", overviewStatus === 401 && caseStatus === 401, `${overviewStatus}/${caseStatus}`);
  await shot(anonPage, "14-admin-signin", false);
  await anon.close();

  // ------------------------------------------------------------ admin: PDF, approve, history
  await ap.goto(`${BASE}/admin`);
  await ap.getByRole("heading", { name: "Applications" }).waitFor();
  check("Fit-to-screen: queue does not scroll at 1440×950", await ap.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 1));
  const pdfStatus = await ap.evaluate(async (id) => {
    const c = await (await fetch(`/api/admin/applications/${id}`)).json();
    const run = c.runs[0];
    const r = await fetch(`/api/admin/applications/${id}/runs/${run.id}/documents/${run.pdf_types[0]}`);
    return `${r.status} ${r.headers.get("content-type")}`;
  }, A.id);
  check("Admin can open the exact committed PDF", pdfStatus === "200 application/pdf", pdfStatus);
  await ap.getByRole("tab", { name: /All/ }).click();
  await shot(ap, "15-admin-queue-all");
  await ap.getByRole("link", { name: "Activity" }).first().click();
  await ap.getByRole("heading", { name: "Decision history" }).waitFor();
  check("Decision history shows the correction request", (await ap.locator("section", { hasText: "Decision history" }).locator("tbody").textContent()).includes("Reviewer requested a correction"));

  // ------------------------------------------------------------ mobile
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const mp = await mobile.newPage();
  await mp.goto(BASE);
  check("Mobile home has no horizontal overflow", await noHorizontalOverflow(mp));
  await shot(mp, "16-mobile-home");
  const M = await startDocs(mp, BASE, pdf("frontend_happy", "gst"), pdf("frontend_happy", "bank"));
  check("Mobile documents step fits one screen", await mp.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1)
    && await noHorizontalOverflow(mp), M.states.join());
  await shot(mp, "17-mobile-apply-documents");
  await mp.getByRole("button", { name: /Continue/ }).click();
  await mp.getByRole("heading", { name: "Check your details" }).waitFor();
  const cont = await mp.getByRole("button", { name: /Continue/ }).boundingBox();
  check("Mobile details scroll with Continue kept visible", await mp.evaluate(() => document.documentElement.scrollHeight > innerHeight)
    && cont && cont.y + cont.height <= 844 && await noHorizontalOverflow(mp));
  await track(mp, BASE, A.id, A.code);
  await mp.locator("[data-status]").first().waitFor();
  check("Mobile tracking has no horizontal overflow", await noHorizontalOverflow(mp));
  await shot(mp, "18-mobile-track");
  await mobile.close();

  // ------------------------------------------------------------ keyboard
  const kp = await ctx.newPage();
  await kp.goto(BASE);
  await kp.keyboard.press("Tab");
  const first = await kp.evaluate(() => document.activeElement?.textContent?.trim());
  check("First Tab reaches the skip link", first === "Skip to content", first);
  await kp.close();

  check("No browser console errors", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
} finally {
  await browser.close();
}
console.log(failures ? `\n${failures} check(s) FAILED` : "\nAll browser checks passed");
process.exit(failures ? 1 : 0);
