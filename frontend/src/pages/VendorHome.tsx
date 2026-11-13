import { ArrowRight, FileCheck2, FileText, KeyRound, ScanSearch, UserCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { VendorFrame } from "../components/AppShell";
import { useAppState } from "../state";

const NEEDS = [
  { icon: FileText, title: "GST registration certificate", text: "PDF up to 5 MB" },
  { icon: FileCheck2, title: "Cancelled cheque or bank letter", text: "PDF up to 5 MB · photos supported soon" },
];

const FLOW = [
  { icon: ScanSearch, title: "We read your documents", text: "Your details are filled in for you. You check them." },
  { icon: FileCheck2, title: "We check everything automatically", text: "You see the result right away." },
  { icon: UserCheck, title: "Our team handles anything unclear", text: "Never silently approved. We'll message you here." },
];

/** Vendor welcome (V2_02 V1): buyer, what you need, about 5 minutes, start or come back. */
export function VendorHome() {
  const { apply, meta } = useAppState();
  const buyer = meta?.workspace_name || "Zamp AI";
  const resuming = !!apply.creds && (apply.step > 0 || apply.resume);
  return (
    <VendorFrame>
      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section aria-labelledby="home-h" className="flex flex-col gap-6 rounded-2xl border border-line bg-white p-5 sm:rounded-[20px] sm:px-8 sm:py-7">
          <div className="flex flex-col gap-1.5">
            <h1 id="home-h" className="text-[22px] font-bold tracking-[-0.01em] text-ink sm:text-[26px]">Register as a supplier to {buyer}</h1>
            <p className="text-sm text-muted sm:text-[15px]">Upload two documents. We read the details for you, check them, and show you the result right away. Takes about 5 minutes.</p>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2">
            {NEEDS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex items-center gap-3 rounded-2xl border border-line px-4 py-3.5">
                <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-xl bg-navy-50"><Icon className="size-5 text-navy-600" /></span>
                <span className="flex flex-col">
                  <span className="text-[15px] font-semibold text-ink">{title}</span>
                  <span className="text-[13px] text-muted">{text}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-auto flex flex-col gap-3 border-t border-line-soft pt-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-[13px] text-muted">Your progress is saved as you go.</span>
            <Link
              to="/apply"
              className="inline-flex min-h-[52px] items-center justify-center gap-2 rounded-[14px] bg-navy-600 px-7 text-base font-semibold text-white hover:bg-navy-700 sm:min-h-11 sm:rounded-xl sm:text-[15px]"
            >
              {resuming ? "Continue your application" : "Start"} <ArrowRight className="size-4" aria-hidden />
            </Link>
          </div>
        </section>
        <aside className="flex flex-col gap-4">
          <section aria-labelledby="flow-h" className="flex flex-col gap-3.5 rounded-2xl border border-line bg-white px-5 py-5 sm:rounded-[20px] sm:px-6">
            <h2 id="flow-h" className="text-base font-semibold text-ink">How it works</h2>
            <ol className="flex flex-col gap-3.5">
              {FLOW.map(({ icon: Icon, title, text }) => (
                <li key={title} className="flex gap-3">
                  <Icon className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />
                  <span>
                    <span className="block text-sm font-medium text-ink">{title}</span>
                    <span className="block text-[13px] text-muted">{text}</span>
                  </span>
                </li>
              ))}
            </ol>
          </section>
          <Link to="/track" className="group flex items-center gap-3 rounded-2xl border border-line bg-white px-5 py-4 hover:border-navy-300 sm:rounded-[20px] sm:px-6">
            <KeyRound className="size-5 shrink-0 text-navy-600" aria-hidden />
            <span className="flex flex-1 flex-col">
              <span className="text-[15px] font-semibold text-ink">Already started?</span>
              <span className="text-[13px] text-muted">Open your application with its ID and tracking code.</span>
            </span>
            <ArrowRight className="size-4 text-muted transition-transform group-hover:translate-x-0.5" aria-hidden />
          </Link>
        </aside>
      </div>
    </VendorFrame>
  );
}
