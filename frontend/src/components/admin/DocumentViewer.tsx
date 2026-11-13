import { ExternalLink, FileWarning, Minus, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { cx } from "../ui";

export interface ViewerDoc {
  key: string;
  label: string;
  applicationId: string;
  runId: string;
  docType: "GST" | "BANK";
}

const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/**
 * Inline evidence viewer. Pages are rendered to PNG by the server from the exact,
 * hash-verified document a run used, and are served only to a signed-in reviewer.
 * No PDF plugin or script from an uploaded file runs in the browser.
 */
export function DocumentViewer({ docs, className, onUnauthorized }: {
  docs: ViewerDoc[];
  className?: string;
  onUnauthorized: (e: unknown) => boolean;
}) {
  const [activeKey, setActiveKey] = useState(docs[0]?.key ?? "");
  const [zoom, setZoom] = useState(2);
  const [pages, setPages] = useState<Record<string, number | "error">>({});
  const active = docs.find((d) => d.key === activeKey) ?? docs[0];

  useEffect(() => {
    if (!docs.some((d) => d.key === activeKey)) setActiveKey(docs[0]?.key ?? "");
  }, [docs, activeKey]);

  useEffect(() => {
    if (!active || pages[active.key] !== undefined) return;
    api
      .documentPages(active.applicationId, active.runId, active.docType)
      .then((r) => setPages((p) => ({ ...p, [active.key]: r.pages })))
      .catch((e) => {
        if (!onUnauthorized(e)) setPages((p) => ({ ...p, [active.key]: "error" }));
      });
  }, [active, pages, onUnauthorized]);

  const count = active ? pages[active.key] : undefined;
  const scale = ZOOMS[zoom];
  return (
    <section aria-labelledby="doc-h" className={cx("flex flex-col overflow-hidden rounded-[20px] border border-line bg-white", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-4 py-3">
        <h2 id="doc-h" className="sr-only">Documents</h2>
        <div role="tablist" aria-label="Documents" className="flex flex-wrap gap-1.5">
          {docs.map((d) => (
            <button
              key={d.key}
              type="button"
              role="tab"
              aria-selected={d.key === active?.key}
              onClick={() => setActiveKey(d.key)}
              className={cx("rounded-full px-3.5 py-[7px] text-[13px]", d.key === active?.key ? "bg-ink font-semibold text-white" : "bg-[#F2F4F7] text-[#344054] hover:bg-slate-200")}
            >
              {d.label}
            </button>
          ))}
        </div>
        {active ? (
          <div className="flex items-center gap-1.5">
            <button type="button" aria-label="Zoom out" disabled={zoom === 0} onClick={() => setZoom((z) => Math.max(0, z - 1))} className="grid size-9 place-items-center rounded-[10px] border border-[#D0D5DD] bg-white disabled:opacity-40">
              <Minus className="size-4" aria-hidden />
            </button>
            <span className="w-12 text-center text-xs text-muted tabular" aria-live="polite">{Math.round(scale * 100)}%</span>
            <button type="button" aria-label="Zoom in" disabled={zoom === ZOOMS.length - 1} onClick={() => setZoom((z) => Math.min(ZOOMS.length - 1, z + 1))} className="grid size-9 place-items-center rounded-[10px] border border-[#D0D5DD] bg-white disabled:opacity-40">
              <Plus className="size-4" aria-hidden />
            </button>
            <a
              href={api.documentUrl(active.applicationId, active.runId, active.docType)}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-1 inline-flex items-center gap-1 text-[13px] font-medium text-navy-700 hover:underline"
            >
              Original <ExternalLink className="size-3.5" aria-hidden />
            </a>
          </div>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-line-soft p-5">
        {!active ? (
          <p className="flex h-full items-center justify-center gap-2 text-sm text-muted"><FileWarning className="size-4" aria-hidden /> No documents were used in the latest check.</p>
        ) : count === "error" ? (
          <p className="text-sm text-muted">This document can't be previewed here. Use “Original” to open it.</p>
        ) : count === undefined ? (
          <p className="text-sm text-muted">Loading document…</p>
        ) : (
          <div className={cx("flex flex-col items-center gap-4", scale <= 1 && "mx-auto")} style={{ width: 640 * scale, maxWidth: scale <= 1 ? "100%" : undefined }}>
            {Array.from({ length: count }, (_, i) => (
              <img
                key={`${active.key}-${i}`}
                src={api.documentPageUrl(active.applicationId, active.runId, active.docType, i + 1)}
                alt={`${active.label}, page ${i + 1} of ${count}`}
                className="w-full rounded-md bg-white shadow-[0_1px_3px_rgba(16,24,40,0.12)]"
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
