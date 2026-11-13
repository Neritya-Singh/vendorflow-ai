import { ArrowRight, Building2, FileCheck2, FileText, Landmark, Lock, ScanSearch, Search, UserCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/AppShell";
import { Card } from "../components/ui";
import { useAppState } from "../state";

const NEEDS = [
  { icon: Building2, title: "Business details", text: "Legal name, state, PAN and GSTIN" },
  { icon: Landmark, title: "Bank details", text: "Account holder, account number and IFSC" },
  { icon: FileText, title: "GST certificate", text: "PDF with selectable text, up to 5 MB" },
  { icon: FileCheck2, title: "Bank proof", text: "Bank letter or cancelled cheque as a PDF" },
];

const FLOW = [
  { icon: ScanSearch, title: "Documents are read", text: "Text is extracted from your PDFs and key fields identified." },
  { icon: FileCheck2, title: "Rules compare everything", text: "Fixed checks compare your form with your documents." },
  { icon: UserCheck, title: "People handle exceptions", text: "Anything unclear goes to a reviewer — never silently approved." },
];

export function VendorHome() {
  const { draft } = useAppState();
  const resuming = draft.step > 0 || draft.fields.legal_name;
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
      <PageHeader
        eyebrow="Vendor workspace"
        title="Become an approved vendor"
        description="Submit your business and bank details with two PDFs. Watch each check run live, then get a decision with clear reasons and a next step."
      />

      <div className="mt-7 grid gap-4 md:grid-cols-2">
        <Link to="/apply" className="group rounded-xl focus-visible:outline-offset-4">
          <Card as="div" className="h-full border-navy-900 bg-navy-900 p-6 text-white transition-shadow group-hover:shadow-raised">
            <p className="text-xs font-semibold uppercase tracking-wider text-teal-300">{resuming ? "Draft in progress" : "New vendor"}</p>
            <h2 className="mt-2 text-xl font-semibold">{resuming ? "Continue your application" : "Start application"}</h2>
            <p className="mt-1.5 text-sm text-navy-100">Three short steps: business, banking & PDFs, then review and submit.</p>
            <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-white">
              {resuming ? "Continue" : "Start now"} <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </span>
          </Card>
        </Link>
        <Link to="/track" className="group rounded-xl focus-visible:outline-offset-4">
          <Card as="div" className="h-full p-6 transition-shadow group-hover:shadow-raised">
            <p className="text-xs font-semibold uppercase tracking-wider text-navy-600">Already applied</p>
            <h2 className="mt-2 text-xl font-semibold text-slate-900">Track existing application</h2>
            <p className="mt-1.5 text-sm text-slate-600">See your decision, reviewer messages and history, or correct a pending application.</p>
            <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-navy-800">
              <Search className="size-4" aria-hidden /> Track with ID and code
            </span>
          </Card>
        </Link>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Card className="p-6">
          <h2 className="text-[15px] font-semibold text-slate-900">What you'll need</h2>
          <ul className="mt-4 grid gap-4 sm:grid-cols-2">
            {NEEDS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-navy-50">
                  <Icon className="size-4 text-navy-700" aria-hidden />
                </span>
                <span>
                  <span className="block text-sm font-medium text-slate-900">{title}</span>
                  <span className="block text-[13px] text-slate-500">{text}</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-5 rounded-lg bg-slate-50 px-3 py-2.5 text-[13px] text-slate-600">
            For India GST-registered businesses. Scanned images without selectable text can't be read automatically and
            will be routed to a reviewer.
          </p>
        </Card>
        <Card className="p-6">
          <h2 className="text-[15px] font-semibold text-slate-900">How decisions are made</h2>
          <ol className="mt-4 space-y-4">
            {FLOW.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3">
                <Icon className="mt-0.5 size-4 shrink-0 text-teal-700" aria-hidden />
                <span>
                  <span className="block text-sm font-medium text-slate-900">{title}</span>
                  <span className="block text-[13px] text-slate-500">{text}</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-5 flex gap-2 text-[13px] text-slate-600">
            <Lock className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden />
            Documents are stored privately and are visible only to authorised reviewers.
          </p>
        </Card>
      </div>
    </div>
  );
}
