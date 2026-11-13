import { ArrowLeftRight, Camera, Check, Loader2, RotateCcw, TriangleAlert, Upload } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import type { DraftFile, Slot } from "../../lib/types";
import { Button, cx } from "../ui";

export const SLOT_TITLES: Record<Slot, string> = {
  GST: "GST registration certificate",
  BANK: "Cancelled cheque or bank letter",
};
export const SLOT_SHORT: Record<Slot, string> = { GST: "GST certificate", BANK: "Bank document" };

export interface SlotActivity {
  filename: string;
  /** Live server stage: "Received", "Identified the document type", "Read the details". */
  stage: string;
  progress: number;
}

/**
 * One upload slot. Reading starts as soon as a file is chosen (V2_03 §4.3), so the
 * vendor can pick the next file while this one is read. Every status shown here
 * comes from the server's reading stages and saved draft, never from a timer.
 */
export function DocumentSlot({ slot, file, activity, error, maxBytes, onFile, onMove, onRetry, note }: {
  slot: Slot;
  file: DraftFile | null;
  activity: SlotActivity | null;
  error: string | null;
  maxBytes: number;
  onFile: (file: File) => void;
  onMove: () => void;
  onRetry: (() => void) | null;
  /** Extra line under an empty slot, e.g. which file is on file now. */
  note?: string;
}) {
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const title = SLOT_TITLES[slot];
  const choose = () => input.current?.click();
  const picker = (
    <input
      ref={input}
      id={inputId}
      type="file"
      accept=".pdf,application/pdf"
      className="sr-only"
      aria-label={`${title} file`}
      data-slot={slot}
      onChange={(e) => {
        const chosen = e.target.files?.[0];
        e.target.value = "";
        if (chosen) onFile(chosen);
      }}
    />
  );
  const tooBig = `Files can be up to ${Math.round(maxBytes / 1024 / 1024)} MB.`;
  const errorLine = error ? <p role="alert" className="text-[13px] font-medium text-[#B42318]">{error}</p> : null;

  if (activity) {
    return (
      <div data-slot-state="reading" className="flex items-center gap-4 rounded-2xl border border-navy-200 bg-[#F5F7FF] px-4 py-3.5 sm:px-5 sm:py-4">
        <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-xl bg-navy-100">
          <Loader2 className="size-5 animate-spin text-navy-600" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="text-[15px] font-semibold text-ink">{title}</span>
          <span className="truncate text-[13px] text-[#344054]" aria-live="polite">
            {activity.filename} · {activity.stage}…
          </span>
          <div aria-hidden className="h-1.5 overflow-hidden rounded-full bg-navy-100">
            <div className="h-1.5 rounded-full bg-navy-600 transition-[width] duration-300" style={{ width: `${activity.progress}%` }} />
          </div>
        </div>
      </div>
    );
  }

  if (!file) {
    return (
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e: DragEvent) => {
            e.preventDefault();
            setOver(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) onFile(dropped);
          }}
          data-slot-state="empty"
          className={cx(
            "flex cursor-pointer flex-col gap-3 rounded-2xl border-2 border-dashed px-4 py-4 sm:flex-row sm:items-center sm:px-5",
            over ? "border-navy-500 bg-navy-50" : "border-[#B4BCF0] bg-[#FAFBFF]",
          )}
        >
          <span className="flex min-w-0 flex-1 items-center gap-3">
            <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-xl bg-navy-50">
              <Upload className="size-5 text-navy-600" />
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="text-[15px] font-semibold text-ink">{title}</span>
              <span className="text-[13px] text-muted">
                <span className="hidden sm:inline">Drop the file here or </span>
                <span className="font-semibold text-navy-600 underline">browse</span> · PDF up to 5 MB
              </span>
            </span>
          </span>
          <span className="grid grid-cols-2 gap-2 sm:flex sm:items-center">
            <span className="inline-flex min-h-11 items-center justify-center rounded-xl bg-navy-600 px-4 text-sm font-semibold text-white sm:hidden">
              Choose file
            </span>
            <button
              type="button"
              disabled
              title="Photos are supported soon"
              className="inline-flex min-h-11 cursor-not-allowed flex-col items-center justify-center rounded-xl border border-[#D0D5DD] bg-white px-3 text-[13px] font-semibold leading-tight text-[#98A2B3]"
            >
              <span className="inline-flex items-center gap-1.5"><Camera className="size-4" aria-hidden /> Take photo</span>
              <span className="text-[11px] font-medium">Photos supported soon</span>
            </button>
          </span>
          {picker}
        </label>
        {note ? <p className="text-[13px] text-muted">{note}</p> : null}
        {errorLine}
        {error?.includes("5 MB") ? <span className="sr-only">{tooBig}</span> : null}
      </div>
    );
  }

  const good = file.status === "read";
  const wrong = file.status === "wrong_slot";
  return (
    <div className="flex flex-col gap-1.5">
      <div
        data-slot-state={file.status}
        className={cx(
          "flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl border px-4 py-3.5 sm:px-5 sm:py-4",
          good ? "border-[#ABEFC6] bg-[#F6FEF9]" : "border-[#FEC84B] bg-[#FFFCF5]",
        )}
      >
        <span aria-hidden className={cx("grid size-10 shrink-0 place-items-center rounded-xl", good ? "bg-teal-100" : "bg-[#FEF0C7]")}>
          {good ? <Check className="size-5 text-teal-700" strokeWidth={2.5} /> : <TriangleAlert className="size-5 text-[#B54708]" />}
        </span>
        <div className="flex min-w-[min(100%,14rem)] flex-1 flex-col gap-0.5">
          <span className="text-[15px] font-semibold text-ink">{title}</span>
          <span className="break-words text-[13px] text-[#344054]">
            <span className="text-muted">{file.filename}</span> · {file.message}
          </span>
        </div>
        <div className="flex w-full gap-2 sm:w-auto [&>*]:flex-1 sm:[&>*]:flex-none">
          {wrong ? <Button size="md" icon={ArrowLeftRight} onClick={onMove}>Move it</Button> : null}
          {file.status === "unavailable" && onRetry ? <Button size="md" variant="secondary" icon={RotateCcw} onClick={onRetry}>Try again</Button> : null}
          <Button size="md" variant="secondary" onClick={choose}>Replace</Button>
        </div>
        {picker}
      </div>
      {errorLine}
    </div>
  );
}
