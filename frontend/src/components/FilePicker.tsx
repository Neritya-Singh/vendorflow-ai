import { FileCheck2, FileUp, X } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import { formatBytes } from "../lib/format";
import { cx } from "./ui";

export const MAX_PDF_BYTES = 5 * 1024 * 1024;

export function validatePdf(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf")) return "Only PDF files are accepted.";
  if (file.type && file.type !== "application/pdf") return "This file is not a PDF.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_PDF_BYTES) return `This PDF is ${formatBytes(file.size)}. The limit is 5 MB.`;
  return null;
}

export function FilePicker({ label, description, file, onChange, existing }: {
  label: string;
  description: string;
  file: File | null;
  onChange: (file: File | null) => void;
  existing?: string;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const accept = (candidate: File | undefined) => {
    if (!candidate) return;
    const problem = validatePdf(candidate);
    setError(problem);
    onChange(problem ? null : candidate);
    if (input.current) input.current.value = "";
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files?.[0]);
  };

  return (
    <div>
      <p id={`${id}-label`} className="text-[13px] font-medium text-slate-800">{label}</p>
      <p className="mt-0.5 text-xs text-slate-500">{description}</p>
      <input
        ref={input}
        id={id}
        type="file"
        accept="application/pdf,.pdf"
        className="sr-only"
        aria-labelledby={`${id}-label`}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(e) => accept(e.target.files?.[0])}
      />
      {file ? (
        <div className="mt-2 flex items-center gap-3 rounded-lg border border-teal-200 bg-teal-50/60 px-3 py-2.5">
          <FileCheck2 className="size-5 shrink-0 text-teal-700" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-slate-900">{file.name}</p>
            <p className="text-xs text-slate-500">{formatBytes(file.size)} · ready to upload</p>
          </div>
          <button
            type="button"
            onClick={() => input.current?.click()}
            className="rounded-md px-2 py-1 text-[13px] font-medium text-navy-700 hover:bg-white"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={() => onChange(null)}
            className="rounded-md p-1 text-slate-500 hover:bg-white hover:text-slate-800"
            aria-label={`Remove ${file.name}`}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ) : (
        <label
          htmlFor={id}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cx(
            "mt-2 flex cursor-pointer items-center gap-3 rounded-lg border border-dashed px-3 py-3 transition-colors",
            "focus-within:ring-2 focus-within:ring-navy-600/25",
            dragging ? "border-navy-500 bg-navy-50" : error ? "border-red-300 bg-red-50/40" : "border-slate-300 bg-white hover:border-navy-400 hover:bg-slate-50",
          )}
        >
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-slate-100">
            <FileUp className="size-4 text-slate-600" aria-hidden />
          </span>
          <span className="min-w-0 text-sm">
            <span className="font-medium text-navy-700">Choose PDF</span>
            <span className="text-slate-500"> or drag it here · max 5 MB</span>
            {existing ? <span className="block text-xs text-slate-500">{existing}</span> : null}
          </span>
        </label>
      )}
      {error ? <p id={`${id}-error`} role="alert" className="mt-1.5 text-xs font-medium text-red-700">{error}</p> : null}
    </div>
  );
}
